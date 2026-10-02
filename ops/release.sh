#!/usr/bin/env bash
# Immutable candidate -> database/readiness checks -> switch -> verify, with code/image rollback.
# Usage: sudo bash ops/release.sh <full 40-character commit SHA>
# This release path deliberately does not install, change or run backup services.
set -Eeuo pipefail

sha=${1:-}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'A full commit SHA is required; branch archives are not accepted.' >&2; exit 2; }
ROOT=${HEUESTA_ROOT:-/opt/heuesta}
DATA=${HEUESTA_DATA_ROOT:-/srv/heuesta}
ENV_FILE=${HEUESTA_ENV_FILE:-$ROOT/.env}
REPO_DIR=$ROOT/web
RELEASE=$ROOT/releases/$sha
DOMAIN=${HEUESTA_DOMAIN:-heuesta.cn}
APP_PORT=${HEUESTA_PORT:-8001}
CANDIDATE_PORT=${HEUESTA_CANDIDATE_PORT:-18001}
NETWORK=${HEUESTA_NETWORK:-heuesta_default}
DB_HOST=${POSTGRES_HOST:-db}
APP_CONTAINER=${HEUESTA_APP_CONTAINER:-heuesta-app-1}
NGINX_FILE=${HEUESTA_NGINX_FILE:-/etc/nginx/sites-available/heuesta.cn}
GH_REPO=${HEUESTA_GH_REPO:-sijiaohanshusin/web}
IMAGE=heuesta-app:$sha
CANDIDATE=heuesta-candidate
[[ -r "$ENV_FILE" && -d "$REPO_DIR" ]] || { echo 'Existing source and environment file are required.' >&2; exit 2; }
exec 9>"$ROOT/release.lock"
flock -n 9 || { echo 'Another release is running.' >&2; exit 2; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
state=$ROOT/releases/release-$stamp
mkdir -p "$state"
chmod 700 "$state"
old_sha=$(cat "$ROOT/DEPLOYED_SHA")
old_image=$(docker inspect "$APP_CONTAINER" --format '{{.Image}}')
old_source=$(readlink -f "$REPO_DIR")
docker tag "$old_image" "heuesta-app:rollback-$stamp"
cp "$NGINX_FILE" "$state/nginx.previous"
printf '%s\n' "$old_sha" > "$state/previous-sha"
printf '%s\n' "$old_image" > "$state/previous-image"
printf '%s\n' "$old_source" > "$state/previous-source"
export HEUESTA_ENV_FILE="$ENV_FILE" HEUESTA_DATA_ROOT="$DATA"
export HEUESTA_PORT="$APP_PORT" POSTGRES_HOST="$DB_HOST"
switched=0

compose() { docker compose --project-name heuesta --env-file "$ENV_FILE" -f "$REPO_DIR/ops/docker-compose.yml" "$@"; }
ready() {
    local port=$1
    for _ in $(seq 1 45); do
        if curl -fsS --max-time 4 -H "Host: $DOMAIN" "http://127.0.0.1:$port/health/ready/" >/dev/null; then return 0; fi
        sleep 2
    done
    return 1
}
cleanup() { docker rm -f "$CANDIDATE" >/dev/null 2>&1 || true; }
rollback() {
    local code=$?
    trap - ERR
    cleanup
    if [[ "$switched" == 1 ]]; then
        echo 'Release failed: restoring previous source, image and nginx configuration.' >&2
        ln -sfn "$old_source" "$REPO_DIR"
        cp "$state/nginx.previous" "$NGINX_FILE"
        export HEUESTA_APP_IMAGE="$old_image"
        # Previous compose may not declare image:; an override guarantees the exact image.
        printf 'services:\n  app:\n    image: %s\n  honor-ai-worker:\n    image: %s\n' "$old_image" "$old_image" > "$state/rollback.yml"
        compose -f "$state/rollback.yml" --profile honor-ai up -d --no-build --no-deps app honor-ai-worker || true
        nginx -t && systemctl reload nginx
        printf '%s\n' "$old_sha" > "$ROOT/DEPLOYED_SHA"
    fi
    echo "Release stopped. Review $state; no database migration was applied." >&2
    exit "$code"
}
trap cleanup EXIT
trap rollback ERR

if [[ ! -d "$RELEASE" ]]; then
    mkdir -p "$RELEASE"
    curl -fL --retry 3 --connect-timeout 15 --max-time 180 \
        "https://codeload.github.com/$GH_REPO/tar.gz/$sha" -o "$state/source.tar.gz"
    tar -xzf "$state/source.tar.gz" --strip-components=1 -C "$RELEASE"
    printf '%s\n' "$sha" > "$RELEASE/.source-sha"
fi
[[ -f "$RELEASE/.source-sha" && $(cat "$RELEASE/.source-sha") == "$sha" ]]
[[ -f "$RELEASE/ops/Dockerfile" && -f "$RELEASE/app/manage.py" ]]
docker build --label "org.opencontainers.image.revision=$sha" -t "$IMAGE" -f "$RELEASE/ops/Dockerfile" "$RELEASE"
[[ $(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}') == "$sha" ]]

# Candidate uses a separate static directory and a read-only media mount.
# Its entrypoint is bypassed, so validation cannot migrate the production schema.
mkdir -p "$state/static"
chown 1000:1000 "$state/static"
chmod 755 "$state" "$state/static"
docker run --rm --network "$NETWORK" --env-file "$ENV_FILE" -e POSTGRES_HOST="$DB_HOST" \
    --entrypoint python "$IMAGE" manage.py migrate --check
docker run --rm --network "$NETWORK" --env-file "$ENV_FILE" -e POSTGRES_HOST="$DB_HOST" \
    -v "$state/static:/app/staticfiles" --entrypoint python "$IMAGE" manage.py collectstatic --noinput
docker run -d --name "$CANDIDATE" --network "$NETWORK" --env-file "$ENV_FILE" -e POSTGRES_HOST="$DB_HOST" \
    --memory "${HEUESTA_CANDIDATE_MEMORY:-300m}" -p "127.0.0.1:$CANDIDATE_PORT:8000" \
    -v "$DATA/media:/app/media:ro" -v "$state/static:/app/staticfiles:ro" \
    --entrypoint gunicorn "$IMAGE" config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 2
ready "$CANDIDATE_PORT"
for path in / /recruit/ /resources/ /recruitment/ /accounts/register/ /sitemap.xml; do
    curl -fsS --max-time 15 -H "Host: $DOMAIN" "http://127.0.0.1:$CANDIDATE_PORT$path" -o /dev/null
done
if [[ "${HEUESTA_CANDIDATE_ONLY:-0}" == 1 ]]; then
    echo "Candidate verified without switching production: $sha ($state)"
    exit 0
fi
cleanup

# Hash-named assets from the old release stay available for open tabs and rollback.
rsync -a "$state/static/" "$DATA/static/"
if [[ ! -L "$REPO_DIR" ]]; then
    old_source=$ROOT/releases/previous-$old_sha-$stamp
    mv "$REPO_DIR" "$old_source"
    printf '%s\n' "$old_source" > "$state/previous-source"
fi
switched=1
ln -sfn "$RELEASE" "$REPO_DIR"
export HEUESTA_APP_IMAGE="$IMAGE"
compose --profile honor-ai up -d --no-build --no-deps app honor-ai-worker
ready "$APP_PORT"
[[ $(docker inspect "$APP_CONTAINER" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}') == "$sha" ]]

# Existing TLS certificates are referenced by the repository configuration.
sed -e "s|/srv/heuesta|$DATA|g" -e "s|127.0.0.1:8001|127.0.0.1:$APP_PORT|g" \
    "$REPO_DIR/ops/nginx/heuesta.cn.conf" > "$NGINX_FILE"
nginx -t
systemctl reload nginx
curl -fsS --max-time 15 --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" -o /dev/null
status=$(curl -sS --max-time 10 --resolve "$DOMAIN:443:127.0.0.1" -o /dev/null -w '%{http_code}' "https://$DOMAIN/health/ready/")
[[ "$status" == 404 ]]
printf '%s\n' "$sha" > "$ROOT/DEPLOYED_SHA"

# Install only the new snapshot refresher. Backup services are outside this release.
sed "s|heuesta-app-1|$APP_CONTAINER|g" "$REPO_DIR/ops/heuesta-bilibili.service" > /etc/systemd/system/heuesta-bilibili.service
cp "$REPO_DIR/ops/heuesta-bilibili.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now heuesta-bilibili.timer
printf '%s\n' "$IMAGE" > "$ROOT/DEPLOYED_IMAGE"
echo "Released $sha. Recovery metadata: $state"
