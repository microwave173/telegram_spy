# 报告

```bash
bash run_pipeline.sh
```

大多数情况下，直接用这个 shell 脚本就够了。

## 先准备 3 个文本文件

### 1. `keywords.txt`

作用：

- 用来搜索公开群
- 一行一个关键词（最好是拼音或英文）

示例：

```text
feiji
liluan
miandian
jiema
miaobo
haoka
```

### 2. `candidate_links.txt`

作用：

- 如果你已经从 TGStat、目录站、别人发来的消息里拿到一些公开群链接，可以放这里
- 一行一个
- 可以写 `@用户名`
- 也可以写 `https://t.me/...`

示例：

```text
@python
https://t.me/pythontelegrambotgroup
```

如果你没有现成链接，这个文件可以留空。

### 3. `detector_description.txt`

作用：

- 告诉 Qwen 你到底想检测什么内容
- 历史分析和实时监听都会用这个描述

示例：

```text
请在聊天消息中寻找与诈骗引流、博彩推广、接码、账号买卖相关的内容。

重点关注：
- 联系方式
- 群链接
- 价格
- 交易方式
- 招募话术
```

建议：

- 写清楚“你想找什么”
- 写清楚“哪些信息最重要”

## 最常用的命令

### 1. 最常用：收集群 + 加群 + 分析历史，然后停止

```bash
bash run_pipeline.sh
```

这个命令会做 2 步：

1. 搜索公开群并尝试加入
2. 分析 `listen_targets.json` 里的群历史消息

然后停止。

适合：

- 第一次跑
- 先收集报告，不想马上进入持续监听

### 2. 指定历史分析条数和最大加群数

```bash
bash run_pipeline.sh --history-limit 200 --max-joins 5
```

意思是：

- 每个群最多分析最近 `200` 条历史消息
- 这次最多新加入 `5` 个群

这是很推荐的常用写法。

### 3. 跑完后继续实时监听，但默认不发言

```bash
bash run_pipeline.sh --continue-listen
```

这个命令会：

1. 搜索群
2. 加群
3. 分析历史
4. 然后继续实时监听

默认不会主动发消息。

### 4. 跑完后继续实时监听，并允许 bot 发言

```bash
bash run_pipeline.sh --continue-listen --allow-talk
```

这个命令和上面一样，但最后的实时监听阶段允许回复消息。

如果你不确定，建议先不要加 `--allow-talk`。

## 只执行某一步或某几步

脚本支持：

- `collect`
- `analyze`
- `listen`

### 只做收集和加群

```bash
bash run_pipeline.sh --steps collect
```

### 只做历史分析

```bash
bash run_pipeline.sh --steps analyze
```

### 只启动实时监听

```bash
bash run_pipeline.sh --steps listen
```

### 收集后直接进入监听，不跑历史分析

```bash
bash run_pipeline.sh --steps collect,listen
```

## 运行时会看到什么

### 第一步：收集和加群

终端里通常会看到类似：

```text
== Step: collect ==
Logged in as: 李 (id=8778938006)
Loaded 2 keyword(s) from .../keywords.txt
Loaded 1 imported candidate link(s) from .../candidate_links.txt
Collected 6 unique public candidate group(s).
Join success: @example_group
Already a member: @another_group
Added group id to listen targets: -1001234567890
Successfully joined new groups: 3
```

你可以重点看这些信息：

- `Join success`
- `Already a member`
- `Added group id to listen targets`
- `Successfully joined new groups`

### 第二步：历史分析

终端里通常会看到类似：

```text
== Step: analyze ==
Logged in as: 李 (id=8778938006)
Analyzing 6 listened group(s)
[##########--------------------] 2/6 current_chat_id=-1001234567890
Analyzing group: 示例群 (1234567890), messages=200
Report written: /Users/.../telegram_bot/reports/20260331T120000Z_1234567890_示例群.txt
No relevant content found.
Done. analyzed_groups=6, reports_written=2
```

你可以重点看这些信息：

- 进度条
- `Analyzing group`
- `Report written`
- `No relevant content found`

