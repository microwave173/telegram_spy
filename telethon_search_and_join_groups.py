#!/usr/bin/env python3
"""Search public Telegram groups, inspect public history without joining,
extract t.me links, and maintain a local dedupe state.

Examples:
  python3 telethon_search_and_join_groups.py
  python3 telethon_search_and_join_groups.py --keywords-file keywords.txt --history-limit 30
  python3 telethon_search_and_join_groups.py --candidate-links-file candidate_links.txt
  python3 telethon_search_and_join_groups.py --proxy-host 127.0.0.1 --proxy-port 7890
"""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from telethon import TelegramClient, functions, types, utils
from telethon.errors import InviteRequestSentError, UserAlreadyParticipantError

from dashboard_state import append_collect_group, utc_now_iso

TME_LINK_RE = re.compile(r"(https?://t\.me/[^\s<>()]+|t\.me/[^\s<>()]+)", re.IGNORECASE)
TGSTAT_URL_RE = re.compile(r"https?://(?:www\.)?tgstat\.(?:org|com)/[^\s<>()]+", re.IGNORECASE)
TGSTAT_USERNAME_RE = re.compile(r"Username:\s*@([A-Za-z][A-Za-z0-9_]{3,})", re.IGNORECASE)
AT_USERNAME_RE = re.compile(r"(?<![\w/])@([A-Za-z][A-Za-z0-9_]{3,})")


def read_api_credentials(keys_path: Path) -> tuple[int, str]:
    api_id = None
    api_hash = None

    with keys_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "api_id":
                api_id = int(value)
            elif key == "api_hash":
                api_hash = value

    if api_id is None or not api_hash:
        raise ValueError("keys.txt missing api_id or api_hash")
    return api_id, api_hash


def load_lines(path: Path, empty_error: str, missing_ok: bool = False) -> list[str]:
    if not path.exists():
        if missing_ok:
            return []
        raise FileNotFoundError(f"file not found: {path}")

    lines = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)

    if not lines and not missing_ok:
        raise ValueError(empty_error)
    return lines


def normalize_tme_link(link: str) -> str:
    normalized = link.strip()
    if normalized.startswith("http://"):
        normalized = normalized[len("http://") :]
    elif normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    if normalized.startswith("t.me/"):
        normalized = normalized[len("t.me/") :]
    normalized = normalized.strip("/")
    if normalized.startswith("s/"):
        normalized = normalized[2:]
    return normalized


def canonicalize_tme_link(link: str) -> str:
    normalized = normalize_tme_link(link)
    return f"https://t.me/{normalized}"


def normalize_public_username(raw_username: str) -> str | None:
    username = raw_username.strip()
    if username.startswith("@"):
        username = username[1:]
    if not username:
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", username):
        return None
    return username


def to_public_username_ref(raw_ref: str) -> str | None:
    normalized = normalize_tme_link(raw_ref)
    if normalized.startswith("+") or normalized.startswith("joinchat/"):
        return None
    username = normalized.split("/", 1)[0]
    return normalize_public_username(username)


def extract_candidate_usernames_from_text(text: str) -> set[str]:
    usernames = set()

    for match in TME_LINK_RE.finditer(text):
        username = to_public_username_ref(match.group(0).rstrip(".,;!?"))
        if username:
            usernames.add(username)

    for match in TGSTAT_USERNAME_RE.finditer(text):
        username = normalize_public_username(match.group(1))
        if username:
            usernames.add(username)

    for match in AT_USERNAME_RE.finditer(text):
        username = normalize_public_username(match.group(1))
        if username:
            usernames.add(username)

    return usernames


def fetch_tgstat_page_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


