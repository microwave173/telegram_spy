# telegram_bot CLI 脚本总览

这份文档用于给后续 all-in-one agent 统一调用本项目脚本。

建议运行目录：`/Users/mabokai/Desktop/proj/telegram_bot`

## 0. 通用前置

需要准备：

- `keys.txt`（`api_id` + `api_hash`）
- `bot_key.txt`（Qwen key）
- `telethon_user_session.session`（首次登录后生成）

建议依赖：

```bash
pip install telethon openai
```

可选代理环境变量（多数脚本可用）：

```bash
TELEGRAM_PROXY_HOST=127.0.0.1
TELEGRAM_PROXY_PORT=7890
TELEGRAM_USE_PROXY=1
```

---

## 1) `run_pipeline.sh`

用途：一条命令串联 `collect / analyze / listen`。

### 命令

```bash
bash run_pipeline.sh [--steps collect,analyze,listen] [--history-limit N] [--max-joins N] [--continue-listen] [--allow-talk]
```

### 关键参数

- `--steps`：逗号分隔步骤，支持 `collect,analyze,listen`
- `--history-limit`：覆盖 analyze 历史条数
- `--max-joins`：覆盖 collect 最大加群数
- `--continue-listen`：跑完后继续 listen
- `--allow-talk`：仅在 listen 阶段允许自动回复

### 常用示例

```bash
bash run_pipeline.sh
bash run_pipeline.sh --history-limit 200 --max-joins 5
bash run_pipeline.sh --steps collect
bash run_pipeline.sh --steps collect,listen
bash run_pipeline.sh --continue-listen --allow-talk
```

---

## 2) `telethon_search_and_join_groups.py`

用途：按关键词/候选链接搜索公开群、尝试加入、可同步到监听列表。

### 命令

```bash
python3 telethon_search_and_join_groups.py [options]
```

### 主要参数

- `--keywords-file`（默认 `keywords.txt`）
- `--candidate-links-file`（默认 `candidate_links.txt`）
- `--seen-file`（默认 `seen_groups.json`）
- `--listen-targets-file`（默认 `listen_targets.json`）
- `--search-limit`（默认 `20`）
- `--history-limit`（默认 `30`，`0` 为尽量全量）
- `--recursive`（开启递归发现）
- `--max-groups`（默认 `100`）
- `--max-joins`（默认 `-1`，不限）
- `--add-to-listen-targets`（将群 id 同步到监听列表）
- `--max-depth`（递归深度，默认 `-1` 不限）
- `--proxy-host` / `--proxy-port`

### 常用示例

```bash
python3 telethon_search_and_join_groups.py
python3 telethon_search_and_join_groups.py --max-joins 5 --add-to-listen-targets
python3 telethon_search_and_join_groups.py --recursive --max-depth 2 --max-joins 5
python3 telethon_search_and_join_groups.py --proxy-host 127.0.0.1 --proxy-port 7890
```

输出重点：`seen_groups.json`、可选更新 `listen_targets.json`。

---

## 3) `telethon_analyze_listen_targets.py`

用途：读取 `listen_targets.json` 的群组，拉历史消息，用 Qwen 分析并写入报告。

### 命令

```bash
python3 telethon_analyze_listen_targets.py [options]
```

### 主要参数

- `--history-limit`（默认 `200`，`0` 为尽量全量）
- `--max-groups`（默认 `-1`，不限）

### 常用示例

```bash
python3 telethon_analyze_listen_targets.py
python3 telethon_analyze_listen_targets.py --history-limit 200
python3 telethon_analyze_listen_targets.py --history-limit 0
python3 telethon_analyze_listen_targets.py --max-groups 10
```

输出重点：`reports/*.txt`。

---

## 4) `telethon_talk.py`

用途：实时监听私聊/群聊；按配置决定是否自动回复；命中检测时写报告。

### 命令

```bash
python3 telethon_talk.py [--list_all_dialogs]
```

### 参数

- `--list_all_dialogs`：列出可见联系人和群组后退出

### 常用环境变量

