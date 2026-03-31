#!/usr/bin/env python3
"""Search public Telegram chats by keyword with Telethon.

Examples:
  python3 telethon_search_groups_test.py
  python3 telethon_search_groups_test.py --keyword 摄影
  python3 telethon_search_groups_test.py --keyword travel --limit 30 --proxy-host 127.0.0.1 --proxy-port 7890
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from telethon import TelegramClient, functions, types


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


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Telethon keyword search test")
    parser.add_argument("--keyword", default="摄影", help="Search keyword (default: 摄影)")
    parser.add_argument("--limit", type=int, default=20, help="Max results from Telegram (default: 20)")
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

    async with TelegramClient(session_name, api_id, api_hash, proxy=proxy) as client:
        await client.start()
        me = await client.get_me()
        print(f"Logged in as: {me.username or me.first_name} (id={me.id})")

        result = await client(functions.contacts.SearchRequest(q=args.keyword, limit=args.limit))
        print(f"keyword={args.keyword!r} chats={len(result.chats)} users={len(result.users)}")

        for chat in result.chats:
            if isinstance(chat, types.Channel):
                chat_type = "group" if getattr(chat, "megagroup", False) else "channel"
            else:
                chat_type = type(chat).__name__.lower()

            title = getattr(chat, "title", None)
            username = getattr(chat, "username", None)
            print(f"- {chat_type}: title={title!r} username={username!r} id={chat.id}")


if __name__ == "__main__":
    asyncio.run(async_main())
