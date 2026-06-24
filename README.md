# ⚽ 世界杯竞猜平台 World Cup Guess

2026 世界杯球迷群竞猜系统 — 一站式提交预测、自动算分、实时排名。

## 功能概览

| 功能 | 说明 |
|------|------|
| 🔐 账号系统 | 昵称 + 密码注册登录，管理员单独账号 |
| 📜 规则展示 | 四个竞猜项目完整规则，比分预测示例 |
| 🏆 项目一 | 冠军 + 金靴/金球/金手套/最佳年轻球员预测 |
| 📋 项目二 | 小组赛排名预测（12个小组，每组猜第一第二） |
| 🏟️ 项目三 | 淘汰赛四强预测（4个分区各选一队） |
| ⚽ 项目四 | 32场淘汰赛单场比分竞猜 |
| 🧮 自动算分 | 录入比分后自动比对、算分、更新排名 |
| 🌾 收米之星 | 每日得分最高者获荣誉称号 |
| 📊 实时排名 | 总分排名 + 各项目单项得分 |
| 🔍 预测公示 | 赛后公开所有群友预测，透明可见 |
| 🎛️ 管理员控制 | 手动开放/截止项目一/二/三的填写 |
| 📈 统计页面 | 查看所有群友竞猜信息 + 饼图可视化分析 |
| 🏳️ 国旗图标 | 使用 flagcdn.com SVG 图片，Windows/手机全平台兼容 |
| 📱 移动端 | 响应式设计，微信浏览器打开直接用 |

## 项目结构

```
world-cup-guess/
├── run.py                 # 应用入口
├── src/                   # Python 源码包
│   ├── __init__.py        # Flask 应用主入口（页面路由 + API + CLI命令）
│   ├── config.py          # 配置文件（积分规则、管理员账号）
│   ├── models.py          # 数据库模型（8个表，SQLAlchemy ORM）
│   └── scoring.py         # 算分引擎（纯函数，含大球加成和决赛翻倍逻辑）
├── scripts/               # 工具脚本
│   ├── init_db.py         # 一键初始化数据库 + 创建管理员账号 + 迁移脚本
│   ├── deploy.sh          # Ubuntu 22.04 一键部署脚本
│   └── update.sh          # 增量更新脚本（保留玩家数据）
├── tests/                 # 测试
│   └── test_e2e.py        # 端到端测试脚本（覆盖注册→预测→算分→排名）
├── requirements.txt       # Python 依赖
├── CLAUDE.md              # AI 辅助开发文档
├── static/
│   └── style.css          # 自定义样式（Pico.css 主题 + 响应式 + 国旗图标）
└── templates/
    ├── layout.html        # 公共导航框架（含统计入口）
    ├── index.html         # 首页（赛况概览 + 收米之星）
    ├── login.html         # 登录 / 注册
    ├── rules.html         # 竞猜规则完整展示
    ├── predict.html       # 四个竞猜项目的提交入口（含截止状态提示）
    ├── matches.html       # 所有淘汰赛 + 赛后预测公示
    ├── rankings.html      # 积分排名 + 收米之星历史
    ├── stats.html         # 统计页（预测数据 + Chart.js 饼图可视化）
    └── admin.html         # 管理后台（添加比赛、录入比分、结算项目、项目状态控制）
```

## 技术栈

| 层面 | 选择 |
|------|------|
| 后端框架 | Python Flask |
| 数据库 | SQLite + SQLAlchemy ORM |
| 用户认证 | Flask-Login + Session |
| 前端 | Jinja2 模板 + Pico.css + 原生 JS |
| 生产部署 | Gunicorn + Nginx + systemd |

## 竞猜规则

### 活动简介

2026 年世界杯期间，可以组建球友参与竞猜活动。活动分为 **4 个项目**，各项目累计积分排名，=**前三名有奖**。

---

### 🏆 项目一：冠军 + 四项个人奖项

竞猜冠军球队以及四项个人奖项得主。决赛结束后结算。

| 预测项 | 分值 | 说明 |
|--------|------|------|
| 🏆 冠军球队 | **8 分** | 世界杯冠军队伍 |
| 👟 金靴奖 | **3 分** | 赛事最佳射手（进球最多） |
| 🏅 金球奖 | **3 分** | 赛事最佳球员（综合表现最优） |
| 🧤 金手套奖 | **3 分** | 赛事最佳守门员 |
| 🌟 最佳年轻球员 | **3 分** | 赛事最佳 21 岁及以下球员 |
| 全部猜对 | **20 分** | |

> 📌 提交截止：第一场淘汰赛开赛前。截止前可修改。