def resolve_candidate_usernames(raw_item: str, tgstat_cache: dict[str, set[str]]) -> tuple[set[str], list[str]]:
    usernames = set()
    notes = []

    direct_usernames = extract_candidate_usernames_from_text(raw_item)
    if direct_usernames:
        usernames.update(direct_usernames)
        notes.append(f"direct={len(direct_usernames)}")

    tgstat_urls = [match.group(0).rstrip(".,;!?") for match in TGSTAT_URL_RE.finditer(raw_item)]
    for tgstat_url in tgstat_urls:
        if tgstat_url in tgstat_cache:
            fetched_usernames = tgstat_cache[tgstat_url]
        else:
            try:
                fetched_text = fetch_tgstat_page_text(tgstat_url)
                fetched_usernames = extract_candidate_usernames_from_text(fetched_text)
            except Exception as e:
                fetched_usernames = set()
                notes.append(f"tgstat_fetch_error={type(e).__name__}")
            tgstat_cache[tgstat_url] = fetched_usernames

        if fetched_usernames:
            usernames.update(fetched_usernames)
            notes.append(f"tgstat={len(fetched_usernames)}")

    return usernames, notes


def load_seen_state(path: Path) -> dict:
    if not path.exists():
        return {"processed_groups": {}, "discovered_links": [], "all_groups": [], "group_tree": []}

    data = json.loads(path.read_text(encoding="utf-8"))
    if "processed_groups" not in data:
        data["processed_groups"] = {}
    if "discovered_links" not in data:
        data["discovered_links"] = []
    if "all_groups" not in data:
        data["all_groups"] = []
    if "group_tree" not in data:
        data["group_tree"] = []
    return data


def load_listen_targets(path: Path) -> dict[str, list[int]]:
    if not path.exists():
        return {"private_chat_ids": [], "group_chat_ids": []}

    data = json.loads(path.read_text(encoding="utf-8"))
    private_chat_ids = data.get("private_chat_ids", [])
    group_chat_ids = data.get("group_chat_ids", [])
    if not isinstance(private_chat_ids, list) or not isinstance(group_chat_ids, list):
        raise ValueError("listen_targets.json must contain private_chat_ids and group_chat_ids arrays")
    return {
        "private_chat_ids": [int(x) for x in private_chat_ids],
        "group_chat_ids": [normalize_listen_group_id(int(x)) for x in group_chat_ids],
    }


def normalize_listen_group_id(group_id: int) -> int:
    if group_id > 0:
        return int(f"-100{group_id}")
    return group_id


def add_group_id_to_listen_targets(path: Path, group_id: int) -> bool:
    data = load_listen_targets(path)
    group_chat_ids = set(data["group_chat_ids"])
    if group_id in group_chat_ids:
        return False

    group_chat_ids.add(group_id)
    updated = {
        "private_chat_ids": data["private_chat_ids"],
        "group_chat_ids": sorted(group_chat_ids),
    }
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def sync_seen_groups_to_listen_targets(path: Path, processed_groups: dict) -> int:
    data = load_listen_targets(path)
    group_chat_ids = set(data["group_chat_ids"])
    before_count = len(group_chat_ids)

    for info in processed_groups.values():
        group_id = info.get("listen_chat_id") or info.get("id")
        if group_id is None:
            continue
        group_chat_ids.add(normalize_listen_group_id(int(group_id)))

    updated = {
        "private_chat_ids": data["private_chat_ids"],
        "group_chat_ids": sorted(group_chat_ids),
    }
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(group_chat_ids) - before_count


def rebuild_all_groups(processed_groups: dict) -> list[dict]:
    all_groups = []

    for username, info in processed_groups.items():
        group_id = info.get("id")
        title = info.get("title") or username
        if group_id is None:
            continue
        all_groups.append(
            {
                "title": title,
                "username": username,
                "id": group_id,
                "depth": info.get("depth", 0),
            }
        )

    all_groups.sort(key=lambda item: (item.get("depth", 0), (item.get("title") or "").lower(), item["id"]))
    return all_groups


