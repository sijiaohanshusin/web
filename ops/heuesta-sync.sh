#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/sijiaohanshusin/web.git"
BRANCH="main"
REPO_DIR="/opt/heuesta/repo"
WEB_ROOT="/var/www/heuesta.cn/public"

install -d -m 755 "$(dirname "$REPO_DIR")" "$WEB_ROOT"

if [ ! -d "$REPO_DIR/.git" ]; then
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$REPO_DIR"
else
    git -C "$REPO_DIR" fetch origin "$BRANCH"
    current_branch="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD || true)"
    if [ "$current_branch" != "$BRANCH" ]; then
        git -C "$REPO_DIR" checkout "$BRANCH"
    fi
    git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
fi

rsync -a --delete \
    --exclude ".git/" \
    --exclude ".gitignore" \
    --exclude "README.md" \
    --exclude "ops/" \
    --exclude "index_v1.html" \
    --exclude "科协招新综述/" \
    --exclude "*.pem" \
    "$REPO_DIR/" "$WEB_ROOT/"

find "$WEB_ROOT" -type d -exec chmod 755 {} +
find "$WEB_ROOT" -type f -exec chmod 644 {} +

nginx -t >/dev/null
systemctl reload nginx