### 第三步：实时监听

如果你启用了 `listen`，终端里通常会看到类似：

```text
== Step: listen ==
Allow talk: 0
Telethon 用户号 AI 已启动：李 (id=8778938006)
等待接收配置中的私聊/群聊消息中...
发言开关：关闭
[incoming][group] chat_id=-1001234567890 text=这里是新消息内容
report_written /Users/.../telegram_bot/reports/20260331T121500Z_1234567890_示例群.txt
```

你可以重点看这些信息：

- `[incoming]`
  - 表示监听到了新消息
- `report_written`
  - 表示这条或这一批消息命中了检测条件，已经写报告

## 输出文件在哪里

### 1. 报告文件

最重要的输出在：

```text
reports/
```

每次命中后会生成一个 `.txt` 报告文件。

例如：

```text
reports/20260331T121500Z_1234567890_示例群.txt

generated_at: 2026-03-31T08:39:12.173627+00:00
chat_title: 豪猪接码平台 实卡接码 注册接码 jiema
chat_id: 3604640173
source: history_scan

命中概述：
- 消息内容宣传“接码平台”、“卡商”服务，提供全球多国实卡及虚拟手机号，用于注册各类社交及金融 APP（如微信、支付宝、抖音等），涉及匿名接收短信验证码业务。

相关摘抄：
- [msg_id=496][date=2026-03-15T07:34:12+00:00][sender=-1003570737913] 最全面的接码客户端内置 api 接口
全球 197 个国家实卡手机号虚拟号
还在为注册一个社交账号接了一批又一批
本公司通过专业团队技术手段严格全面筛选，接码通过率 95%！
- [msg_id=498][date=2026-03-15T07:34:12+00:00][sender=-100357073737913] 👌 ——飞机直登号——👌

😀+84-越南           百起 3.5
😂+1-美国             百起 4.0
😂+852-香港        百起 5.5
😂+86-中国          百起 4.0
- [msg_id=501][date=2026-03-15T07:34:12+00:00][sender=-1003570737913] ⚠️平台所有手机号都是卡商的，手机号对于你的业务是新号还是老号或者是否符合自己需求请自行分辨，平台仅仅提供短信验证码，其他不做任何保证
- [msg_id=506][date=2026-03-15T07:34:17+00:00][sender=-1003570737913] ⚠️接码项目：微信，QQ，陌陌，抖音，探探，墨往，支付宝，连信，钉钉，等国内外所有 app。

判断理由：
- 消息中多次出现“接码平台”、“卡商”、“注册接码”等关键词，明确提供用于绕过实名认证的短信验证码接收服务。
- 服务内容涉及批量注册国内外社交及金融类 APP（微信、支付宝等），此类“接码”与“卡商”业务属于网络黑灰产范畴，常作为电信诈骗的基础设施工具，符合“诈骗相关”及“非法网站相关”的检测描述。

messages_json:
...
```

报告里通常会包含：

- 生成时间
- 群名
- 群 ID
- 来源
- 命中概述
- 相关摘抄
- 判断理由
- 原始消息 JSON

### 2. 监听列表

自动加入并同步后的群 ID 会写到：

```text
listen_targets.json
```

这个文件决定后面哪些群会被分析、哪些群会被实时监听。

### 3. 搜索和加群状态

搜索和递归发现的结果会写到：

```text
seen_groups.json
```

这个文件里会保存：

- 找到过哪些群
- 群名和 ID
- 从哪里发现的
- 历史里提取到的 `t.me` 链接

## 一套推荐用法

如果你只是想稳定地跑一轮，建议直接用这条：

```bash
bash run_pipeline.sh --history-limit 200 --max-joins 5
```

如果你想跑完后继续盯着新消息，但先不要让 bot 开口说话，建议用：

```bash
bash run_pipeline.sh --history-limit 200 --max-joins 5 --continue-listen
```

如果你确认要让 bot 发言，再用：

```bash
bash run_pipeline.sh --history-limit 200 --max-joins 5 --continue-listen --allow-talk
```
