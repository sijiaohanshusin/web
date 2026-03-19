# 哈尔滨工程大学电子科技协会官网

这是哈尔滨工程大学电子科技协会（HEU ESTA）的官网仓库。当前线上域名为 [heuesta.cn](https://heuesta.cn)，现阶段用于协会官网页面的维护与发布。

## 仓库内容

仓库中的主要文件：

- `index.html`：网站首页
- `image_6662db.png`：协会会标图片
- `ops/`：部署和自动同步所需的运维文件

以下内容不会发布到线上站点：

- `index_v1.html`
- `科协招新综述/`
- `*.pem`
- `.gitignore`
- `.gitattributes`
- `README.md`
- `ops/`

## 技术说明

当前站点是静态页面，主要使用：

- HTML
- CSS
- JavaScript

线上环境使用：

- Ubuntu
- Nginx
- Cloudflare
- Let's Encrypt

## 本地预览

直接在浏览器中打开 `index.html` 即可查看页面效果。

如果需要边改边预览，可以在编辑器中使用本地静态服务器工具，例如 VS Code 的 `Live Server`。

## 线上部署

线上站点目录：

```text
/var/www/heuesta.cn/public
```

网站由 Nginx 提供服务，Cloudflare 负责外层代理与 DNS，HTTPS 由 Let's Encrypt 证书提供。

## 自动同步发布

服务器已配置自动同步任务，会定时从 GitHub 获取 `main` 分支最新内容，并同步到线上站点目录。

同步逻辑包括：

1. 获取 GitHub 上 `main` 分支的最新归档
2. 更新服务器上的源码缓存目录
3. 同步正式站点文件到线上目录
4. 自动排除资料文件、说明文件和运维文件
5. 校验并重载 Nginx

服务器上的相关文件：

```text
/usr/local/bin/heuesta-sync.sh
/etc/systemd/system/heuesta-sync.service
/etc/systemd/system/heuesta-sync.timer
```

常用运维命令：

```bash
sudo systemctl start heuesta-sync.service
sudo systemctl status heuesta-sync.service
sudo systemctl status heuesta-sync.timer
sudo systemctl list-timers --all | grep heuesta-sync
```

## 日常更新流程

推荐的更新方式：

1. 在本地修改站点文件
2. 提交并推送到 GitHub `main`
3. 等待服务器自动同步，或手动触发一次同步

## 维护说明

- 新增静态资源时，需要确认它们没有被同步脚本的排除规则过滤掉
- 如果后续站点结构调整，记得同步检查 `ops/heuesta-sync.sh` 中的发布规则
- 本仓库的运维说明仅覆盖官网相关内容