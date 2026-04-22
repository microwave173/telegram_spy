# telegram_bot

这是一个面向 Telegram 线索发现与运营的工具仓库，支持：

- 群组发现与加入（collect）
- 历史消息分析与报告（analyze）
- 实时监听与持续产出（listen）
- 面向联系人/群组的批量发送（支持分组与定时）

## 推荐入口（先看这个）

如果你后续要做 all-in-one agent，请先看：

- [`SKILL.md`](/Users/mabokai/Desktop/proj/telegram_bot/SKILL.md)

`SKILL.md` 定义了：

- agent 该如何调用本仓库脚本
- 如何通过 `send_target_groups.json` 做“分组批量发送”
- 如何实现“用户一句话 -> agent 自动映射分组 -> 执行发送”

## 快速开始

### 1) 安装依赖

```bash
pip install telethon openai
```

### 2) 准备关键文件

- `keys.txt`（`api_id` + `api_hash`）
- `bot_key.txt`（Qwen API Key）
- `telethon_user_session.session`（首次登录后生成）

### 3) 常见用法

完整流水线：

```bash
bash run_pipeline.sh
```

启动 Dashboard：

```bash
python3 dashboard_server.py
```

查看发送分组：

```bash
python3 telethon_send_cli.py --show-groups
```

按分组发送：

```bash
python3 telethon_send_cli.py \
  --groups ops_daily \
  --target-book send_target_groups.json \
  --message "hello"
```

## 文档结构

- 简略说明：[`README.md`](/Users/mabokai/Desktop/proj/telegram_bot/README.md)
- 详细文档：[`README_FULL.md`](/Users/mabokai/Desktop/proj/telegram_bot/README_FULL.md)
- CLI 参数总览：[`CLI_SCRIPTS.md`](/Users/mabokai/Desktop/proj/telegram_bot/CLI_SCRIPTS.md)
- agent 技能定义：[`SKILL.md`](/Users/mabokai/Desktop/proj/telegram_bot/SKILL.md)

## 发送分组配置

分组文件：

- [`send_target_groups.json`](/Users/mabokai/Desktop/proj/telegram_bot/send_target_groups.json)

示例：

```json
{
  "groups": {
    "core_contacts": ["传 李"],
    "ops_daily": ["传 李", "-1002069074753"]
  }
}
```

配置好分组后，用户只需一句话（例如“给 ops_daily 发今天总结”），agent 就可以映射到发送 CLI 执行。
