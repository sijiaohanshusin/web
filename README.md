# 哈尔滨工程大学电子科技协会官网

线上地址：[heuesta.cn](https://heuesta.cn) · 论坛：[bbs.heuesta.cn](https://bbs.heuesta.cn)

本仓库包含协会官网、会员与招新系统、资料站、活动与项目模块、NodeBB 论坛，以及生产部署和备份脚本。当前版本为 **2026 招新预发布版**，2026 秋季招新已开放。

## 正式招新规则

- 注册入口分为“新会员”和“老会员”两个通道。
- 新会员通过邮箱验证后自动成为“招新成员”，可登录、提交招新申请和维护个人资料，但不会解锁会员资料、活动报名、项目、管理驾驶舱或论坛账号。
- 老会员注册后保持未激活，由站务在管理驾驶舱核验；审核记录不会因拒绝而删除。
- 一面通过后成为“预备会员”，二面通过后成为“科协会员”。预备会员及以上才会获得论坛 SSO。
- 固定职位为主席、硬件主席、软件主席、硬件副主席、软件副主席；主席和两类主席职位自动获得管理驾驶舱权限。
- 2026 招新 QQ 群：`1081376858`。

## 仓库结构

```text
web/
├── app/                   Django 官网与会员系统
│   ├── accounts/          注册、身份、等级与论坛 SSO
│   ├── recruitment/       招新批次、申请与面试流程
│   ├── news/ events/      公告与活动
│   ├── files/ projects/   资料站与项目档案
│   ├── dashboard/         管理驾驶舱
│   ├── templates/         页面模板
│   └── static/            CSS、JS 和图片
├── learn/electronics/     静态电子学学习中心
├── ops/                   Docker、Nginx、部署与备份脚本
│   └── forum/             NodeBB 配置与公共邮箱插件
└── docs/维护手册.md        维护与交接说明
```

## 本地开发

```bash
python -m venv .venv

# Windows
.venv/Scripts/pip install -r app/requirements.txt
.venv/Scripts/python app/manage.py migrate
.venv/Scripts/python app/manage.py runserver

# macOS / Linux 将 .venv/Scripts/python 换为 .venv/bin/python
```

开发配置使用 SQLite 和内存缓存，不需要本地 PostgreSQL。打开 <http://127.0.0.1:8000>，高级后台位于 `/admin/`。

提交前至少运行：

```bash
cd app
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test

cd ../ops/forum/plugins/nodebb-plugin-heuesta-mailbox
npm test
```

## 生产发布

日常流程为：提交并推送 `main`，在服务器先备份，再部署主站和论坛。

```bash
sudo /opt/heuesta/web/ops/backup.sh
sudo /opt/heuesta/web/ops/deploy.sh
sudo /opt/heuesta/web/ops/forum/deploy-forum.sh
```

部署脚本会完成代码更新、镜像构建、数据库迁移、静态文件收集、论坛组与私密版块权限同步，以及服务健康检查。注册、招新等动态页面禁止 CDN 缓存；静态二维码使用内容哈希文件名。

生产密钥只保存在服务器环境文件中，不得提交到仓库、群聊或工单。公共邮箱使用 Gmail IMAP 只读同步，应用专用密码仅保存在 `/opt/heuesta/forum.env`。

详细的审核、备份、论坛权限和故障处理流程见[维护手册](docs/维护手册.md)。本次正式招新发布核对项见[2026 招新发布说明](docs/2026招新发布说明.md)。

## 成员展示

已激活的科协会员及以上可在个人中心进入“设计我的展示”，自愿制作名片与个人页面，无需担任职位。先保存草稿、预览，再自行发布；随时可以撤回。官方职位和任期来自任命记录，不由成员自行填写。操作说明、素材保护和发布顺序见[成员展示维护说明](docs/成员展示维护说明.md)。

## 体验与帮助中心候选版

成员展示 v4、三类任务式帮助中心和质量门槛在候选分支中验收，尚未全部发布。网页帮助以 `/help/` 为入口，支持按任务搜索；管理内容及截图由服务端按权限过滤。离线三册从同一 Markdown 来源生成，不再维护两份不同正文。

当前实现、已验证范围、尚未完成项及下一步方向见[全站体验审计](docs/audit/2026-09-05-experience.md)；手册维护方式见[任务式帮助中心说明](docs/help/README.md)。CI 使用隔离 PostgreSQL 和本地浏览器测试账号，不向正式站写入演示数据。

## 技术栈

- Django 5.2 LTS、Python 3.12、PostgreSQL 16
- Django 模板与原生 CSS/JavaScript
- NodeBB 4、Node.js 22、自研公共邮箱插件
- Docker Compose、Nginx、HTTPS、CDN
