#!/usr/bin/env bash
# HEU ESTA 官网部署脚本（在服务器上执行）
# 用法：sudo /opt/heuesta/web/ops/deploy.sh
# 幂等：可重复执行；每次执行 = 拉最新代码 + 重建容器 + 同步学习中心 + 重载 nginx
#
# 注：服务器直连 github git 协议不通，但 codeload tarball 通道可用，
#     故通过下载归档来更新代码（与旧版 heuesta-sync 相同的通道）。
#     **按提交号下载，不按分支名** —— 分支名归档有 CDN 缓存，会静默装成旧版本，
#     理由与那次事故写在下面下载那一段。装了哪个提交会写进 /opt/heuesta/DEPLOYED_SHA，
#     `ops/verify.sh` 拿它和 GitHub 上的 main 对账。
set -euo pipefail

REPO_DIR=/opt/heuesta/web
ENV_FILE=/opt/heuesta/.env
BRANCH=main
GH_REPO=sijiaohanshusin/web
BRANCH_URL="https://codeload.github.com/$GH_REPO/tar.gz/refs/heads/$BRANCH"
COMPOSE="docker compose -f $REPO_DIR/ops/docker-compose.yml --env-file $ENV_FILE"
SHA_FILE=/opt/heuesta/DEPLOYED_SHA

if [ ! -f "$ENV_FILE" ]; then
    echo "缺少 $ENV_FILE，请先从 ops/env.example 复制并填写" >&2
    exit 1
fi

# ============================================================================
# 下载代码。**按提交号下载，不按分支名下载。**
#
# 踩过一次线上事故：推完立刻部署，`deploy.sh` 打印「部署完成」、`verify.sh` 全绿，
# 而线上跑的还是**上一个提交** —— 因为 `tar.gz/refs/heads/main` 这个 URL 是
# 按分支名取的，GitHub 的 CDN 会缓存它几分钟。于是「部署成功」这件事根本不能
# 证明「我刚推的东西上线了」，而没有任何一条检查会红。
#
# 按提交号取的归档（`tar.gz/<sha>`）是**不可变**的，不存在这个问题。
# 所以先问一次 API 把 main 解析成 sha，再按 sha 下载。
# API 万一不通就退回按分支名下载，但要**大声警告**并且不写 SHA_FILE ——
# 宁可让人知道「这一次无法确认版本」，也不要静默地装一个旧版本。
# ============================================================================
echo "==> 解析 $BRANCH 的提交号"
sha=""
if api=$(curl -fsS --connect-timeout 10 --retry 2 \
         "https://api.github.com/repos/$GH_REPO/commits/$BRANCH" 2>/dev/null); then
    # 响应里第一个 40 位十六进制就是这次提交的 sha（不用 jq，服务器上没有）。
    # **`|| true` 是必需的**：脚本开头是 `set -euo pipefail`，grep 没匹配到会退 1，
    # 加上 pipefail 整条管道判失败 → 赋值失败 → set -e 直接把部署中断。
    # 这里「取不到 sha」是一个要走降级分支的正常情况，不是错误。
    sha=$(grep -oiE '[0-9a-f]{40}' <<<"$api" | head -n 1 || true)
fi

tmp_archive=$(mktemp /tmp/heuesta-web.XXXXXX.tar.gz)
tmp_dir=$(mktemp -d /tmp/heuesta-web-src.XXXXXX)
cleanup() { rm -f "$tmp_archive"; rm -rf "$tmp_dir"; }
trap cleanup EXIT

if [ -n "$sha" ]; then
    echo "  $BRANCH = $sha"
    url="https://codeload.github.com/$GH_REPO/tar.gz/$sha"
else
    echo "  !! 取不到提交号（api.github.com 不通？），退回按分支名下载。" >&2
    echo "  !! 分支归档有 CDN 缓存，**这一次不能保证装的是最新提交** ——" >&2
    echo "  !! 部署完请手动核对，或过几分钟再跑一次。" >&2
    url="$BRANCH_URL"
fi

curl --fail --location --retry 5 --retry-delay 5 --connect-timeout 15 \
    --output "$tmp_archive" "$url"
tar -xzf "$tmp_archive" -C "$tmp_dir"
extracted_dir=$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)

install -d -m 755 "$REPO_DIR"
rsync -a --delete "$extracted_dir/" "$REPO_DIR/"
chmod +x "$REPO_DIR"/ops/*.sh
# 记下这次到底装了哪个提交，给 verify.sh 对账用。取不到 sha 时把文件删掉，
# 而不是写一个假值 —— verify.sh 那边会因此报「版本无法确认」。
if [ -n "$sha" ]; then printf '%s\n' "$sha" > "$SHA_FILE"; else rm -f "$SHA_FILE"; fi

echo "==> 准备目录"
install -d -m 755 /srv/heuesta/static /srv/heuesta/media /srv/heuesta/pgdata /srv/heuesta/backups /srv/heuesta/site
# 容器内 appuser uid=1000 需要写入 static/media
chown -R 1000:1000 /srv/heuesta/static /srv/heuesta/media

echo "==> 同步学习中心静态文件"
rsync -a --delete "$REPO_DIR/learn/" /srv/heuesta/site/learn/
find /srv/heuesta/site -type d -exec chmod 755 {} +
find /srv/heuesta/site -type f -exec chmod 644 {} +

echo "==> 构建并启动容器"
$COMPOSE build
$COMPOSE up -d

echo "==> 等待应用就绪"
for i in $(seq 1 60); do
    if curl -fsS -o /dev/null -H "Host: heuesta.cn" http://127.0.0.1:8001/; then
        echo "应用已就绪"
        break
    fi
    if [ "$i" = 60 ]; then
        echo "应用启动超时，查看日志：$COMPOSE logs app" >&2
        exit 1
    fi
    sleep 2
done

echo "==> 更新 nginx 配置"
cp "$REPO_DIR/ops/nginx/heuesta.cn.conf" /etc/nginx/sites-available/heuesta.cn
ln -sf /etc/nginx/sites-available/heuesta.cn /etc/nginx/sites-enabled/heuesta.cn
nginx -t
systemctl reload nginx

echo "==> 安装/刷新定时器（每日备份 + 活动开场提醒）"
cp "$REPO_DIR/ops/heuesta-backup.service" "$REPO_DIR/ops/heuesta-backup.timer" \
   "$REPO_DIR/ops/heuesta-event-reminder.service" "$REPO_DIR/ops/heuesta-event-reminder.timer" \
   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now heuesta-backup.timer >/dev/null 2>&1 || true
systemctl enable --now heuesta-event-reminder.timer >/dev/null 2>&1 || true

if [ -n "$sha" ]; then
    echo "==> 部署完成：https://heuesta.cn （提交 $sha）"
else
    echo "==> 部署完成：https://heuesta.cn （**提交号未确认**，见上面的警告）"
fi
