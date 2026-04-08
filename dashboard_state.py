from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_STATE_PATH = BASE_DIR / "dashboard_state.json"
DASHBOARD_READ_STATE_PATH = BASE_DIR / "dashboard_read_state.json"
MAX_LISTEN_EVENTS = 300
MAX_COLLECT_GROUPS = 300


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default.copy()
        merged = default.copy()
        merged.update(data)
        return merged
    except Exception:
        return default.copy()


def load_dashboard_state() -> dict:
    return _load_json(
        DASHBOARD_STATE_PATH,
        {
            "collect_groups": [],
            "listen_events": [],
        },
    )


def save_dashboard_state(state: dict) -> None:
    DASHBOARD_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_collect_group(entry: dict) -> None:
    state = load_dashboard_state()
    groups = state.get("collect_groups", [])
    groups.append(entry)
    state["collect_groups"] = groups[-MAX_COLLECT_GROUPS:]
    save_dashboard_state(state)


def append_listen_event(entry: dict) -> None:
    state = load_dashboard_state()
    events = state.get("listen_events", [])
    events.append(entry)
    state["listen_events"] = events[-MAX_LISTEN_EVENTS:]
    save_dashboard_state(state)


def load_dashboard_read_state() -> dict:
    return _load_json(
        DASHBOARD_READ_STATE_PATH,
        {
            "last_read_at_by_chat": {},
        },
    )


def save_dashboard_read_state(state: dict) -> None:
    DASHBOARD_READ_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_chat_reports_read(chat_id: int) -> None:
    state = load_dashboard_read_state()
    mapping = state.get("last_read_at_by_chat", {})
    mapping[str(chat_id)] = utc_now_iso()
    state["last_read_at_by_chat"] = mapping
    save_dashboard_read_state(state)
