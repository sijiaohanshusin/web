#!/usr/bin/env bash
# Roll back code/image/config only. The release path refuses schema migrations.
set -euo pipefail
ROOT=${HEUESTA_ROOT:-/opt/heuesta}
state=$(realpath "${1:?Pass the release metadata directory printed by release.sh}")
[[ "$state" == "$ROOT"/releases/release-* && -f "$state/previous-image" ]]
exec 9>"$ROOT/release.lock"
flock -n 9
source_dir=$(cat "$state/previous-source")
image=$(cat "$state/previous-image")
sha=$(cat "$state/previous-sha")
[[ -d "$source_dir" && "$sha" =~ ^[0-9a-f]{40}$ ]]
docker image inspect "$image" >/dev/null
[[ -L "$ROOT/web" ]]
ln -sfn "$source_dir" "$ROOT/web"
printf 'services:\n  app:\n    image: %s\n  honor-ai-worker:\n    image: %s\n' "$image" "$image" > "$state/rollback.yml"
docker compose --project-name heuesta --env-file "${HEUESTA_ENV_FILE:-$ROOT/.env}" \
    -f "$ROOT/web/ops/docker-compose.yml" -f "$state/rollback.yml" \
    --profile honor-ai up -d --no-build --no-deps app honor-ai-worker
cp "$state/nginx.previous" "${HEUESTA_NGINX_FILE:-/etc/nginx/sites-available/heuesta.cn}"
nginx -t
systemctl reload nginx
for _ in $(seq 1 45); do
    if curl -fsS --max-time 4 -H "Host: ${HEUESTA_DOMAIN:-heuesta.cn}" "http://127.0.0.1:${HEUESTA_PORT:-8001}/" >/dev/null; then
        [[ $(docker inspect "${HEUESTA_APP_CONTAINER:-heuesta-app-1}" --format '{{.Image}}') == "$image" ]]
        printf '%s\n' "$sha" > "$ROOT/DEPLOYED_SHA"
        printf '%s\n' "$image" > "$ROOT/DEPLOYED_IMAGE"
        # Older images have no refresh command. Disable only this newly added timer.
        if [[ ! -f "$ROOT/web/app/core/management/commands/refresh_bilibili.py" ]]; then
            systemctl disable --now heuesta-bilibili.timer
        fi
        echo "Restored $sha and its exact previous image."
        exit 0
    fi
    sleep 2
done
echo 'Rollback container did not become ready; inspect application logs.' >&2
exit 1
