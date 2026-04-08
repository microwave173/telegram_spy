from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_STATE_PATH = BASE_DIR / "dashboard_state.json"
DASHBOARD_READ_STATE_PATH = BASE_DIR / "dashboard_read_state.json"
HIT_COUNT_BACKUPS_DIR = BASE_DIR / "hit_count_backups"
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
            "group_hit_counts": {},
            "hit_counts_seeded": False,
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


def clear_listen_events() -> None:
    state = load_dashboard_state()
    state["listen_events"] = []
    save_dashboard_state(state)


def increment_group_hit_count(chat_id: int, chat_title: str) -> None:
    state = load_dashboard_state()
    mapping = state.get("group_hit_counts", {})
    key = str(chat_id)
    entry = mapping.get(key, {})
    count = int(entry.get("count", 0) or 0) + 1
    mapping[key] = {
        "chat_id": chat_id,
        "title": chat_title,
        "count": count,
        "last_hit_at": utc_now_iso(),
    }
    state["group_hit_counts"] = mapping
    save_dashboard_state(state)


def reset_group_hit_counts_with_backup() -> dict:
    state = load_dashboard_state()
    mapping = state.get("group_hit_counts", {})
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    HIT_COUNT_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = HIT_COUNT_BACKUPS_DIR / f"group_hit_counts_{timestamp}.json"
    backup_payload = {
        "reset_at": utc_now_iso(),
        "group_hit_counts": mapping,
    }
    backup_path.write_text(json.dumps(backup_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    state["group_hit_counts"] = {}
    state["hit_counts_seeded"] = True
    save_dashboard_state(state)
    return {"backup_path": str(backup_path), "backed_up_groups": len(mapping)}


def seed_group_hit_counts_from_reports(reports: list[dict]) -> None:
    state = load_dashboard_state()
    if state.get("hit_counts_seeded"):
        return
    if state.get("group_hit_counts"):
        state["hit_counts_seeded"] = True
        save_dashboard_state(state)
        return

    mapping = {}
    for report in reports:
        chat_id = int(report.get("chat_id", 0) or 0)
        if not chat_id:
            continue
        key = str(chat_id)
        entry = mapping.get(
            key,
            {
                "chat_id": chat_id,
                "title": report.get("chat_title") or str(chat_id),
                "count": 0,
                "last_hit_at": report.get("generated_at", ""),
            },
        )
        entry["count"] += 1
        if report.get("generated_at", "") > entry.get("last_hit_at", ""):
            entry["last_hit_at"] = report.get("generated_at", "")
        mapping[key] = entry

    state["group_hit_counts"] = mapping
    state["hit_counts_seeded"] = True
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
