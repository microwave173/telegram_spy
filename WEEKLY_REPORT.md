# 周报

## 本周目标

本周主要把 Telegram 工具链整理成一套三阶段流程，方便从公开群发现、内容分析，到后续持续监听形成闭环。

三阶段分别是：

1. `collect`
2. `analyze`
3. `listen`

## 三阶段在做什么

### 1. collect

作用：

- 根据 `keywords.txt` 搜索公开群
- 可选结合 `candidate_links.txt` 里的候选链接
- 自动尝试加入目标群
- 把群 `id` 同步到 `listen_targets.json`
- 把搜索和发现结果写入 `seen_groups.json`

简单理解：

- 这一阶段负责“找群、加群、建名单”

输入：

- `keywords.txt`
- `candidate_links.txt`

输出：

- `listen_targets.json`
- `seen_groups.json`

### 2. analyze

作用：

- 读取 `listen_targets.json` 里的群组列表
- 拉取群历史消息
- 按 `detector_description.txt` 交给 Qwen 分析
- 把命中的内容摘抄成报告

简单理解：

- 这一阶段负责“看历史、找重点、出报告”

输入：

- `listen_targets.json`
- `detector_description.txt`

输出：

- `reports/`

### 3. listen

作用：

- 持续监听 `listen_targets.json` 里的私聊和群组
- 监听到消息时先在终端打印日志
- 群消息会按缓冲批次处理
- 命中检测描述时继续写入 `reports/`
- 可选允许 bot 发言，默认关闭

简单理解：

- 这一阶段负责“实时盯消息、持续补报告”

输入：

- `listen_targets.json`
- `detector_description.txt`

输出：

- 终端实时日志
- `reports/`

## 当前成果

本周已经完成：

- 三阶段脚本拆分清楚，并能通过 shell 一键执行
- 搜索加群、同步监听名单、历史分析、实时监听已经串起来
- 增加了 `run_pipeline.sh` 作为统一入口
- 增加了 `README.md` 和 `REPORT.md`，方便快速上手
- 增加了实验记录，验证三阶段都能正常运行

## 当前默认流程

最常用命令：

```bash
bash run_pipeline.sh
```

默认会执行：

1. `collect`
2. `analyze`
3. 停止

如果需要继续实时监听：

```bash
bash run_pipeline.sh --continue-listen
```

如果需要继续实时监听并允许 bot 发言：

```bash
bash run_pipeline.sh --continue-listen --allow-talk
```

## 一句话总结

这套系统现在可以概括为：

- 先找群并加入
- 再分析历史消息生成报告
- 最后可选进入持续监听，继续发现新内容并产出报告
