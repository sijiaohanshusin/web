# 哈尔滨工程大学电子科技协会官网

线上地址：[heuesta.cn](https://heuesta.cn)

这是协会官网的完整代码仓库：Django 全栈站点（官网 + 会员系统 + 资料站）+ 静态电子学学习中心 + 部署运维脚本。

## 仓库结构

```text
web/
├── app/                Django 项目（官网本体）
│   ├── config/         配置（settings 分 dev/prod 两套）
│   ├── core/           首页、新生指南、B 站数据集成、站点配置
│   ├── accounts/       会员系统（注册/登录/审核/角色）
│   ├── files/          资料站（上传/下载/权限）
│   ├── templates/      页面模板
│   └── static/         CSS / JS / 图片（无构建链，改完即生效）
├── learn/electronics/  电子学学习中心（纯静态，nginx 直接服务）
├── ops/                部署：Dockerfile、compose、nginx 配置、部署/备份脚本
├── scripts/            工具脚本（图片压缩等）
└── docs/维护手册.md     ★ 接手维护先读这个
```

## 本地开发（Windows / macOS / Linux 通用）

```bash
# 1. 建虚拟环境并装依赖（只需一次）
python -m venv .venv
.venv/Scripts/pip install -r app/requirements.txt      # Windows
# .venv/bin/pip install -r app/requirements.txt        # macOS / Linux

# 2. 初始化数据库并创建管理员（只需一次）
cd app
../.venv/Scripts/python manage.py migrate
../.venv/Scripts/python manage.py createsuperuser

# 3. 启动开发服务器
../.venv/Scripts/python manage.py runserver
```

打开 <http://127.0.0.1:8000>，管理后台在 `/admin/`。开发模式用 SQLite，不需要装数据库。

## 线上部署

服务器上一条命令：

```bash
sudo /opt/heuesta/web/ops/deploy.sh
```

它会自动：拉最新代码 → 重建 Docker 镜像 → 数据库迁移 → 收集静态文件 → 同步学习中心 → 重载 nginx。

日常更新流程：本地改代码 → 推送到 GitHub `main` → 服务器上跑 `deploy.sh`。

## 常用运维

| 操作 | 入口 / 命令 |
| --- | --- |
| 部署 / 更新 | `sudo /opt/heuesta/web/ops/deploy.sh` |
| 看应用日志 | `cd /opt/heuesta/web && docker compose -f ops/docker-compose.yml --env-file /opt/heuesta/.env logs -f app` |
| 手动备份 | `sudo /opt/heuesta/web/ops/backup.sh` |
| 审核会员 / 数据图表 / 传资料 / 改配置 / 轮播图 | **管理驾驶舱** `heuesta.cn/dashboard/`（干事及以上） |
| 底层数据管理 | 高级后台 `heuesta.cn/admin/`（管理员，simpleui 主题） |

详细说明（架构图、备份恢复、故障排查、如何加新页面）见 [docs/维护手册.md](docs/维护手册.md)。

## 技术栈

- **后端**：Django 5.2 LTS（Python 3.12）+ PostgreSQL 16（生产）/ SQLite（开发）
- **前端**：Django 模板 + 手写 CSS/JS，零构建链，零 Node 依赖
- **部署**：Docker Compose + 宿主机 nginx + Let's Encrypt，站点前置 CDN
- **历史版本**：旧静态站保存在 `legacy-static` 分支
