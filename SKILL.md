---
name: telegram-agent-ops
description: Use this skill when the user wants an all-in-one Telegram operations agent flow in this repo: discover groups, analyze reports, listen in realtime, and especially perform one-shot/batch sends by interacting with the agent and using target groups stored in a JSON target book.
---

# telegram-agent-ops

## Purpose

This skill standardizes how to operate this repository as an all-in-one agent using CLI tools.

Primary goals:

1. Keep every operation scriptable and CLI-first.
2. Support interactive user intent -> deterministic command execution.
3. Enable "one sentence send" by mapping user categories to JSON-defined target groups.

## When To Use

Use this skill when the user asks to:

- run collect/analyze/listen workflows,
- send text/files/images to contacts or groups,
- schedule sends,
- send to multiple targets by category/group,
- orchestrate this project as one unified agent workflow.

## Canonical Tools In This Repo

- `bash run_pipeline.sh`
- `python3 telethon_search_and_join_groups.py`
- `python3 telethon_analyze_listen_targets.py`
- `python3 telethon_talk.py`
- `python3 dashboard_server.py`
- `python3 telethon_send_cli.py`

For full parameter reference, read:

- `CLI_SCRIPTS.md`

## Batch Send Model (Core)

### Target Book

Use `send_target_groups.json` as the source of truth for categorized targets.

Path:

- `send_target_groups.json`

Format:

```json
{
  "groups": {
    "group_name": [
      "传 李",
      "@some_username",
      "-1001234567890"
    ]
  }
}
```

Rules:

1. Group names are stable identifiers used by the agent.
2. Group values are target tokens supported by `telethon_send_cli.py`.
3. Keep tokens human-readable where possible (display names or usernames).
4. Use chat IDs for strict routing when needed.

### One-Sentence Send Workflow

When user intent is like:

- "给测试组发一句话..."
- "给 ops_daily 发图并延迟 10 分钟"

Agent should:

1. Parse send intent: content, attachments, schedule, groups.
2. Resolve groups from `send_target_groups.json`.
3. Build one deterministic `telethon_send_cli.py` command.
4. Execute and report target resolution + message IDs.

Use `--groups` with `--target-book`:

```bash
python3 telethon_send_cli.py \
  --groups ops_daily \
  --target-book send_target_groups.json \
  --message "daily update" \
  --schedule-in 600
```

## Recommended Interaction Contract

When user asks to send, the agent should confirm only missing essentials.

Minimum required fields for send action:

1. target scope (`--groups` or direct targets)
2. payload (text/file/image)

Optional fields:

1. first-run schedule (`--schedule-in` or `--schedule-at`)
2. repeat (`--repeat` + `--interval-seconds`)
3. matching behavior (`--match-mode`)

If user provides a category but no such group exists in target book, agent should:

1. show existing groups,
2. ask to map category -> group,
3. or append a new group into `send_target_groups.json` then run.

## Group Management Pattern

For persistent operations, keep categories in `send_target_groups.json`.

Typical categories:

- `core_contacts`
- `test_groups`
- `ops_daily`
- `risk_watch`
- `broadcast_all`

Agent may edit `send_target_groups.json` directly when user requests:

- "把 A 和 B 加到 ops_daily"
- "新建一个 marketing_test 组"

After editing, agent should validate with:

```bash
python3 telethon_send_cli.py --show-groups
```

## Safety Defaults

1. Prefer dry visibility before bulk send:

```bash
python3 telethon_send_cli.py --show-groups
python3 telethon_send_cli.py --list-dialogs --list-limit 100
```

2. For first run on a new group, start with a short test message.
3. For repeated sends, require explicit `--repeat` and `--interval-seconds`.
4. Never assume missing attachments; fail fast if file path is invalid.

## Common Command Templates

### Send text to one group category

```bash
python3 telethon_send_cli.py \
  --groups ops_daily \
  --target-book send_target_groups.json \
  --message "hello"
```

### Send image + file to multiple categories with delay

```bash
python3 telethon_send_cli.py \
  --groups ops_daily,test_groups \
  --target-book send_target_groups.json \
  --message "materials attached" \
  --file candidate_links.txt \
  --image image.png \
  --schedule-in 300
```

### Repeated heartbeat send

```bash
python3 telethon_send_cli.py \
  --groups core_contacts \
  --target-book send_target_groups.json \
  --message "heartbeat" \
  --repeat 5 \
  --interval-seconds 60
```

## Integration With All-In-One Agent

Suggested internal routing:

1. Discovery task -> `telethon_search_and_join_groups.py`
2. Historical analysis -> `telethon_analyze_listen_targets.py`
3. Realtime monitoring -> `telethon_talk.py` / `run_pipeline.sh --steps listen`
4. Outbound messaging -> `telethon_send_cli.py` + `send_target_groups.json`
5. Human supervision -> `dashboard_server.py`

This skill should keep outbound sending category-driven so users can complete complex sends with one natural-language sentence once categories are configured.