def rebuild_group_tree(processed_groups: dict) -> list[dict]:
    node_map = {}
    roots = []

    for username, info in processed_groups.items():
        group_id = info.get("id")
        if group_id is None:
            continue
        node_map[username] = {
            "title": info.get("title") or username,
            "username": username,
            "id": group_id,
            "depth": info.get("depth", 0),
            "children": [],
        }

    for username, info in processed_groups.items():
        if username not in node_map:
            continue
        parent_username = info.get("parent_username")
        if parent_username and parent_username in node_map:
            node_map[parent_username]["children"].append(node_map[username])
        else:
            roots.append(node_map[username])

    def sort_nodes(nodes: list[dict]) -> None:
        nodes.sort(key=lambda item: (item.get("depth", 0), (item.get("title") or "").lower(), item["id"]))
        for node in nodes:
            sort_nodes(node["children"])

    sort_nodes(roots)
    return roots


def save_seen_state(path: Path, state: dict) -> None:
    state["all_groups"] = rebuild_all_groups(state["processed_groups"])
    state["group_tree"] = rebuild_group_tree(state["processed_groups"])
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_public_group(chat) -> bool:
    return (
        isinstance(chat, types.Channel)
        and getattr(chat, "megagroup", False)
        and bool(getattr(chat, "username", None))
    )


def dedupe_public_groups(chats) -> list[types.Channel]:
    seen_keys = set()
    unique_chats = []

    for chat in chats:
        if not is_public_group(chat):
            continue

        username = getattr(chat, "username", None)
        chat_id = getattr(chat, "id", None)
        key = username or chat_id
        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_chats.append(chat)

    return unique_chats


def extract_tme_links(text: str | None) -> list[str]:
    if not text:
        return []
    links = {canonicalize_tme_link(match.group(0).rstrip(".,;!?")) for match in TME_LINK_RE.finditer(text)}
    return sorted(links)


async def search_public_groups(
    client: TelegramClient, keyword: str, limit: int
) -> tuple[list[types.Channel], int, int]:
    global_result = await client(
        functions.messages.SearchGlobalRequest(
            q=keyword,
            filter=types.InputMessagesFilterEmpty(),
            min_date=None,
            max_date=None,
            offset_rate=0,
            offset_peer=types.InputPeerEmpty(),
            offset_id=0,
            limit=limit,
            groups_only=True,
        )
    )
    contacts_result = await client(functions.contacts.SearchRequest(q=keyword, limit=limit))

    global_chats = getattr(global_result, "chats", [])
    contacts_chats = getattr(contacts_result, "chats", [])
    public_groups = dedupe_public_groups([*global_chats, *contacts_chats])
    return public_groups, len(global_chats), len(contacts_chats)