---

### 📋 项目二：小组赛排名

世界杯小组赛共 **12 个小组**（A-L 组），每组 4 支球队。群友预测每个小组的**第一名和第二名**。

| 预测项 | 猜对得分 |
|--------|---------|
| 单个小组（第一 + 第二全对且顺序正确）| **1 分** |
| 满分（12组全部猜对）| **12 分** |

> ⚠️ 第一和第二必须**全部猜对且顺序正确**才得分。只对一个或顺序颠倒不得分。
>
> 📌 提交截止：小组赛开赛前（2026-06-11）。截止前可修改。

---

### 🏟️ 项目三：四强

世界杯淘汰赛共 32 支球队，分为 **4 个 1/4 分区**，每区 8 支球队。

群友在每个分区中选择一支可能进入四强的球队，共预测 4 支。每猜对一支得 **2 分**，满分 **8 分**。

> 📌 开放时间：16强出炉后 → 截止：16进8开赛前

---

### ⚽ 项目四：单场淘汰赛

世界杯共有 **32 场淘汰赛**，每场开赛前竞猜该场比赛比分。

> ⚠️ 只考虑**常规时间**比分，不考虑加时和点球大战。

**基本积分：**

| 情况 | 得分 |
|------|------|
| 比分完全正确 | **3 分** |
| 比分不完全正确，但胜负关系对（胜/负/平）| **1 分** |
| 胜负关系错误 | 0 分 |

**🏅 决赛加成：** 决赛猜对比分得 **6 分**，胜负关系对得 **2 分**。

**💥 大球加成：** 当常规时间 **总进球数 ≥ 5** 或 **分差 ≥ 3** 时，猜对比分可得 **5 分**（决赛则为 10 分）。

**举例说明：**

> **半决赛：葡萄牙 vs 英格兰**
>
> 赛前预测：玩家A预测葡 1-1 英，玩家B预测葡 2-1 英，玩家C预测葡 8-1 英
>
> 实际结果：**葡萄牙 8-1 英格兰**（总进球 9 ≥ 5，分差 7 ≥ 3 → 激活大球加成）
>
> - 玩家A：**0 分**（预测平局，实际主队胜）
> - 玩家B：**1 分**（胜负关系对，比分不对）
> - 玩家C：**5 分**（比分全对 + 大球加成）

---

### 🌾 收米之星

以**比赛日**为单位，每天颁给前一天所有比赛结算后得分最高的群友。

- 多人并列则**共享称号**，纯荣誉，不加分
- 排名页展示每位群友累计获得次数（🌾 × N）
- 整个赛事结束后，获得次数最多者授予 **「收米界最长的河」🏆** 称号

---

### 积分与排名

小组赛开始后，陆续结算各项积分。四项目合计总分排序，前三名有奖。

## 本地开发

### 环境要求

- Python 3.10+
- pip

### 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库
python scripts/init_db.py

# 3. 启动开发服务器
python run.py

# 4. 打开浏览器访问
# http://127.0.0.1:5000
```

默认管理员：昵称 `admin`，密码 `admin123`（可在 `config.py` 修改）。

### 运行测试

测试前需要**清空数据库**，然后**启动服务器**，再运行测试脚本。

**Linux / macOS (bash)：**

```bash
# 清空数据库并初始化
rm -f instance/guess.db
python scripts/init_db.py

# 后台启动服务器
python run.py &

# 运行测试
PYTHONIOENCODING=utf-8 python tests/test_e2e.py
```

**Windows (PowerShell)：**

```powershell
# 清空数据库并初始化
Remove-Item -Force instance/guess.db
python scripts/init_db.py

# 启动服务器（新开一个 PowerShell 窗口，切换到项目目录后执行）
python run.py

# 回到原窗口，设置编码并运行测试
$env:PYTHONIOENCODING = "utf-8"
python tests/test_e2e.py
```

> 💡 **为什么需要两个终端？** Windows PowerShell 不支持 bash 的 `&` 后台运行语法，所以服务器和测试需要分别在两个窗口中运行。Linux/macOS 用户可以在一个终端中用 `&` 后台启动服务器。

## 部署到云服务器

### 1. 购买服务器

推荐阿里云 ECS：1核 2GB，Ubuntu 22.04 LTS，1-3 Mbps 带宽。

买完后获得**公网 IP**。

服务器购买完成后，需在其安全组中开放 80(HTTP) 端口。

如果以后以后要配置 HTTPS 域名，也可以顺手加上 443(HTTPS) 端口。

### 2. 连接到服务器

```bash
ssh root@你的服务器IP
```

> 如果提示 `Permission denied (publickey)`，去阿里云控制台「重置实例密码」并重启，再用密码登录。

### 3. 一键部署

```bash
# 先安装 git 并拉取代码
apt update && apt install -y git
git clone https://github.com/你的仓库/world-cup-guess.git /opt/world-cup-guess

