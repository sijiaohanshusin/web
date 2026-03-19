#!/usr/bin/env bash
set -euo pipefail

REPO_ARCHIVE_URL="https://codeload.github.com/sijiaohanshusin/web/tar.gz/refs/heads/main"
WORK_DIR="/opt/heuesta"
SOURCE_DIR="$WORK_DIR/source"
WEB_ROOT="/var/www/heuesta.cn/public"

tmp_archive="$(mktemp /tmp/heuesta.XXXXXX.tar.gz)"
tmp_dir="$(mktemp -d /tmp/heuesta-src.XXXXXX)"

cleanup() {
    rm -f "$tmp_archive"
    rm -rf "$tmp_dir"
}
trap cleanup EXIT

install -d -m 755 "$WORK_DIR" "$SOURCE_DIR" "$WEB_ROOT"

curl --fail --location --retry 5 --retry-delay 5 --connect-timeout 15 \
    --output "$tmp_archive" "$REPO_ARCHIVE_URL"

tar -xzf "$tmp_archive" -C "$tmp_dir"

extracted_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "$extracted_dir" ]; then
    echo "Failed to extract GitHub archive" >&2
    exit 1
fi

rsync -a --delete "$extracted_dir/" "$SOURCE_DIR/"

rsync -a --delete \
    --exclude ".git/" \
    --exclude ".gitignore" \
    --exclude ".gitattributes" \
    --exclude "README.md" \
    --exclude "ops/" \
    --exclude "index_v1.html" \
    --exclude "科协招新综述/" \
    --exclude "*.pem" \
    "$SOURCE_DIR/" "$WEB_ROOT/"

rm -f "$WEB_ROOT/.gitignore" "$WEB_ROOT/.gitattributes" "$WEB_ROOT/README.md" "$WEB_ROOT/index_v1.html"
rm -rf "$WEB_ROOT/ops" "$WEB_ROOT/科协招新综述"
find "$WEB_ROOT" -maxdepth 1 -type f -name "*.pem" -delete

find "$WEB_ROOT" -type d -exec chmod 755 {} +
find "$WEB_ROOT" -type f -exec chmod 644 {} +

nginx -t >/dev/null
systemctl reload nginx