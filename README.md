# telegram_bot

这是一个基于 Telethon 和 Qwen 的 Telegram 群组发现、历史分析和实时监听工具集。

它主要用来完成三件事：

- 搜索并加入公开群组
- 对已加入或已监听群组的历史消息做内容分析并生成报告
- 对目标私聊和群组做持续监听，在实时消息中继续发现线索并输出报告

这个目录里目前主要有三个可直接使用的脚本：

- `telethon_talk.py`
- `telethon_search_and_join_groups.py`
- `telethon_analyze_listen_targets.py`

另外还有一个总控脚本：

- `run_pipeline.sh`

## 运行前准备

确保当前目录下这些文件已经准备好：

- `keys.txt`
  - 包含 `api_id` 和 `api_hash`
- `bot_key.txt`
  - 最后一行放 Qwen API Key
- `telethon_user_session.session`
  - 首次运行 Telethon 登录后会生成
- `listen_targets.json`
  - 监听的私聊和群组列表
- `detector_description.txt`
  - 给 Qwen 的检测描述

如果还没装依赖，可以先装：

```bash
pip install telethon openai
```

## Dashboard（可视化控制台）

项目现在支持一个本地 Dashboard，用来在浏览器里可视化并控制 `collect / analyze / listen` 三阶段流程。

### 快速启动

```bash
python3 dashboard_server.py
```

默认地址：

- `http://127.0.0.1:8765`

可选参数：

```bash
python3 dashboard_server.py --host 0.0.0.0 --port 8765
```

### Dashboard 里可以做什么

- 在“开始界面”里直接编辑并保存：
  - `keywords.txt`
  - `detector_description.txt`
- 勾选要执行的步骤（`collect` / `analyze` / `listen`）后，一键启动 pipeline
- 按本次运行覆盖：
  - 最大加群数（`max_joins`）
  - 群消息缓冲条数（`TELEGRAM_GROUP_BUFFER_MAX_MESSAGES`）
- 实时查看：
  - pipeline 运行状态与日志
  - Collect / Analyze / Listen 三列数据
  - 本轮测试指标
- 对 Analyze 列按群查看报告，展开后自动标记已读
- 一键清零命中次数（会先自动备份）

### Dashboard 数据来源（和脚本的关系）

- Collect 列
  - 由 `listen_targets.json` + `seen_groups.json` + `dashboard_state.json` 的 `collect_groups` 合并得到
- Analyze 列
  - 直接来自 `reports/*.txt`，按 `chat_id` 分组
  - 已读状态来自 `dashboard_read_state.json`
- Listen 列
  - 来自 `dashboard_state.json` 的 `listen_events`
  - 事件由 `telethon_talk.py` 在实时监听过程中写入
- 命中次数
  - 由 `reporting_utils.py` 在每次写报告时递增并写入 `dashboard_state.json`

### 说明

- Dashboard 启动 pipeline 时，底层仍然调用 `run_pipeline.sh`
- 目前 Dashboard UI 没有 `allow-talk` 开关；如果需要 bot 在群里实际发言，请用命令行：
  - `bash run_pipeline.sh --steps collect,analyze,listen --allow-talk`

## 推荐入口

如果你想用一条命令串起整个流程，直接用：

```bash
bash run_pipeline.sh
```

它默认会执行：

1. `collect`
2. `analyze`
3. 停止

如果你想在这之后继续实时监听：

```bash
bash run_pipeline.sh --continue-listen
```

如果你想继续实时监听并允许 user bot 发言：

```bash
bash run_pipeline.sh --continue-listen --allow-talk
```

如果你想直接在 shell 里指定历史分析条数和最大加群数：

```bash
bash run_pipeline.sh --history-limit 200 --max-joins 5
```

### `run_pipeline.sh` 的默认配置

`run_pipeline.sh` 已经把各个 Python 脚本的常用参数写成一套默认值，直接放在脚本开头，例如：

- `SEARCH_LIMIT`
- `SEARCH_RECURSIVE`
- `SEARCH_MAX_DEPTH`
- `SEARCH_MAX_GROUPS`
- `SEARCH_MAX_JOINS`
- `ANALYZE_HISTORY_LIMIT`
- `ANALYZE_MAX_GROUPS`

如果你想改默认行为，直接编辑 [run_pipeline.sh](/Users/mabokai/Desktop/proj/telegram_bot/run_pipeline.sh) 顶部这些变量即可。

### `run_pipeline.sh` 的步骤参数

可以用 `--steps` 指定只执行哪些步骤，支持：

- `collect`
- `analyze`
- `listen`

例如：

只做收集和加群：

```bash
bash run_pipeline.sh --steps collect
```

