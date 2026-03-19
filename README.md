# 哈尔滨工程大学电子科技协会官网

这是哈尔滨工程大学电子科技协会（HEU ESTA）的静态官网仓库。当前线上版本为备案期间使用的临时首页，域名为 [heuesta.cn](https://heuesta.cn)。

## 技术栈

- HTML5
- Tailwind CSS（CDN）
- Vanilla JavaScript
- Lucide Icons
- Google Fonts

## 仓库结构

- `index.html`
  线上首页入口文件
- `image_6662db.png`
  协会会标图片
- `ops/`
  服务器自动同步脚本与 `systemd` 配置样例

以下内容不参与线上站点发布：

- `index_v1.html`
- `科协招新综述/`
- `*.pem`

## 本地预览

直接在浏览器中打开 `index.html` 即可预览。

如果需要实时刷新，推荐在 VS Code 中使用 `Live Server`。

## 线上部署

线上环境当前采用：

- 阿里云 Ubuntu 24.04
- Nginx
- Cloudflare 代理
- Let's Encrypt HTTPS 证书

站点根目录：

```text
/var/www/heuesta.cn/public
```

Nginx 配置：

```text
/etc/nginx/sites-enabled/heuesta.cn
```

## GitHub 自动同步发布

服务器已改为定时从 GitHub 拉取并同步到站点目录，不再依赖本地手动上传。

同步逻辑：

1. 服务器将仓库克隆到 `/opt/heuesta/repo`
2. 定时执行 `git pull --ff-only origin main`
3. 使用 `rsync` 将生产文件同步到 `/var/www/heuesta.cn/public`
4. 排除不应公开的文件和目录
5. 自动校验并重载 Nginx

服务器上的关键文件：

```text
/usr/local/bin/heuesta-sync.sh
/etc/systemd/system/heuesta-sync.service
/etc/systemd/system/heuesta-sync.timer
```

手动触发一次同步：

```bash
sudo systemctl start heuesta-sync.service
```

查看定时器状态：

```bash
sudo systemctl status heuesta-sync.timer
sudo systemctl list-timers --all | grep heuesta-sync
```

## 更新流程

推荐的日常维护方式：

1. 在本地修改 `index.html` 或相关静态资源
2. 提交并推送到 GitHub `main`
3. 等待服务器定时同步，或手动执行一次同步服务

## 注意事项

- 当前 `frps` 已从 `443` 改到 `7443`
- 如果 Minecraft 穿透客户端仍在使用旧端口，需要同步改为 `7443`
- 如果未来新增线上静态资源，请放在仓库中并确保未被 `ops/heuesta-sync.sh` 的排除规则过滤
