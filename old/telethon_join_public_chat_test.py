#!/usr/bin/env python3
"""Join a public Telegram group/channel with Telethon.

Examples:
  python3 telethon_join_public_chat_test.py
  python3 telethon_join_public_chat_test.py --target @Python
  python3 telethon_join_public_chat_test.py --target https://t.me/pythontelegrambotgroup
  python3 telethon_join_public_chat_test.py --target "@Seed Photo" --proxy-host 127.0.0.1 --proxy-port 7890
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from telethon import TelegramClient, functions
from telethon.errors import InviteRequestSentError, UserAlreadyParticipantError


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


def normalize_target(target: str) -> str:
    t = target.strip()
    if t.startswith("https://t.me/"):
        t = t[len("https://t.me/") :]
    elif t.startswith("http://t.me/"):
        t = t[len("http://t.me/") :]
    t = t.strip("/")
    if t.startswith("@"):
        t = t[1:]
    return t


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Telethon join public chat test")
    parser.add_argument(
        "--target",
        default="@Python",
        help="Public group/channel username or t.me link (default: @Python)",
    )
    parser.add_argument("--proxy-host", help="SOCKS5 proxy host, e.g. 127.0.0.1")
    parser.add_argument("--proxy-port", type=int, help="SOCKS5 proxy port, e.g. 7890")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    keys_path = base_dir / "keys.txt"
    session_name = str(base_dir / "telethon_test")

    api_id, api_hash = read_api_credentials(keys_path)

    proxy = None
    if args.proxy_host and args.proxy_port:
        proxy = ("socks5", args.proxy_host, args.proxy_port)

    target = normalize_target(args.target)

    async with TelegramClient(session_name, api_id, api_hash, proxy=proxy) as client:
        await client.start()
        me = await client.get_me()
        print(f"Logged in as: {me.username or me.first_name} (id={me.id})")

        try:
            await client(functions.channels.JoinChannelRequest(channel=target))
            entity = await client.get_entity(target)
            title = getattr(entity, "title", None) or getattr(entity, "username", None) or target
            print(f"Join success: {title}")
        except UserAlreadyParticipantError:
            print(f"Already a member of: {target}")
        except InviteRequestSentError:
            print(f"Join request sent and pending approval: {target}")


if __name__ == "__main__":
    asyncio.run(async_main())