只做历史分析：

```bash
bash run_pipeline.sh --steps analyze
```

只启动实时监听：

```bash
bash run_pipeline.sh --steps listen
```

收集后直接监听，不跑历史分析：

```bash
bash run_pipeline.sh --steps collect,listen
```

完整三步都跑：

```bash
bash run_pipeline.sh --steps collect,analyze,listen --allow-talk
```

同时指定历史分析条数和最大加群数：

```bash
bash run_pipeline.sh --steps collect,analyze --history-limit 300 --max-joins 10
```

### `listen` 阶段会输出到哪里

`listen` 阶段实际就是启动 `telethon_talk.py`。

它的输出有两类：

- 终端输出
  - 启动日志
  - 每收到一条监听范围内的新消息，都会先 `print` 一行
  - 报告写入日志
- `reports/`
  - 如果群消息命中了 `detector_description.txt` 的检测描述，会在 `reports/` 目录下生成 `.txt` 报告

如果带了 `--allow-talk`：

- bot 会真的在 Telegram 里回复消息

如果不带 `--allow-talk`：

- 默认只监听、打印日志、写 `reports/`
- 不会真正发言

## 文件说明

- `listen_targets.json`
  - 监听名单，`telethon_talk.py` 和 `telethon_analyze_listen_targets.py` 都会用到
- `keywords.txt`
  - 搜索公开群的关键词，一行一个
- `candidate_links.txt`
  - 从 TGStat 或其他目录站整理来的候选 `@username`、`t.me/...`、TGStat 页面 URL，甚至可直接粘贴部分 TGStat 页面文本
- `seen_groups.json`
  - 搜索/加群脚本的状态文件
- `detector_description.txt`
  - 你要让大模型检测什么内容，就改这个文件
- `reports/`
  - Qwen 生成的命中报告会写到这里
- `dashboard_server.py`
  - Dashboard 后端服务（HTTP API + 静态页面）
- `dashboard_static/`
  - Dashboard 前端静态资源（`index.html` / `app.js` / `styles.css`）
- `dashboard_state.py`
  - Dashboard 状态读写工具
- `dashboard_state.json`
  - Dashboard 运行态数据（collect/listen 事件、命中计数）
- `dashboard_read_state.json`
  - Analyze 列的按群已读状态
- `hit_count_backups/`
  - 命中计数清零时自动生成的备份

## 1. telethon_talk.py

用途：

- 监听 `listen_targets.json` 里的私聊和群组
- 私聊自动回复
- 群里只有被叫到时才回复
- 群消息先缓冲，再按间隔批量处理
- 群消息会按 `detector_description.txt` 做显式分析，命中后写入 `reports/`

### 列出联系人和群组

先列出当前账号可见的联系人和群组，方便拿 `id`：

```bash
python3 telethon_talk.py --list_all_dialogs
```

这个命令会列出结果后直接退出。

### 正常启动

```bash
python3 telethon_talk.py
```

### 常用可调项

直接改脚本里的这些值：

- `GROUP_PROCESS_INTERVAL_SECONDS`
  - 群消息批处理间隔，默认 `5`
- `GROUP_BUFFER_MAX_MESSAGES`
  - 每个群缓冲的最大消息数，默认 `8`

也可以用环境变量调整代理或触发词：

```bash
TELEGRAM_PROXY_HOST=127.0.0.1 TELEGRAM_PROXY_PORT=7890 python3 telethon_talk.py
```

```bash
TELEGRAM_GROUP_TRIGGER_NAMES=李 python3 telethon_talk.py
```

## 2. telethon_search_and_join_groups.py

用途：

- 按关键词搜索公开群
- 可选导入你从 TGStat 或其他目录站整理的候选链接
- 找到后直接尝试加入
- 可以递归发现下一层公开群
- 会把结果写入 `seen_groups.json`
- 可选把群 `id` 自动同步到 `listen_targets.json`

### 输入文件

关键词在 `keywords.txt`，一行一个：

```text
photography
travel
```

可选候选链接文件在 `candidate_links.txt`，一行一个：

```text
@python
https://t.me/pythontelegrambotgroup
https://tgstat.org/bestoftelegram/channels/20/food-health/
```

现在 `candidate_links.txt` 不只支持 Telegram 链接，也支持：

- `@username`
- `https://t.me/...`
- `https://tgstat.org/...`
- 从 TGStat 页面复制出来的带 `Username: @...` 的文本行

### 最简单运行

```bash
python3 telethon_search_and_join_groups.py
```

### 常用参数

最多新加入 5 个群：

```bash
python3 telethon_search_and_join_groups.py --max-joins 5
```

把找到/已加入的群 `id` 同步到 `listen_targets.json`：

