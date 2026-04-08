import argparse
import asyncio
import json
import os
from collections import deque
from pathlib import Path

from openai import OpenAI
from telethon import TelegramClient, events

from dashboard_state import append_listen_event, utc_now_iso
from reporting_utils import (
    generate_detection_report,
    load_detector_description,
    read_qwen_key,
    write_report_file,
)

# ==========================================
# 1. Telegram 用户号配置区（Telethon）
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
KEYS_PATH = BASE_DIR / "keys.txt"
BOT_KEY_PATH = BASE_DIR / "bot_key.txt"
MONITOR_TARGETS_PATH = BASE_DIR / "listen_targets.json"
DETECTOR_DESCRIPTION_PATH = BASE_DIR / "detector_description.txt"
REPORTS_DIR = BASE_DIR / "reports"
SESSION_NAME = str(BASE_DIR / "telethon_user_session")

# 默认走本地代理（可通过环境变量覆盖）
# TELEGRAM_PROXY_HOST=127.0.0.1
# TELEGRAM_PROXY_PORT=7890
PROXY_HOST = os.getenv("TELEGRAM_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("TELEGRAM_PROXY_PORT", "7890"))
USE_PROXY = os.getenv("TELEGRAM_USE_PROXY", "1") != "0"
# 群聊监听默认开启，但只会处理配置文件中显式列出的群组
ENABLE_GROUPS = os.getenv("TELEGRAM_ENABLE_GROUPS", "1") == "1"
ENABLE_REPLY = os.getenv("TELETHON_TALK_ENABLE_REPLY", "0") == "1"

# 群聊批处理参数
GROUP_PROCESS_INTERVAL_SECONDS = 5
GROUP_BUFFER_MAX_MESSAGES = 8
GROUP_TRIGGER_NAMES = tuple(
    x.strip() for x in os.getenv("TELEGRAM_GROUP_TRIGGER_NAMES", "李").split(",") if x.strip()
)


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
        raise ValueError("keys.txt 缺少 api_id 或 api_hash")

    return api_id, api_hash


def load_monitor_targets(path: Path) -> dict[str, set[int]]:
    if not path.exists():
        return {"private_chat_ids": set(), "group_chat_ids": set()}

    data = json.loads(path.read_text(encoding="utf-8"))

    def normalize_group_chat_id(value: int) -> int:
        if value > 0:
            return int(f"-100{value}")
        return value

    def parse_id_list(field_name: str) -> set[int]:
        raw_values = data.get(field_name, [])
        if not isinstance(raw_values, list):
            raise ValueError(f"{field_name} 必须是数组")
        parsed_values = set()
        for value in raw_values:
            parsed_value = int(value)
            if field_name == "group_chat_ids":
                parsed_value = normalize_group_chat_id(parsed_value)
            parsed_values.add(parsed_value)
        return parsed_values

    return {
        "private_chat_ids": parse_id_list("private_chat_ids"),
        "group_chat_ids": parse_id_list("group_chat_ids"),
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list_all_dialogs",
        action="store_true",
        help="列出当前账号可见的联系人和群组，然后直接退出",
    )
    return parser.parse_args()


# ==========================================
# 2. Qwen3 大脑配置区
# ==========================================
BASE_URL = "https://coding.dashscope.aliyuncs.com/v1"
MODEL = "qwen3.5-plus"

QWEN_API_KEY = read_qwen_key(BOT_KEY_PATH)
DETECTOR_DESCRIPTION = load_detector_description(DETECTOR_DESCRIPTION_PATH)
client_ai = OpenAI(api_key=QWEN_API_KEY, base_url=BASE_URL)

# ==========================================
# 3. 工具与状态管理
# ==========================================


def pass_reply():
    return "成功跳过本次回答"


available_tools = {
    "pass_reply": pass_reply,
}

tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "pass_reply",
            "description": "跳过本次回答",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# 用于存储不同用户的独立对话历史
user_sessions = {}
monitor_targets = load_monitor_targets(MONITOR_TARGETS_PATH)
group_message_buffers = {}
group_buffer_lock = asyncio.Lock()


def get_user_messages(chat_id):
    """获取或初始化用户的对话历史"""
    if chat_id not in user_sessions:
        user_sessions[chat_id] = [
            {
                "role": "system",
                "content": "你是李，说话像一个普通、友善、正在上班的人。你的表达要自然、口语化、简洁，不要太像客服，也不要像百科词条；少一点套话，少一点完美答案，多一点真实聊天的感觉。你可以适当使用日常口吻，比如“我这边看下来”“稍等我想一下”“这个大概是这样”，但不要故意演得夸张。在一对一私聊中，你应该正常直接回答对方；在群聊中，只有别人明确在叫你，或者话题明显是在问你时你才回答，否则使用pass_reply工具跳过本次回答。回复时尽量像真人聊天，优先直接回应重点，不要每次都长篇大论，也不要机械重复对方的话。",
            }
        ]
    return user_sessions[chat_id]


def trim_session_messages(chat_id):
    messages = user_sessions[chat_id]
    if len(messages) > 11:
        user_sessions[chat_id] = [messages[0]] + messages[-10:]
    return user_sessions[chat_id]


def is_monitored_private_chat(chat_id: int) -> bool:
    return chat_id in monitor_targets["private_chat_ids"]


def is_monitored_group_chat(chat_id: int) -> bool:
    return chat_id in monitor_targets["group_chat_ids"]


def should_reply_to_group(batch_text: str) -> bool:
    return any(trigger_name in batch_text for trigger_name in GROUP_TRIGGER_NAMES)


def log_incoming_message(chat_type: str, chat_id: int, text: str):
    preview = text.strip().replace("\n", " ")
    if len(preview) > 80:
        preview = preview[:77] + "..."
    print(f"[incoming][{chat_type}] chat_id={chat_id} text={preview}")
    append_listen_event(
        {
            "timestamp": utc_now_iso(),
            "event_type": "incoming",
            "chat_type": chat_type,
            "chat_id": chat_id,
            "text": preview,
        }
    )


def render_group_rows_for_prompt(message_rows: list[dict]) -> str:
    return "\n".join(f"{row['sender']}: {row['text']}" for row in message_rows if row.get("text"))


async def analyze_and_write_group_report(chat_id: int, message_rows: list[dict], source_label: str):
    try:
        entity = await tg_client.get_entity(chat_id)
        chat_title = getattr(entity, "title", None) or str(chat_id)
        report_text = await asyncio.to_thread(
            generate_detection_report,
            client_ai,
            MODEL,
            DETECTOR_DESCRIPTION,
            chat_title,
            chat_id,
            source_label,
            message_rows,
        )
        if not report_text:
            return

        report_path = write_report_file(
            REPORTS_DIR,
            chat_title,
            chat_id,
            source_label,
            report_text,
            message_rows,
        )
        print(f"report_written {report_path}")
        append_listen_event(
            {
                "timestamp": utc_now_iso(),
                "event_type": "report_written",
                "chat_type": "group",
                "chat_id": chat_id,
                "text": f"report_written {report_path.name}",
            }
        )
    except Exception as e:
        print(f"report_error {chat_id} {type(e).__name__}: {e}")
        append_listen_event(
            {
                "timestamp": utc_now_iso(),
                "event_type": "report_error",
                "chat_type": "group",
                "chat_id": chat_id,
                "text": f"{type(e).__name__}: {e}",
            }
        )


async def run_ai_turn(chat_id: int, user_content: str, reply_callback):
    messages = get_user_messages(chat_id)
    messages.append({"role": "user", "content": user_content})
    messages = trim_session_messages(chat_id)

    try:
        response = client_ai.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools_definition,
            max_tokens=10000,
        )
        response_message = response.choices[0].message

        if response_message.tool_calls:
            messages.append(response_message)
            skip_reply = False

            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments or "{}")

                if function_name == "pass_reply":
                    skip_reply = True

                print(f"{function_name} {function_args}")

                if function_name in available_tools:
                    function_to_call = available_tools[function_name]
                    tool_result = function_to_call(**function_args)
                else:
                    tool_result = f"错误：找不到名为 {function_name} 的工具。"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": str(tool_result),
                    }
                )

            if not skip_reply:
                second_response = client_ai.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_tokens=10000,
                )
                final_reply = second_response.choices[0].message.content or ""
                messages.append({"role": "assistant", "content": final_reply})
                if final_reply.strip():
                    await reply_callback(final_reply)
        else:
            reply = response_message.content or ""
            messages.append({"role": "assistant", "content": reply})
            if reply.strip():
                await reply_callback(reply)

    except Exception as e:
        print(f"出错了: {e}")


