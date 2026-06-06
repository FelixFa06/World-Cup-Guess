# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

世界杯球迷群竞猜平台 — Flask Web 应用，替代手工 Excel 管理模式。群友提交预测，管理员录入比分，系统自动算分排名。

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库（创建表 + admin 用户）
python init_db.py

# 启动开发服务器
python -m flask --app app run --host 0.0.0.0 --port 5000

# 运行端到端测试（需要先启动服务器）
# 注意：测试会操作当前数据库，先清空 instance/guess.db
rm -f instance/guess.db && python init_db.py
python -m flask --app app run --host 0.0.0.0 --port 5000 &
PYTHONIOENCODING=utf-8 python test_e2e.py

# 生产部署（在 Ubuntu 服务器上）
sudo bash deploy.sh
```

## 架构

```
Flask 单文件应用 (app.py)
  ├── 页面路由 → Jinja2 模板 (templates/)
  ├── API 路由 → JSON (用户操作 + 管理员操作)
  └── 算分引擎 (scoring.py) → 纯函数，无副作用

SQLAlchemy ORM (models.py) → SQLite (instance/guess.db)
  ├── User / Match / Project1Pick / GroupStagePick / Project2Pick / MatchPrediction / DailyStar
```

## 核心算分规则 (scoring.py)

- **项目一**：冠军 6分 / 金靴 3分 / 金球 3分 / 金手套 3分 / 最佳年轻球员 3分，满分 18分 — `score_project1()`
- **项目二**：小组赛排名，12组各猜第一第二名，全对且顺序正确得2分/组，满分24分 — `score_group_stage()`
- **项目三**：4个分区各选1队进四强，每对1队 2分 — `score_project2()`（DB 表仍为 project2_picks）
- **项目四**：比分全对 3分，胜负关系对 1分；总进球≥5 或 分差≥3 → 猜对比分 5分；决赛翻倍 — `score_match_prediction()`
- **收米之星**：`calculate_daily_stars()` 按比赛日汇总，最高分者获得（可并列）

## 关键设计点

- **SQLite 要求 naive datetime**：项目中使用 `utcnow()` (app.py 中定义) 返回无时区的 UTC 时间。**禁止**使用 `datetime.now(timezone.utc)` 直接写入数据库。
- **算分幂等性**：录入比赛结果时先清再算，重复触发不会重复加分。
- **截止控制**：项目一在淘汰赛开赛前截止；项目二（小组赛排名）在小组赛开赛前截止；项目三（四强）在16进8开赛前截止；项目四每场开赛前截止。由 `_is_p1_deadline_passed()`、`_is_p2_deadline_passed()`、`_is_p3_open()`、`_is_p3_deadline_passed()` 等函数判断。
- **管理员账号**：`config.py` 中 `ADMIN_NICKNAME` / `ADMIN_PASSWORD`，初始化时自动创建。`is_admin=True` 的用户不参与竞猜。
- **前端零构建**：Pico.css 从 CDN 加载，无 npm/webpack。移动端优先。
- **instance/ 目录不进 git**：数据库文件在 `.gitignore` 中排除。

## 部署

`deploy.sh` 在 Ubuntu 22.04 上完成：系统更新 → 安装 Python/Nginx → 创建 venv → 初始化 DB → 配置 systemd + Gunicorn → 配置 Nginx 反向代理 → 开启防火墙。

管理员密码在部署时会自动重新生成（脚本用 `secrets.token_hex` 覆盖环境变量），部署后查看 `/etc/systemd/system/world-cup-guess.service` 中的 `ADMIN_PASSWORD`。