```bash
python3 telethon_search_and_join_groups.py --max-joins 5 --add-to-listen-targets
```

开启递归发现并限制层数：

```bash
python3 telethon_search_and_join_groups.py --recursive --max-depth 2 --max-joins 5
```

限制单次最多处理多少个新群：

```bash
python3 telethon_search_and_join_groups.py --max-groups 100
```

带代理运行：

```bash
python3 telethon_search_and_join_groups.py --proxy-host 127.0.0.1 --proxy-port 7890
```

### 输出文件

结果保存在 `seen_groups.json`，里面主要有这些字段：

- `processed_groups`
  - 每个群的详细处理结果
- `discovered_links`
  - 历史消息里提取到的 `t.me` 链接
- `all_groups`
  - 当前发现到的所有群的平铺列表
- `group_tree`
  - 按递归发现关系组织的树结构

## 3. telethon_analyze_listen_targets.py

用途：

- 读取 `listen_targets.json` 里的 `group_chat_ids`
- 拉取这些群的历史消息
- 用 Qwen 按 `detector_description.txt` 分析是否命中
- 把相关内容摘抄成报告写入 `reports/`

### 最简单运行

```bash
python3 telethon_analyze_listen_targets.py
```

### 常用参数

分析每个群最近 200 条消息：

```bash
python3 telethon_analyze_listen_targets.py --history-limit 200
```

尽量读取当前可见的全部历史：

```bash
python3 telethon_analyze_listen_targets.py --history-limit 0
```

最多只分析 10 个群：

```bash
python3 telethon_analyze_listen_targets.py --max-groups 10
```

## 最简单一步一步流程

下面这个流程适合你现在最常见的用法：先搜索公开群并自动加入，再把这些群同步到监听列表，然后做历史分析，最后启动实时监听。

### 第 1 步：准备关键词

打开 `keywords.txt`，一行写一个关键词，例如：

```text
photography
travel
```

如果你还从 TGStat 或其他目录站找到了公开链接，也可以顺手写到 `candidate_links.txt`，一行一个。

### 第 2 步：搜索并加入群，同时同步监听列表

例如最多加入 5 个群，同时把群 `id` 自动写入 `listen_targets.json`：

```bash
python3 telethon_search_and_join_groups.py --recursive --max-depth 2 --max-joins 5 --add-to-listen-targets
```

运行结束后，终端会看到：

- 成功加入了多少个群
- 哪些群已经在账号里
- 有多少群被同步进了 `listen_targets.json`

### 第 3 步：改检测描述

打开 `detector_description.txt`，把你想让 Qwen 关注和摘抄的内容写清楚。

### 第 4 步：先跑一次历史分析

```bash
python3 telethon_analyze_listen_targets.py --history-limit 50
```

命中的内容会被写到 `reports/`。

### 第 5 步：启动实时监听

```bash
python3 telethon_talk.py
```

启动后：

- `private_chat_ids` 里的私聊会自动回复
- `group_chat_ids` 里的群会被监听
- 群里只有被叫到时才回复
- 群消息命中 `detector_description.txt` 时会继续写入 `reports/`

## 一个常用完整示例

```bash
python3 telethon_search_and_join_groups.py --recursive --max-depth 2 --max-joins 5 --add-to-listen-targets
python3 telethon_analyze_listen_targets.py --history-limit 200
python3 telethon_talk.py
```

## shell 脚本常用示例

默认流程：收集 + 历史分析，然后停止：

```bash
bash run_pipeline.sh
```

只收集并加群，不做分析：

```bash
bash run_pipeline.sh --steps collect
```

只分析当前 `listen_targets.json` 里的群历史：

```bash
bash run_pipeline.sh --steps analyze
```

收集后直接进入实时监听，但默认不发言：

```bash
bash run_pipeline.sh --steps collect,listen
```

完整流程都跑，并允许发言：

```bash
bash run_pipeline.sh --steps collect,analyze,listen --allow-talk
```

## 用总控脚本的一步到位示例

默认流程，收集 + 历史分析，然后停止：

```bash
bash run_pipeline.sh
```

收集 + 历史分析 + 实时监听，但默认不发言：

```bash
bash run_pipeline.sh --continue-listen
```

收集 + 历史分析 + 实时监听，并允许发言：

```bash
bash run_pipeline.sh --continue-listen --allow-talk
```

只做某几个步骤：

```bash
bash run_pipeline.sh --steps collect
bash run_pipeline.sh --steps analyze
bash run_pipeline.sh --steps collect,listen
```

同时覆盖默认的历史分析条数和最大加群数：

```bash
bash run_pipeline.sh --history-limit 300 --max-joins 10
```