async def enqueue_group_message(event, user_text: str):
    sender = await event.get_sender()
    sender_name = (
        getattr(sender, "first_name", None)
        or getattr(sender, "username", None)
        or str(event.sender_id)
    )
    chat_id = event.chat_id
    message_row = {
        "message_id": event.id,
        "date": event.date.isoformat() if event.date else None,
        "sender": sender_name,
        "text": user_text,
    }

    async with group_buffer_lock:
        buffer = group_message_buffers.setdefault(chat_id, deque(maxlen=GROUP_BUFFER_MAX_MESSAGES))
        buffer.append(message_row)


async def process_group_batch(chat_id: int, batched_messages: list[dict]):
    if not batched_messages:
        return

    await analyze_and_write_group_report(chat_id, batched_messages, "realtime_group_batch")
    if not ENABLE_REPLY:
        return

    batch_text = render_group_rows_for_prompt(batched_messages)
    if not should_reply_to_group(batch_text):
        return

    prompt = (
        "以下是过去几秒内同一个群聊里收到的多条消息，请合并上下文后最多回复一次。"
        "如果大家没有在叫你，或者没有必要回应，可以调用 pass_reply。\n\n"
        f"{batch_text}"
    )

    async def send_group_reply(text: str):
        await tg_client.send_message(chat_id, text)

    await run_ai_turn(chat_id, prompt, send_group_reply)


