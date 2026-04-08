from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from dashboard_state import increment_group_hit_count

NO_MATCH_SENTINEL = "NO_MATCH"


def read_qwen_key(path: Path) -> str:
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not lines:
        raise ValueError("bot_key.txt is empty")
    return lines[-1]


def load_detector_description(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"detector description file not found: {path}")
    description = path.read_text(encoding="utf-8").strip()
    if not description:
        raise ValueError(f"detector description file is empty: {path}")
    return description


def ensure_reports_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", name.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "chat"


def format_messages_for_prompt(message_rows: list[dict]) -> str:
    lines = []
    for row in message_rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        lines.append(
            f"[msg_id={row.get('message_id')}][date={row.get('date')}][sender={row.get('sender')}] {text}"
        )
    return "\n".join(lines)


def generate_detection_report(
    client_ai,
    model: str,
    detector_description: str,
    chat_title: str,
    chat_id: int,
    source_label: str,
    message_rows: list[dict],
) -> str | None:
    rendered_messages = format_messages_for_prompt(message_rows)
    if not rendered_messages:
        return None

    response = client_ai.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个内容分析与报告助手。"
                    "你会根据给定的检测描述，判断输入消息里是否存在明显相关内容。"
                    f"如果没有相关内容，只返回 {NO_MATCH_SENTINEL}。"
                    "如果存在相关内容，输出一份中文报告。"
                    "必须严格基于输入消息，不要猜测，不要补充输入里没有出现的事实。"
                    "摘抄部分尽量保持原文。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"检测描述：\n{detector_description}\n\n"
                    f"聊天名称：{chat_title}\n"
                    f"聊天ID：{chat_id}\n"
                    f"来源：{source_label}\n\n"
                    "请阅读下面这些消息。如果存在与检测描述明显相关的内容，"
                    "请按下面格式输出：\n"
                    "命中概述：\n"
                    "- ...\n"
                    "相关摘抄：\n"
                    "- [msg_id=...][date=...][sender=...] 原文摘抄\n"
                    "判断理由：\n"
                    "- ...\n\n"
                    f"如果没有相关内容，只返回 {NO_MATCH_SENTINEL}。\n\n"
                    f"消息如下：\n{rendered_messages}"
                ),
            },
        ],
        max_tokens=2000,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content or content == NO_MATCH_SENTINEL:
        return None
    return content


def build_report_header(chat_title: str, chat_id: int, source_label: str) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    return (
        f"generated_at: {generated_at}\n"
        f"chat_title: {chat_title}\n"
        f"chat_id: {chat_id}\n"
        f"source: {source_label}\n"
    )


def write_report_file(
    reports_dir: Path,
    chat_title: str,
    chat_id: int,
    source_label: str,
    report_text: str,
    message_rows: list[dict],
) -> Path:
    ensure_reports_dir(reports_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_title = sanitize_filename(chat_title)
    report_path = reports_dir / f"{timestamp}_{chat_id}_{safe_title}.txt"
    body = (
        build_report_header(chat_title, chat_id, source_label)
        + "\n"
        + report_text.strip()
        + "\n\nmessages_json:\n"
        + json.dumps(message_rows, ensure_ascii=False, indent=2)
        + "\n"
    )
    report_path.write_text(body, encoding="utf-8")
    increment_group_hit_count(chat_id, chat_title)
    return report_path
