#!/usr/bin/env python3
"""Send text/files/images to Telegram contacts or groups via Telethon.

Examples:
  python3 telethon_send_cli.py --list-dialogs
  python3 telethon_send_cli.py --targets "传 李" --message "hello"
  python3 telethon_send_cli.py --targets "传 李,@somegroup" --file candidate_links.txt --image image.png
  python3 telethon_send_cli.py --targets-file targets.txt --message "ping" --schedule-in 60
  python3 telethon_send_cli.py --targets "传 李" --message "heartbeat" --repeat 5 --interval-seconds 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from telethon import TelegramClient

BASE_DIR = Path(__file__).resolve().parent
KEYS_PATH = BASE_DIR / "keys.txt"
SESSION_NAME = str(BASE_DIR / "telethon_user_session")


@dataclass
class ResolvedTarget:
    chat_id: int
    name: str
    username: str
    chat_type: str
    entity: object


def read_api_credentials(path: Path) -> tuple[int, str]:
    api_id = None
    api_hash = None

    with path.open("r", encoding="utf-8") as f:
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


def parse_csv_items(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def load_targets_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"targets file not found: {path}")
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def resolve_book_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def load_target_book(path: Path) -> dict:
    if not path.exists():
        return {"groups": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"target book must be a JSON object: {path}")
    groups = data.get("groups", {})
    if not isinstance(groups, dict):
        raise ValueError(f"target book field 'groups' must be an object: {path}")
    normalized_groups = {}
    for group_name, group_targets in groups.items():
        if not isinstance(group_name, str):
            raise ValueError("target group name must be string")
        if not isinstance(group_targets, list):
            raise ValueError(f"target group '{group_name}' must be a list")
        cleaned = []
        for item in group_targets:
            if not isinstance(item, str):
                raise ValueError(f"target in group '{group_name}' must be string")
            value = item.strip()
            if value:
                cleaned.append(value)
        normalized_groups[group_name] = cleaned
    return {"groups": normalized_groups}


def print_target_book_groups(path: Path, target_book: dict) -> None:
    groups = target_book.get("groups", {})
    print(f"target_book={path}")
    if not groups:
        print("(no groups)")
        return
    for name in sorted(groups):
        print(f"- {name}: {len(groups[name])} target(s)")


def looks_like_chat_id(token: str) -> bool:
    return re.fullmatch(r"-?\d+", token) is not None


def normalize_tme_ref(token: str) -> str:
    value = token.strip()
    if value.startswith("https://t.me/"):
        return value[len("https://t.me/") :]
    if value.startswith("http://t.me/"):
        return value[len("http://t.me/") :]
    if value.startswith("t.me/"):
        return value[len("t.me/") :]
    return value


def parse_datetime_local(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send Telegram text/files/images to one or more contacts/groups via Telethon",
    )
    parser.add_argument("--targets", help="Comma-separated target list (display name, @username, t.me/... or chat_id)")
    parser.add_argument("--targets-file", help="File with one target per line")
    parser.add_argument("--target-ids", help="Comma-separated numeric chat IDs")
    parser.add_argument(
        "--groups",
        help="Comma-separated target group names loaded from --target-book",
    )
    parser.add_argument(
        "--target-book",
        default="send_target_groups.json",
        help="JSON file storing target groups (default: send_target_groups.json)",
    )
    parser.add_argument(
        "--match-mode",
        choices=["exact", "contains"],
        default="exact",
        help="How display-name targets are matched in dialog list (default: exact)",
    )

    parser.add_argument("--message", default="", help="Text message to send")
    parser.add_argument("--message-file", help="Read message text from file")
    parser.add_argument("--file", dest="files", action="append", default=[], help="Document path; can be repeated")
    parser.add_argument("--image", dest="images", action="append", default=[], help="Image path; can be repeated")

    parser.add_argument("--schedule-in", type=int, default=0, help="Delay before first send in seconds (default: 0)")
    parser.add_argument(
        "--schedule-at",
        help="Local datetime for first send, format: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS",
    )
    parser.add_argument("--repeat", type=int, default=1, help="How many rounds to send (default: 1)")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=0,
        help="Interval between rounds in seconds (required when --repeat > 1)",
    )

    parser.add_argument("--proxy-host", help="SOCKS5 proxy host, e.g. 127.0.0.1")
    parser.add_argument("--proxy-port", type=int, help="SOCKS5 proxy port, e.g. 7890")

    parser.add_argument("--list-dialogs", action="store_true", help="List visible dialogs and exit")
    parser.add_argument("--list-limit", type=int, default=200, help="Max dialogs printed with --list-dialogs (default: 200)")
    parser.add_argument("--show-groups", action="store_true", help="Show groups from --target-book and exit")
    return parser.parse_args()


def load_message(args: argparse.Namespace) -> str:
    text = args.message or ""
    if args.message_file:
        path = Path(args.message_file)
        if not path.is_absolute():
            path = BASE_DIR / path
        text = path.read_text(encoding="utf-8").strip()
    return text


def normalize_path_list(paths: Iterable[str]) -> list[Path]:
    out = []
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute():
            p = BASE_DIR / p
        p = p.resolve()
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"attachment not found: {p}")
        out.append(p)
    return out


async def list_dialogs(client: TelegramClient, limit: int) -> None:
    print("visible dialogs:")
    count = 0
    async for dialog in client.iter_dialogs(limit=limit):
        entity = dialog.entity
        username = getattr(entity, "username", None) or ""
        if dialog.is_user:
            chat_type = "user"
        elif dialog.is_group:
            chat_type = "group"
        elif dialog.is_channel:
            chat_type = "channel"
        else:
            chat_type = "other"
        print(f"- id={dialog.id} type={chat_type} name={dialog.name!r} username={username!r}")
        count += 1
    print(f"done. shown={count}")


async def dialogs_snapshot(client: TelegramClient) -> list[tuple[int, str, str, str, object]]:
    rows = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        username = getattr(entity, "username", None) or ""
        if dialog.is_user:
            chat_type = "user"
        elif dialog.is_group:
            chat_type = "group"
        elif dialog.is_channel:
            chat_type = "channel"
        else:
            chat_type = "other"
        rows.append((dialog.id, dialog.name or str(dialog.id), username, chat_type, entity))
    return rows


async def resolve_targets(client: TelegramClient, tokens: list[str], match_mode: str) -> list[ResolvedTarget]:
    if not tokens:
        raise ValueError("no targets provided; use --targets/--targets-file/--target-ids")

    dialogs = await dialogs_snapshot(client)
    resolved: dict[int, ResolvedTarget] = {}

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # explicit numeric id
        if looks_like_chat_id(token):
            entity = await client.get_entity(int(token))
            chat_id = int(getattr(entity, "id", int(token)))
            name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(chat_id)
            username = getattr(entity, "username", None) or ""
            chat_type = "user" if hasattr(entity, "first_name") else "group"
            resolved[chat_id] = ResolvedTarget(chat_id=chat_id, name=name, username=username, chat_type=chat_type, entity=entity)
            continue

        # direct username / t.me ref
        norm = normalize_tme_ref(token)
        if norm.startswith("@") or norm == token or "/" not in norm:
            direct_ref = norm if norm.startswith("@") else f"@{norm}" if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", norm) else None
            if direct_ref:
                try:
                    entity = await client.get_entity(direct_ref)
                    chat_id = int(getattr(entity, "id", 0) or 0)
                    name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(chat_id)
                    username = getattr(entity, "username", None) or ""
                    chat_type = "user" if hasattr(entity, "first_name") else "group"
                    if chat_id:
                        resolved[chat_id] = ResolvedTarget(
                            chat_id=chat_id,
                            name=name,
                            username=username,
                            chat_type=chat_type,
                            entity=entity,
                        )
                        continue
                except Exception:
                    pass

        # match by visible dialog name
        matches = []
        for chat_id, name, username, chat_type, entity in dialogs:
            matched = name == token if match_mode == "exact" else token in name
            if matched:
                matches.append((chat_id, name, username, chat_type, entity))

        if not matches:
            raise ValueError(f"target not found in dialogs: {token!r}")

        for chat_id, name, username, chat_type, entity in matches:
            resolved[chat_id] = ResolvedTarget(
                chat_id=chat_id,
                name=name,
                username=username,
                chat_type=chat_type,
                entity=entity,
            )

    if not resolved:
        raise ValueError("no valid targets resolved")

    return list(resolved.values())


async def send_once(
    client: TelegramClient,
    targets: list[ResolvedTarget],
    text: str,
    files: list[Path],
    images: list[Path],
    round_index: int,
) -> None:
    for target in targets:
        print(f"[round {round_index}] sending to {target.name} (id={target.chat_id}, type={target.chat_type})")

        if text:
            msg = await client.send_message(target.entity, text)
            print(f"  text_sent message_id={msg.id}")

        for file_path in files:
            msg = await client.send_file(target.entity, str(file_path), force_document=True)
            print(f"  file_sent path={file_path.name} message_id={msg.id}")

        for image_path in images:
            msg = await client.send_file(target.entity, str(image_path), force_document=False)
            print(f"  image_sent path={image_path.name} message_id={msg.id}")


async def main() -> None:
    args = parse_args()

    if args.schedule_in < 0:
        raise ValueError("--schedule-in must be >= 0")
    if args.repeat <= 0:
        raise ValueError("--repeat must be > 0")
    if args.repeat > 1 and args.interval_seconds <= 0:
        raise ValueError("--interval-seconds must be > 0 when --repeat > 1")
    if args.schedule_at and args.schedule_in:
        raise ValueError("--schedule-in and --schedule-at are mutually exclusive")

    book_path = resolve_book_path(args.target_book)
    target_book = load_target_book(book_path)
    if args.show_groups:
        print_target_book_groups(book_path, target_book)
        if not args.list_dialogs:
            return

    text = load_message(args)
    files = normalize_path_list(args.files)
    images = normalize_path_list(args.images)

    if not args.list_dialogs and not text and not files and not images:
        raise ValueError("nothing to send; provide --message/--message-file/--file/--image")

    api_id, api_hash = read_api_credentials(KEYS_PATH)
    proxy = ("socks5", args.proxy_host, args.proxy_port) if args.proxy_host and args.proxy_port else None

    async with TelegramClient(SESSION_NAME, api_id, api_hash, proxy=proxy) as client:
        await client.start()
        me = await client.get_me()
        print(f"logged in as: {me.username or me.first_name} (id={me.id})")

        if args.list_dialogs:
            await list_dialogs(client, args.list_limit)
            return

        target_tokens = []
        target_tokens.extend(parse_csv_items(args.targets))
        if args.targets_file:
            file_path = Path(args.targets_file)
            if not file_path.is_absolute():
                file_path = BASE_DIR / file_path
            target_tokens.extend(load_targets_file(file_path))
        target_tokens.extend(parse_csv_items(args.target_ids))
        group_names = parse_csv_items(args.groups)
        for group_name in group_names:
            group_targets = target_book.get("groups", {}).get(group_name)
            if group_targets is None:
                raise ValueError(f"group not found in target book: {group_name!r}")
            print(f"loaded_group={group_name} targets={len(group_targets)}")
            target_tokens.extend(group_targets)

        targets = await resolve_targets(client, target_tokens, args.match_mode)
        print(f"resolved_targets={len(targets)}")
        for t in targets:
            uname = f" @{t.username}" if t.username else ""
            print(f"- {t.name} (id={t.chat_id}, type={t.chat_type}){uname}")

        initial_delay = args.schedule_in
        if args.schedule_at:
            schedule_at = parse_datetime_local(args.schedule_at.replace(" ", "T"))
            now_local = datetime.now().astimezone()
            initial_delay = int((schedule_at - now_local).total_seconds())
            if initial_delay < 0:
                initial_delay = 0

        if initial_delay > 0:
            print(f"waiting {initial_delay}s before first send...")
            await asyncio.sleep(initial_delay)

        for idx in range(1, args.repeat + 1):
            if idx > 1:
                print(f"waiting {args.interval_seconds}s before round {idx}...")
                await asyncio.sleep(args.interval_seconds)
            await send_once(client, targets, text, files, images, idx)

        print("done")


if __name__ == "__main__":
    asyncio.run(main())