# 执行部署脚本
cd /opt/world-cup-guess
sudo bash scripts/deploy.sh
```

`deploy.sh` 自动完成：
- 安装 Python、Nginx、Gunicorn
- 创建虚拟环境并安装依赖
- 初始化数据库
- 配置 systemd 服务（开机自启）
- 配置 Nginx 反向代理
- 开放防火墙 80 端口

### 4. 验收

浏览器访问 `http://你的服务器IP`，能看到首页即为成功。

### 5. 管理员账户密码

默认管理员密码：admin

部署脚本会自动生成随机管理员密码。查看方式：

```bash
grep ADMIN_PASSWORD /etc/systemd/system/world-cup-guess.service
```

如需重置管理员密码，SSH 到服务器，然后运行两段命令：

```bash
cd /opt/world-cup-guess && source venv/bin/activate
```

```bash
python3 << 'EOF'
from src import create_app
from src.models import User, db
app = create_app()
with app.app_context():
    admin = User.query.filter_by(nickname='admin').first()
    admin.set_password('你的新密码')
    db.session.commit()
    print('Password reset successfully!')
EOF
```

### 6. 更新代码（保留玩家数据）

后续功能更新时，**不要重新运行 `deploy.sh`**（它会重新生成密钥）。使用增量更新脚本：

```bash
cd /opt/world-cup-guess
sudo bash scripts/update.sh
```

`update.sh` 自动完成：
- 拉取最新代码（`git pull`）
- 安装新依赖
- 执行数据库迁移（安全可重复）
- 重启服务

不会覆盖 `instance/guess.db`，玩家数据完好。

## 管理后台操作

管理员登录后可在 `http://你的IP/admin` 执行：

| 操作 | 说明 |
|------|------|
| ➕ 添加比赛 | 逐个添加 32 场淘汰赛（轮次、对阵、时间）|
| 🔓 开放/关闭预测 | 控制每场比赛是否接受竞猜 |
| 🎛️ 项目状态控制 | 手动开放/截止项目一/二/三的填写（亦可设为自动）|
| 📝 录入比赛结果 | 输入真实比分 → 自动算分 → 自动判定收米之星 |
| 🏆 结算项目一 | 输入冠军/金靴/金球 → 批量算分 |
| 📋 结算项目二 | 输入12个小组的第一第二名 → 批量算分 |
| 🏟️ 结算项目三 | 输入四强球队 → 批量算分 |
| ✏️ 编辑群友预测 | 查看和修改任意群友的项目一/二/三内容 |
| 🌍 球队管理 | 修改球队的分区和小组归属 |

## 配置文件说明

`config.py` 中可修改：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | 随机字符串 | 生产环境务必修改 |
| `ADMIN_NICKNAME` | admin | 管理员昵称 |
| `ADMIN_PASSWORD` | admin123 | 管理员密码 |
| `P1_CHAMPION_PTS` | 8 | 项目一冠军分值 |
| `P1_GOLDEN_BOOT_PTS` | 3 | 项目一金靴分值 |
| `P1_GOLDEN_BALL_PTS` | 3 | 项目一金球分值 |
| `P1_GOLDEN_GLOVE_PTS` | 3 | 项目一金手套分值 |
| `P1_BEST_YOUNG_PLAYER_PTS` | 3 | 项目一最佳年轻球员分值 |
| `P1_MAX_PTS` | 20 | 项目一满分 |
| `P2_GROUP_PTS` | 1 | 项目二每组猜对分值 |
| `P2_MAX_PTS` | 12 | 项目二满分（12组×1分）|
| `P3_PER_TEAM_PTS` | 2 | 项目三每队分值（四强）|
| `P4_EXACT_PTS` | 3 | 项目四比分全对分值 |
| `P4_RESULT_PTS` | 1 | 项目四胜负关系对分值 |
| `P4_FINAL_MULTIPLIER` | 2 | 决赛翻倍倍数 |
| `P4_BIG_MATCH_GOALS` | 5 | 大球加成：总进球阈值 |
| `P4_BIG_MATCH_DIFF` | 3 | 大球加成：分差阈值 |
| `P4_BIG_MATCH_PTS` | 5 | 大球加成：猜对比分分值 |

## License

MIT