async def inspect_public_history(client: TelegramClient, username: str, history_limit: int) -> dict:
    entity = await client.get_entity(username)

    collected_links = set()
    sample_messages = []
    nonempty_messages = 0
    messages_fetched = 0

    iter_limit = None if history_limit <= 0 else history_limit

    async for message in client.iter_messages(entity, limit=iter_limit):
        messages_fetched += 1
        text = (message.message or "").strip()
        if text:
            nonempty_messages += 1
            if len(sample_messages) < 5:
                sample_messages.append(text[:200])
        collected_links.update(extract_tme_links(text))

    return {
        "title": getattr(entity, "title", None) or username,
        "username": getattr(entity, "username", None) or username,
        "id": getattr(entity, "id", None),
        "listen_chat_id": utils.get_peer_id(entity),
        "history_limit": history_limit,
        "messages_fetched": messages_fetched,
        "nonempty_messages": nonempty_messages,
        "sample_messages": sample_messages,
        "tme_links": sorted(collected_links),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def join_public_group(client: TelegramClient, username: str) -> str:
    try:
        await client(functions.channels.JoinChannelRequest(channel=username))
        return "joined"
    except UserAlreadyParticipantError:
        return "already_member"
    except InviteRequestSentError:
        return "pending_approval"


def merge_candidate_username(candidate_map: dict, username: str, source_type: str, source_value: str) -> None:
    item = candidate_map.setdefault(
        username,
        {
            "source_keywords": [],
            "source_links": [],
            "discovered_from": [],
            "parent_username": None,
            "depth": 0,
        },
    )
    if source_type == "keyword" and source_value not in item["source_keywords"]:
        item["source_keywords"].append(source_value)
    if source_type == "link" and source_value not in item["source_links"]:
        item["source_links"].append(source_value)
    if source_type == "discovered_from" and source_value not in item["discovered_from"]:
        item["discovered_from"].append(source_value)


def set_candidate_parent(candidate_map: dict, username: str, parent_username: str | None, depth: int) -> None:
    item = candidate_map.setdefault(
        username,
        {
            "source_keywords": [],
            "source_links": [],
            "discovered_from": [],
            "parent_username": None,
            "depth": depth,
        },
    )
    current_depth = item.get("depth")
    if current_depth is None or depth < current_depth:
        item["depth"] = depth
        item["parent_username"] = parent_username
    elif item.get("parent_username") is None and parent_username is not None:
        item["parent_username"] = parent_username


async def async_main() -> None:
    parser = argparse.ArgumentParser(
        description="Search public Telegram groups, inspect history without joining, and collect t.me links"
    )
    parser.add_argument(
        "--keywords-file",
        default="keywords.txt",
        help="Keyword file, one keyword per line (default: keywords.txt)",
    )
    parser.add_argument(
        "--candidate-links-file",
        default="candidate_links.txt",
        help="Optional file with candidate @usernames or t.me links from TGStat/directories (default: candidate_links.txt)",
    )
    parser.add_argument(
        "--seen-file",
        default="seen_groups.json",
        help="Local dedupe/output state file (default: seen_groups.json)",
    )
    parser.add_argument(
        "--listen-targets-file",
        default="listen_targets.json",
        help="Listen targets JSON file used by telethon_talk.py (default: listen_targets.json)",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=20,
        help="Max raw search results per keyword per API path (default: 20)",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=30,
        help="How many recent messages to inspect from each public group; use 0 for all visible history (default: 30)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively inspect newly discovered public t.me links from message history",
    )
    parser.add_argument(
        "--max-groups",
        type=int,
        default=100,
        help="Maximum number of new groups to inspect in one run (default: 100)",
    )
    parser.add_argument(
        "--max-joins",
        type=int,
        default=-1,
        help="Maximum number of newly joined groups in one run; -1 means unlimited (default: -1)",
    )
    parser.add_argument(
        "--add-to-listen-targets",
        action="store_true",
        help="Append joined group ids to listen_targets.json group_chat_ids",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=-1,
        help="Maximum recursive discovery depth; roots are depth 0, -1 means unlimited (default: -1)",
    )
    parser.add_argument("--proxy-host", help="SOCKS5 proxy host, e.g. 127.0.0.1")
    parser.add_argument("--proxy-port", type=int, help="SOCKS5 proxy port, e.g. 7890")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    keys_path = base_dir / "keys.txt"
    session_name = str(base_dir / "telethon_user_session")
    keywords_path = (base_dir / args.keywords_file) if not Path(args.keywords_file).is_absolute() else Path(args.keywords_file)
    candidate_links_path = (
        (base_dir / args.candidate_links_file)
        if not Path(args.candidate_links_file).is_absolute()
        else Path(args.candidate_links_file)
    )
    seen_path = (base_dir / args.seen_file) if not Path(args.seen_file).is_absolute() else Path(args.seen_file)
    listen_targets_path = (
        (base_dir / args.listen_targets_file)
        if not Path(args.listen_targets_file).is_absolute()
        else Path(args.listen_targets_file)
    )

    api_id, api_hash = read_api_credentials(keys_path)
    keywords = load_lines(keywords_path, empty_error="keywords.txt is empty")
    candidate_links = load_lines(
        candidate_links_path,
        empty_error="candidate_links.txt is empty",
        missing_ok=True,
    )
    seen_state = load_seen_state(seen_path)
    processed_groups = seen_state["processed_groups"]
    discovered_links = set(seen_state["discovered_links"])

    proxy = None
    if args.proxy_host and args.proxy_port:
        proxy = ("socks5", args.proxy_host, args.proxy_port)

    candidate_map = {}

    async with TelegramClient(session_name, api_id, api_hash, proxy=proxy) as client:
        await client.start()
        me = await client.get_me()
        print(f"Logged in as: {me.username or me.first_name} (id={me.id})")
        print(f"Loaded {len(keywords)} keyword(s) from {keywords_path}")
        print(f"Loaded {len(candidate_links)} imported candidate link(s) from {candidate_links_path}")
        print(f"Recursive discovery: {'on' if args.recursive else 'off'}")
        print(f"Max discovery depth: {args.max_depth}")
        print(f"Max joins: {args.max_joins}")
        print(f"Add joined ids to listen targets: {'on' if args.add_to_listen_targets else 'off'}")

        for keyword in keywords:
            print(f"\n=== Searching keyword: {keyword} ===")
            public_groups, global_chat_count, contacts_chat_count = await search_public_groups(
                client, keyword, args.search_limit
            )
            print(
                f"Raw hits: searchGlobal.chats={global_chat_count}, contacts.search.chats={contacts_chat_count}"
            )
            if not public_groups:
                print("No public groups found.")
                continue

            for chat in public_groups:
                username = getattr(chat, "username", None)
                if username:
                    merge_candidate_username(candidate_map, username, "keyword", keyword)
                    set_candidate_parent(candidate_map, username, None, 0)

        tgstat_cache = {}
        imported_candidate_count = 0
        for raw_link in candidate_links:
            usernames, notes = resolve_candidate_usernames(raw_link, tgstat_cache)
            if not usernames:
                print(f"Skipping unsupported candidate input: {raw_link}")
                continue

            imported_candidate_count += len(usernames)
            for username in usernames:
                merge_candidate_username(candidate_map, username, "link", raw_link)
                set_candidate_parent(candidate_map, username, None, 0)

            if notes:
                print(f"Imported from candidate input: {raw_link} ({', '.join(notes)})")

        if candidate_links:
            print(f"Imported {imported_candidate_count} candidate username(s) from candidate inputs.")

        print(f"\nCollected {len(candidate_map)} unique public candidate group(s).")

        pending_usernames = deque(sorted(candidate_map))
        queued_usernames = set(pending_usernames)
        inspected_count = 0
        skipped_seen_count = 0
        error_count = 0
        joined_success_count = 0
        already_member_count = 0
        pending_approval_count = 0
        listen_targets_added_count = 0

        while pending_usernames:
            if inspected_count >= args.max_groups:
                print(f"Reached max group inspection limit: {args.max_groups}")
                break
            if args.max_joins >= 0 and joined_success_count >= args.max_joins:
                print(f"Reached max join limit: {args.max_joins}")
                break

            username = pending_usernames.popleft()
            metadata = candidate_map[username]

            if username in processed_groups:
                skipped_seen_count += 1
                print(f"Skipping already-seen group: @{username}")
                continue

            print(f"\n--- Joining group: @{username} ---")
            try:
                join_status = await join_public_group(client, username)
                if join_status == "joined":
                    joined_success_count += 1
                    print(f"Join success: @{username}")
                elif join_status == "already_member":
                    already_member_count += 1
                    print(f"Already a member: @{username}")
                elif join_status == "pending_approval":
                    pending_approval_count += 1
                    print(f"Join request sent and pending approval: @{username}")

                if join_status == "pending_approval":
                    processed_groups[username] = {
                        "username": username,
                        "source_keywords": metadata["source_keywords"],
                        "source_links": metadata["source_links"],
                        "discovered_from": metadata["discovered_from"],
                        "parent_username": metadata["parent_username"],
                        "depth": metadata.get("depth", 0),
                        "join_status": join_status,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                    seen_state["processed_groups"] = processed_groups
                    seen_state["discovered_links"] = sorted(discovered_links)
                    save_seen_state(seen_path, seen_state)
                    continue

                inspection = await inspect_public_history(client, username, args.history_limit)
                inspection["source_keywords"] = metadata["source_keywords"]
                inspection["source_links"] = metadata["source_links"]
                inspection["discovered_from"] = metadata["discovered_from"]
                inspection["parent_username"] = metadata["parent_username"]
                inspection["depth"] = metadata.get("depth", 0)
                inspection["join_status"] = join_status
                processed_groups[username] = inspection
                discovered_links.update(inspection["tme_links"])
                inspected_count += 1
                print(
                    f"Fetched {inspection['messages_fetched']} message(s), extracted {len(inspection['tme_links'])} t.me link(s), depth={inspection['depth']}."
                )

                if join_status == "joined":
                    append_collect_group(
                        {
                            "timestamp": utc_now_iso(),
                            "chat_id": inspection.get("listen_chat_id") or inspection["id"],
                            "title": inspection["title"],
                            "username": inspection["username"],
                            "source_keywords": metadata["source_keywords"],
                            "source_links": metadata["source_links"],
                        }
                    )

                if args.add_to_listen_targets and join_status in {"joined", "already_member"}:
                    if add_group_id_to_listen_targets(
                        listen_targets_path, inspection.get("listen_chat_id") or inspection["id"]
                    ):
                        listen_targets_added_count += 1
                        print(
                            f"Added group id to listen targets: {inspection.get('listen_chat_id') or inspection['id']}"
                        )

                if args.recursive:
                    next_depth = metadata.get("depth", 0) + 1
                    within_depth = args.max_depth < 0 or next_depth <= args.max_depth
                    if not within_depth:
                        continue
                    for link in inspection["tme_links"]:
                        discovered_username = to_public_username_ref(link)
                        if not discovered_username:
                            continue
                        merge_candidate_username(
                            candidate_map,
                            discovered_username,
                            "discovered_from",
                            f"@{username}",
                        )
                        merge_candidate_username(candidate_map, discovered_username, "link", link)
                        set_candidate_parent(candidate_map, discovered_username, username, next_depth)
                        if (
                            discovered_username not in processed_groups
                            and discovered_username not in queued_usernames
                        ):
                            pending_usernames.append(discovered_username)
                            queued_usernames.add(discovered_username)
                            print(f"Queued discovered public group: @{discovered_username}")
            except Exception as e:
                processed_groups[username] = {
                    "username": username,
                    "source_keywords": metadata["source_keywords"],
                    "source_links": metadata["source_links"],
                    "discovered_from": metadata["discovered_from"],
                    "parent_username": metadata["parent_username"],
                    "depth": metadata.get("depth", 0),
                    "join_status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                error_count += 1
                print(f"Failed to inspect @{username}: {type(e).__name__}: {e}")

            seen_state["processed_groups"] = processed_groups
            seen_state["discovered_links"] = sorted(discovered_links)
            save_seen_state(seen_path, seen_state)

        if args.add_to_listen_targets:
            synced_count = sync_seen_groups_to_listen_targets(listen_targets_path, processed_groups)
            if synced_count > 0:
                listen_targets_added_count += synced_count
                print(f"Synced {synced_count} additional group id(s) from seen state to listen targets.")

    print("\nDone.")
    print(f"Successfully joined new groups: {joined_success_count}")
    print(f"Already-member groups: {already_member_count}")
    print(f"Pending approval groups: {pending_approval_count}")
    print(f"Added ids to listen targets: {listen_targets_added_count}")
    print(f"Inspected new groups: {inspected_count}")
    print(f"Skipped already-seen groups: {skipped_seen_count}")
    print(f"Inspection errors: {error_count}")
    print(f"State saved to: {seen_path}")


if __name__ == "__main__":
    asyncio.run(async_main())
