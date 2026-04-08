# 实验记录

实验时间：2026-03-31

这份记录按当前 shell 的 3 个阶段整理：

- `collect`
- `analyze`
- `listen`

## 1. collect 阶段实验

### 实验命令

```bash
bash run_pipeline.sh --steps collect --max-joins 1
```

### 关键输出

```text
== Step: collect ==
Logged in as: 李 (id=8778938006)
Loaded 6 keyword(s) from /Users/mabokai/Desktop/proj/telegram_bot/keywords.txt
Loaded 0 imported candidate link(s) from /Users/mabokai/Desktop/proj/telegram_bot/candidate_links.txt
Recursive discovery: on
Max discovery depth: 2
Max joins: 1
Add joined ids to listen targets: on
...
Collected 13 unique public candidate group(s).
Skipping already-seen group: @MianDian004
Skipping already-seen group: @feijiDH
Skipping already-seen group: @feijihaohaoge1
...
Done.
Successfully joined new groups: 0
Already-member groups: 0
Pending approval groups: 0
Added ids to listen targets: 0
Inspected new groups: 0
Skipped already-seen groups: 13
Inspection errors: 0
```

### 实验结果

- 当前 `keywords.txt` 里的 6 个关键词一共命中了 13 个公开候选群
- 这 13 个候选群都已经存在于 `seen_groups.json`
- 这次实验没有新加群
- 这次实验也没有新增 `listen_targets.json`

### 结论

- `collect` 阶段可以正常工作
- 当前默认关键词对应的候选群已经基本被当前状态文件覆盖
- 如果想看到新的加群结果，需要换一批关键词，或者补充 `candidate_links.txt`

## 2. analyze 阶段实验

### 实验命令

为了让输出更及时、实验更小范围，这里使用了单独的分析脚本，只分析 1 个群、最近 20 条消息：

```bash
python3 -u telethon_analyze_listen_targets.py --history-limit 20 --max-groups 1
```

### 关键输出

```text
Logged in as: 李 (id=8778938006)
Analyzing 6 listened group(s)
[##############################] 1/1 current_chat_id=-1003604640173
Analyzing group: 豪猪接码平台 实卡接码 注册接码 jiema (-1003604640173), messages=18
Report written: /Users/mabokai/Desktop/proj/telegram_bot/reports/20260331T113128Z_-1003604640173_豪猪接码平台_实卡接码_注册接码_jiema.txt
[##############################] 1/1
Done. analyzed_groups=1, reports_written=1
```

### 实验结果

- 成功登录
- 成功读取 `listen_targets.json`
- 成功显示进度条
- 成功分析 1 个群
- 成功写出 1 份报告

### 报告文件

本次实验生成的报告在：

```text
/Users/mabokai/Desktop/proj/telegram_bot/reports/20260331T113128Z_-1003604640173_豪猪接码平台_实卡接码_注册接码_jiema.txt
```

### 结论

- `analyze` 阶段可以正常工作
- Qwen 检测链路和 `reports/` 写文件链路正常
- 终端进度条也正常显示

## 3. listen 阶段实验

### 实验命令

```bash
PYTHONUNBUFFERED=1 bash run_pipeline.sh --steps listen
```

### 关键输出

```text
== Step: listen ==
Allow talk: 0
Telethon 用户号 AI 已启动：李 (id=8778938006)
等待接收配置中的私聊/群聊消息中...
发言开关：关闭
```

实验结束时手动按了 `Ctrl+C` 停止监听。

### 实验结果

- `listen` 阶段可以正常启动
- 当前默认是静默监听
- 发言开关处于关闭状态
- 监听进程可以正常进入等待消息状态

### 结论

- `listen` 阶段可以正常工作
- 当前配置下它会：
  - 监听消息
  - 在终端打印收到的消息日志
  - 命中时写 `reports/`
  - 但不会主动发言

## 总结

这次实验的整体结果是：

- `collect`：成功运行，但当前候选群都已经见过，没有新增加群
- `analyze`：成功分析并产出报告
- `listen`：成功启动并进入持续监听状态

如果下一步想更容易看到 `collect` 阶段的“新加群”效果，建议：

1. 修改 `keywords.txt`
2. 或者补充 `candidate_links.txt`
3. 然后再重新运行：

```bash
bash run_pipeline.sh --steps collect --max-joins 1
```