async def process_group_buffers_loop():
    while True:
        await asyncio.sleep(GROUP_PROCESS_INTERVAL_SECONDS)

        ready_batches = []
        async with group_buffer_lock:
            for chat_id, buffer in group_message_buffers.items():
                if not buffer:
                    continue
                ready_batches.append((chat_id, list(buffer)))
                buffer.clear()

        for chat_id, batched_messages in ready_batches:
            await process_group_batch(chat_id, batched_messages)


async def list_all_dialogs():
    print("开始列出当前账号可见的联系人和群组：")
    async for dialog in tg_client.iter_dialogs():
        entity = dialog.entity
        entity_id = getattr(entity, "id", None)
        title = dialog.name or getattr(entity, "title", None) or getattr(entity, "first_name", None) or ""

        if dialog.is_user:
            username = getattr(entity, "username", None)
            username_text = f", username={username}" if username else ""
            print(f"[私聊] id={entity_id}, name={title}{username_text}")
        elif dialog.is_group or dialog.is_channel:
            print(f"[群组] id={dialog.id}, name={title}")


# ==========================================
# 4. 核心逻辑：监听与回复（Telethon）
# ==========================================
api_id, api_hash = read_api_credentials(KEYS_PATH)
proxy = ("socks5", PROXY_HOST, PROXY_PORT) if USE_PROXY else None
tg_client = TelegramClient(SESSION_NAME, api_id, api_hash, proxy=proxy)


@tg_client.on(events.NewMessage(incoming=True))
async def chat_with_qwen(event):
    chat_id = event.chat_id
    user_text = event.raw_text or ""
    if not user_text.strip():
        return

    if event.is_private:
        if not is_monitored_private_chat(chat_id):
            return
        log_incoming_message("private", chat_id, user_text)
        if not ENABLE_REPLY:
            return
        await run_ai_turn(chat_id, user_text, event.reply)
        return

    if ENABLE_GROUPS and event.is_group and is_monitored_group_chat(chat_id):
        log_incoming_message("group", chat_id, user_text)
        await enqueue_group_message(event, user_text)


# ==========================================
# 5. 启动用户号
# ==========================================
async def main():
    args = parse_args()
    await tg_client.start()
    me = await tg_client.get_me()
    if args.list_all_dialogs:
        print(f"Telethon 用户号已登录：{me.first_name} (id={me.id})")
        await list_all_dialogs()
        await tg_client.disconnect()
        return

    buffer_task = asyncio.create_task(process_group_buffers_loop())
    print(f"Telethon 用户号 AI 已启动：{me.first_name} (id={me.id})")
    print("等待接收配置中的私聊/群聊消息中...")
    print(f"发言开关：{'开启' if ENABLE_REPLY else '关闭'}")
    try:
        await tg_client.run_until_disconnected()
    finally:
        buffer_task.cancel()
        await asyncio.gather(buffer_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
