#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default configuration for Python scripts.
SEARCH_LIMIT=20
SEARCH_RECURSIVE=1
SEARCH_MAX_DEPTH=2
SEARCH_MAX_GROUPS=100
SEARCH_MAX_JOINS=5

ANALYZE_HISTORY_LIMIT=200
ANALYZE_MAX_GROUPS=-1

CONTINUE_LISTEN=0
ALLOW_TALK=0
STEPS="collect,analyze"

has_step() {
  local target="$1"
  local normalized=",${STEPS},"
  [[ "$normalized" == *",$target,"* ]]
}

print_help() {
  cat <<'EOF'
Usage:
  bash run_pipeline.sh [--steps collect,analyze] [--history-limit 200] [--max-joins 5] [--continue-listen] [--allow-talk]

Options:
  --steps STEPS       Comma-separated steps: collect, analyze, listen
  --history-limit N   Override analyze history limit
  --max-joins N       Override maximum newly joined groups in collect step
  --continue-listen   After collect/join/analyze, continue running telethon_talk.py
  --allow-talk        Only meaningful with --continue-listen; allow telethon_talk.py to send replies
  -h, --help          Show this help message

Default behavior:
  1. Search public groups
  2. Join groups and sync ids to listen_targets.json
  3. Analyze listened group history with Qwen
  4. Stop

If --continue-listen is passed:
  5. Continue into telethon_talk.py

By default talking is disabled.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --steps)
      if [[ $# -lt 2 ]]; then
        echo "--steps requires a value" >&2
        exit 1
      fi
      STEPS="${2// /}"
      shift 2
      ;;
    --history-limit)
      if [[ $# -lt 2 ]]; then
        echo "--history-limit requires a value" >&2
        exit 1
      fi
      ANALYZE_HISTORY_LIMIT="$2"
      shift 2
      ;;
    --max-joins)
      if [[ $# -lt 2 ]]; then
        echo "--max-joins requires a value" >&2
        exit 1
      fi
      SEARCH_MAX_JOINS="$2"
      shift 2
      ;;
    --continue-listen)
      CONTINUE_LISTEN=1
      shift
      ;;
    --allow-talk)
      ALLOW_TALK=1
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_help
      exit 1
      ;;
  esac
done

if [[ "$CONTINUE_LISTEN" == "1" ]] && ! has_step "listen"; then
  if [[ -z "$STEPS" ]]; then
    STEPS="listen"
  else
    STEPS="${STEPS},listen"
  fi
fi

for step in ${STEPS//,/ }; do
  case "$step" in
    collect|analyze|listen)
      ;;
    *)
      echo "Unknown step: $step" >&2
      print_help
      exit 1
      ;;
  esac
done

if has_step "collect"; then
  echo "== Step: collect =="
  SEARCH_CMD=(
    python3 telethon_search_and_join_groups.py
    --search-limit "$SEARCH_LIMIT"
    --max-groups "$SEARCH_MAX_GROUPS"
    --max-joins "$SEARCH_MAX_JOINS"
    --add-to-listen-targets
  )

  if [[ "$SEARCH_RECURSIVE" == "1" ]]; then
    SEARCH_CMD+=(--recursive --max-depth "$SEARCH_MAX_DEPTH")
  fi

  "${SEARCH_CMD[@]}"
  echo
fi

if has_step "analyze"; then
  echo "== Step: analyze =="
  python3 telethon_analyze_listen_targets.py \
    --history-limit "$ANALYZE_HISTORY_LIMIT" \
    --max-groups "$ANALYZE_MAX_GROUPS"
  echo
fi

if ! has_step "listen"; then
  echo "== Pipeline complete =="
  echo "Realtime listening was not requested."
  exit 0
fi

echo "== Step: listen =="
echo "Allow talk: $ALLOW_TALK"

TELETHON_TALK_ENABLE_REPLY="$ALLOW_TALK" python3 telethon_talk.py
