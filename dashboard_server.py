#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import threading
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dashboard_state import load_dashboard_read_state, load_dashboard_state, mark_chat_reports_read

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
STATIC_DIR = BASE_DIR / "dashboard_static"
PIPELINE_SCRIPT_PATH = BASE_DIR / "run_pipeline.sh"
PIPELINE_LOG_PATH = BASE_DIR / "dashboard_pipeline.log"
KEYWORDS_PATH = BASE_DIR / "keywords.txt"
DETECTOR_DESCRIPTION_PATH = BASE_DIR / "detector_description.txt"
ALLOWED_STEPS = {"collect", "analyze", "listen"}
PIPELINE_LOG_TAIL_CHARS = 30000

PIPELINE_LOCK = threading.Lock()
PIPELINE_STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "steps": [],
    "pid": None,
    "exit_code": None,
    "log_path": str(PIPELINE_LOG_PATH),
    "max_joins": None,
}
PIPELINE_PROCESS: subprocess.Popen | None = None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind (default: 8765)")
    return parser.parse_args()


def parse_report_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    head, _, tail = raw.partition("\n\n")
    header = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        header[key.strip()] = value.strip()

    report_body, _, _ = tail.partition("\n\nmessages_json:\n")
    generated_at = header.get("generated_at", "")
    chat_id = int(header.get("chat_id", "0") or 0)
    title = header.get("chat_title", str(chat_id))
    source = header.get("source", "")

    return {
        "report_id": path.name,
        "generated_at": generated_at,
        "chat_id": chat_id,
        "chat_title": title,
        "source": source,
        "body": report_body.strip(),
    }


def build_analyze_groups() -> list[dict]:
    read_state = load_dashboard_read_state()
    last_read_at_by_chat = read_state.get("last_read_at_by_chat", {})

    reports = []
    if REPORTS_DIR.exists():
        for path in sorted(REPORTS_DIR.glob("*.txt")):
            try:
                reports.append(parse_report_file(path))
            except Exception:
                continue

    reports.sort(key=lambda item: item["generated_at"], reverse=True)

    grouped = {}
    for report in reports:
        chat_id = report["chat_id"]
        group = grouped.setdefault(
            chat_id,
            {
                "chat_id": chat_id,
                "title": report["chat_title"],
                "latest_generated_at": report["generated_at"],
                "reports": [],
                "unread_count": 0,
            },
        )
        group["reports"].append(report)
        if report["generated_at"] > group["latest_generated_at"]:
            group["latest_generated_at"] = report["generated_at"]

        last_read_at = last_read_at_by_chat.get(str(chat_id), "")
        if not last_read_at or report["generated_at"] > last_read_at:
            group["unread_count"] += 1

    groups = list(grouped.values())
    groups.sort(key=lambda item: item["latest_generated_at"], reverse=True)
    return groups


def build_dashboard_payload() -> dict:
    dashboard_state = load_dashboard_state()
    collect_groups = list(reversed(dashboard_state.get("collect_groups", [])))
    listen_events = list(reversed(dashboard_state.get("listen_events", [])))
    return {
        "collect_groups": collect_groups,
        "analyze_groups": build_analyze_groups(),
        "listen_events": listen_events,
    }


def read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, text: str):
    normalized = text.rstrip()
    if normalized:
        normalized += "\n"
    path.write_text(normalized, encoding="utf-8")


def extract_default_max_joins() -> int:
    try:
        content = PIPELINE_SCRIPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return 5
    match = re.search(r"^SEARCH_MAX_JOINS=(\d+)\s*$", content, flags=re.MULTILINE)
    if not match:
        return 5
    return int(match.group(1))


def build_startup_config_payload() -> dict:
    return {
        "keywords_text": read_text_file(KEYWORDS_PATH),
        "detector_description_text": read_text_file(DETECTOR_DESCRIPTION_PATH),
        "default_max_joins": extract_default_max_joins(),
        "collect_auto_join_enabled": True,
    }


def refresh_pipeline_state_locked():
    if PIPELINE_PROCESS is not None and PIPELINE_STATE["running"]:
        exit_code = PIPELINE_PROCESS.poll()
        if exit_code is not None:
            PIPELINE_STATE["running"] = False
            PIPELINE_STATE["exit_code"] = exit_code
            PIPELINE_STATE["finished_at"] = datetime.utcnow().isoformat() + "Z"


def get_pipeline_status() -> dict:
    with PIPELINE_LOCK:
        refresh_pipeline_state_locked()
        return dict(PIPELINE_STATE)


def read_pipeline_log() -> str:
    if not PIPELINE_LOG_PATH.exists():
        return ""
    text = PIPELINE_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    if len(text) <= PIPELINE_LOG_TAIL_CHARS:
        return text
    return text[-PIPELINE_LOG_TAIL_CHARS:]


