#!/usr/bin/env python3
"""Analyze listened Telegram groups with Qwen and write matched reports."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from openai import OpenAI
from telethon import TelegramClient

from reporting_utils import (
    generate_detection_report,
    load_detector_description,
    read_qwen_key,
    write_report_file,
)

BASE_DIR = Path(__file__).resolve().parent
KEYS_PATH = BASE_DIR / "keys.txt"
BOT_KEY_PATH = BASE_DIR / "bot_key.txt"
LISTEN_TARGETS_PATH = BASE_DIR / "listen_targets.json"
DETECTOR_DESCRIPTION_PATH = BASE_DIR / "detector_description.txt"
REPORTS_DIR = BASE_DIR / "reports"
SESSION_NAME = str(BASE_DIR / "telethon_user_session")

PROXY_HOST = os.getenv("TELEGRAM_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("TELEGRAM_PROXY_PORT", "7890"))
USE_PROXY = os.getenv("TELEGRAM_USE_PROXY", "1") != "0"

BASE_URL = "https://coding.dashscope.aliyuncs.com/v1"
MODEL = "qwen3.5-plus"


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


def load_listen_targets(path: Path) -> list[int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    group_chat_ids = data.get("group_chat_ids", [])
    if not isinstance(group_chat_ids, list):
        raise ValueError("listen_targets.json group_chat_ids must be an array")
    normalized_ids = []
    for value in group_chat_ids:
        parsed = int(value)
        if parsed > 0:
            parsed = int(f"-100{parsed}")
        normalized_ids.append(parsed)
    return normalized_ids


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history-limit",
        type=int,
        default=200,
        help="How many recent messages to analyze per group; use 0 for all visible history (default: 200)",
    )
    parser.add_argument(
        "--max-groups",
        type=int,
        default=-1,
        help="Maximum number of listened groups to analyze; -1 means unlimited (default: -1)",
    )
    return parser.parse_args()


def render_progress(current: int, total: int, width: int = 30) -> str:
    if total <= 0:
        return "[no targets]"
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {current}/{total}"


async def collect_group_history(client: TelegramClient, chat_id: int, history_limit: int) -> tuple[str, list[dict]]:
    entity = await client.get_entity(chat_id)
    chat_title = getattr(entity, "title", None) or str(chat_id)
    rows = []
    iter_limit = None if history_limit <= 0 else history_limit

    async for message in client.iter_messages(entity, limit=iter_limit):
        text = (message.message or "").strip()
        if not text:
            continue
        rows.append(
            {
                "message_id": message.id,
                "date": message.date.isoformat() if message.date else None,
                "sender": str(message.sender_id),
                "text": text,
            }
        )

    rows.reverse()
    return chat_title, rows


async def main():
    args = parse_args()
    api_id, api_hash = read_api_credentials(KEYS_PATH)
    qwen_key = read_qwen_key(BOT_KEY_PATH)
    detector_description = load_detector_description(DETECTOR_DESCRIPTION_PATH)
    group_chat_ids = load_listen_targets(LISTEN_TARGETS_PATH)
    client_ai = OpenAI(api_key=qwen_key, base_url=BASE_URL)

    proxy = ("socks5", PROXY_HOST, PROXY_PORT) if USE_PROXY else None

    analyzed_count = 0
    report_count = 0
    total_targets = len(group_chat_ids) if args.max_groups < 0 else min(len(group_chat_ids), args.max_groups)

    async with TelegramClient(SESSION_NAME, api_id, api_hash, proxy=proxy) as client:
        await client.start()
        me = await client.get_me()
        print(f"Logged in as: {me.username or me.first_name} (id={me.id})")
        print(f"Analyzing {len(group_chat_ids)} listened group(s)")

        for index, chat_id in enumerate(group_chat_ids, start=1):
            if args.max_groups >= 0 and analyzed_count >= args.max_groups:
                break

            try:
                print(f"{render_progress(min(index, total_targets), total_targets)} current_chat_id={chat_id}")
                chat_title, rows = await collect_group_history(client, chat_id, args.history_limit)
                analyzed_count += 1
                print(f"Analyzing group: {chat_title} ({chat_id}), messages={len(rows)}")

                report_text = await asyncio.to_thread(
                    generate_detection_report,
                    client_ai,
                    MODEL,
                    detector_description,
                    chat_title,
                    chat_id,
                    "history_scan",
                    rows,
                )
                if not report_text:
                    print("No relevant content found.")
                    continue

                report_path = write_report_file(
                    REPORTS_DIR,
                    chat_title,
                    chat_id,
                    "history_scan",
                    report_text,
                    rows,
                )
                report_count += 1
                print(f"Report written: {report_path}")
            except Exception as e:
                print(f"Failed to analyze group {chat_id}: {type(e).__name__}: {e}")

    if total_targets > 0:
        print(render_progress(min(analyzed_count, total_targets), total_targets))
    print(f"Done. analyzed_groups={analyzed_count}, reports_written={report_count}")


if __name__ == "__main__":
    asyncio.run(main())
