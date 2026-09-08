#!/bin/bash
set -euo pipefail
exec 9>/opt/heuesta/release.lock
flock -n 9
cd /opt/heuesta/shared-mail/release
test -f /opt/heuesta/shared-mail/secrets/config.json
test "$(docker inspect --format '{{.Config.Image}}' heuesta-shared-mail)" = heuesta-shared-mail:20260908
before=$(docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' heuesta-app-1 heuesta-forum-forum-1 heuesta-db-1)
docker tag heuesta-shared-mail:20260908 heuesta-shared-mail:rollback-before-csrf
docker build -f ops/shared-mail/Dockerfile -t heuesta-shared-mail:20260908 .
docker run --rm --network none --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  heuesta-shared-mail:20260908 python -m unittest discover -s /shared-mail -p 'test_*.py'
docker stop heuesta-shared-mail
docker rm heuesta-shared-mail
docker run -d --name heuesta-shared-mail --restart unless-stopped \
  --memory 160m --cpus .6 --pids-limit 80 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  --log-opt max-size=1m --log-opt max-file=2 -p 127.0.0.1:8012:8000 \
  -v /opt/heuesta/shared-mail/secrets/config.json:/run/secrets/shared-mail.json:ro \
  -v /opt/heuesta/shared-mail/data:/data heuesta-shared-mail:20260908
for attempt in $(seq 1 15); do
  if curl -fsS -H 'Host: heuesta.cn' http://127.0.0.1:8012/shared-mail/ >/dev/null; then break; fi
  sleep 1
done
curl -fsS -H 'Host: heuesta.cn' http://127.0.0.1:8012/shared-mail/ >/dev/null
after=$(docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' heuesta-app-1 heuesta-forum-forum-1 heuesta-db-1)
test "$before" = "$after"
echo 'SHARED_MAIL_UPDATED_MAIN_FORUM_DB_UNCHANGED'