def start_pipeline(steps: list[str], max_joins: int | None = None) -> dict:
    global PIPELINE_PROCESS
    with PIPELINE_LOCK:
        refresh_pipeline_state_locked()
        if PIPELINE_STATE["running"]:
            raise RuntimeError("pipeline is already running")

        PIPELINE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        started_at = datetime.utcnow().isoformat() + "Z"
        PIPELINE_LOG_PATH.write_text(
            f"[dashboard] pipeline started at {started_at}\n"
            f"[dashboard] steps={','.join(steps)}\n\n",
            encoding="utf-8",
        )
        log_file = open(PIPELINE_LOG_PATH, "ab")
        cmd = ["bash", str(PIPELINE_SCRIPT_PATH), "--steps", ",".join(steps)]
        if max_joins is not None:
            cmd.extend(["--max-joins", str(max_joins)])
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        PIPELINE_PROCESS = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )
        PIPELINE_STATE["running"] = True
        PIPELINE_STATE["started_at"] = started_at
        PIPELINE_STATE["finished_at"] = None
        PIPELINE_STATE["steps"] = steps
        PIPELINE_STATE["pid"] = PIPELINE_PROCESS.pid
        PIPELINE_STATE["exit_code"] = None
        PIPELINE_STATE["max_joins"] = max_joins
        return dict(PIPELINE_STATE)


class DashboardHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, static_dir: Path, **kwargs):
        self.static_dir = static_dir
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args):
        return

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel_path: str):
        target = (self.static_dir / rel_path).resolve()
        if not str(target).startswith(str(self.static_dir.resolve())) or not target.exists() or not target.is_file():
            self._send_text("Not found", status=404)
            return
        content = target.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(target))
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_static("index.html")
            return
        if parsed.path == "/app.js":
            self._serve_static("app.js")
            return
        if parsed.path == "/styles.css":
            self._serve_static("styles.css")
            return
        if parsed.path == "/api/dashboard":
            self._send_json(build_dashboard_payload())
            return
        if parsed.path == "/api/pipeline/status":
            self._send_json(get_pipeline_status())
            return
        if parsed.path == "/api/pipeline/log":
            self._send_json({"text": read_pipeline_log()})
            return
        if parsed.path == "/api/config/startup":
            self._send_json(build_startup_config_payload())
            return
        self._send_text("Not found", status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/pipeline/start":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                body = json.loads(raw_body.decode("utf-8"))
                steps = body.get("steps", [])
                max_joins = body.get("max_joins")
                if not isinstance(steps, list) or not steps:
                    self._send_json({"ok": False, "error": "steps required"}, status=400)
                    return
                if max_joins is not None:
                    try:
                        max_joins = int(max_joins)
                    except Exception:
                        self._send_json({"ok": False, "error": "max_joins must be an integer"}, status=400)
                        return
                    if max_joins < 0:
                        self._send_json({"ok": False, "error": "max_joins must be >= 0"}, status=400)
                        return
                normalized_steps = []
                for step in steps:
                    if step not in ALLOWED_STEPS:
                        self._send_json({"ok": False, "error": f"invalid step: {step}"}, status=400)
                        return
                    if step not in normalized_steps:
                        normalized_steps.append(step)
                status_payload = start_pipeline(normalized_steps, max_joins=max_joins)
                self._send_json({"ok": True, "status": status_payload})
                return
            except RuntimeError as e:
                self._send_json({"ok": False, "error": str(e)}, status=409)
                return
            except Exception as e:
                self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)
                return
        if parsed.path.startswith("/api/groups/") and parsed.path.endswith("/read"):
            parts = parsed.path.strip("/").split("/")
            try:
                chat_id = int(parts[2])
            except Exception:
                self._send_json({"ok": False, "error": "invalid chat id"}, status=400)
                return
            mark_chat_reports_read(chat_id)
            self._send_json({"ok": True, "chat_id": chat_id})
            return
        if parsed.path == "/api/config/startup":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                body = json.loads(raw_body.decode("utf-8"))
                keywords_text = body.get("keywords_text")
                detector_description_text = body.get("detector_description_text")
                if not isinstance(keywords_text, str) or not isinstance(detector_description_text, str):
                    self._send_json({"ok": False, "error": "keywords_text and detector_description_text are required"}, status=400)
                    return
                write_text_file(KEYWORDS_PATH, keywords_text)
                write_text_file(DETECTOR_DESCRIPTION_PATH, detector_description_text)
                self._send_json({"ok": True, "config": build_startup_config_payload()})
                return
            except Exception as e:
                self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)
                return
        self._send_text("Not found", status=404)


def main():
    args = parse_args()
    handler_cls = partial(DashboardHandler, static_dir=STATIC_DIR)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(f"Dashboard server running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