- `TELETHON_TALK_ENABLE_REPLY=0|1`（默认 `0`）
- `TELEGRAM_GROUP_TRIGGER_NAMES=李,xxx`
- `TELEGRAM_GROUP_BUFFER_MAX_MESSAGES=8`
- `TELEGRAM_ENABLE_GROUPS=1`
- `TELEGRAM_PROXY_HOST` / `TELEGRAM_PROXY_PORT`

### 常用示例

```bash
python3 telethon_talk.py --list_all_dialogs
python3 telethon_talk.py
TELETHON_TALK_ENABLE_REPLY=1 python3 telethon_talk.py
TELEGRAM_GROUP_TRIGGER_NAMES=李 python3 telethon_talk.py
```

输出重点：终端事件日志 + `reports/*.txt`。

---

## 5) `dashboard_server.py`

用途：启动 Dashboard（浏览器可视化控制台）。

### 命令

```bash
python3 dashboard_server.py [--host 127.0.0.1] [--port 8765]
```

### 示例

```bash
python3 dashboard_server.py
python3 dashboard_server.py --host 0.0.0.0 --port 8765
```

启动后访问：`http://127.0.0.1:8765`

---

## 6) `telethon_send_cli.py`（新增）

用途：向一个或多个联系人/群组发送文本、文件、图片；支持定时发送和重复发送。

### 命令

```bash
python3 telethon_send_cli.py [options]
```

### 目标选择参数

- `--targets`：逗号分隔目标（显示名、`@username`、`t.me/...`、chat_id）
- `--targets-file`：每行一个目标
- `--target-ids`：逗号分隔 chat_id
- `--groups`：逗号分隔分组名（从 `--target-book` 读取）
- `--target-book`：分组 JSON 文件（默认 `send_target_groups.json`）
- `--match-mode exact|contains`：显示名匹配模式（默认 `exact`）

### 发送内容参数

- `--message "..."`
- `--message-file xxx.txt`
- `--file path`（可重复）
- `--image path`（可重复）

### 定时/重复参数

- `--schedule-in N`：N 秒后发送第一轮
- `--schedule-at "YYYY-MM-DDTHH:MM:SS"`：本地时间点发送第一轮
- `--repeat N`：发送轮数（默认 `1`）
- `--interval-seconds N`：多轮间隔（`repeat>1` 时必填）

### 其他参数

- `--list-dialogs`：列出可见会话后退出
- `--list-limit N`：列表上限（默认 `200`）
- `--show-groups`：展示 `--target-book` 里的分组并退出
- `--proxy-host` / `--proxy-port`

### 常用示例

```bash
python3 telethon_send_cli.py --list-dialogs
python3 telethon_send_cli.py --show-groups
python3 telethon_send_cli.py --targets "传 李" --message "hello"
python3 telethon_send_cli.py --groups ops_daily --target-book send_target_groups.json --message "daily ping"
python3 telethon_send_cli.py --targets "传 李,@mygroup" --file candidate_links.txt --image image.png
python3 telethon_send_cli.py --targets-file targets.txt --message "ping" --schedule-in 60
python3 telethon_send_cli.py --targets "传 李" --message "heartbeat" --repeat 5 --interval-seconds 30
```

---

## 7. agent 调用建议（all-in-one）

建议 agent 把任务拆成这几类动作：

1. 收集：调用 `telethon_search_and_join_groups.py`
2. 历史分析：调用 `telethon_analyze_listen_targets.py`
3. 实时监听：调用 `telethon_talk.py` 或 `run_pipeline.sh --steps listen`
4. 主动触达：调用 `telethon_send_cli.py`
5. 可视化人工值守：调用 `dashboard_server.py`

推荐把每个 CLI 的输入参数都标准化成 JSON，再转换成 shell 参数执行。

推荐把批量发送目标维护在：

- `send_target_groups.json`

格式示例：

```json
{
  "groups": {
    "ops_daily": ["传 李", "-1002069074753"],
    "test_groups": ["-1002069074753"]
  }
}
```

这样用户只需要说一句“给 ops_daily 发 xxx”，agent 就能映射到 `--groups ops_daily` 调用发送脚本。
