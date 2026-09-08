#!/bin/bash
set -euo pipefail
exec 9>/opt/heuesta/release.lock
flock -n 9 || { echo 'Another deployment is active'; exit 1; }
cd /opt/heuesta/shared-mail/release
test -f /opt/heuesta/shared-mail/secrets/config.json
test "$(cat /opt/heuesta/DEPLOYED_SHA)" = '6ed8255fdf0e35db1aaa1c4f8fe1330eee39a7ca'
test -z "$(docker ps -aq --filter name=^heuesta-shared-mail$)"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/srv/heuesta/backups/shared-mail-$stamp
install -d -m 700 "$backup"
cp -a /etc/nginx/sites-available/heuesta.cn "$backup/heuesta.cn"
docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' heuesta-app-1 heuesta-forum-forum-1 heuesta-db-1 > "$backup/existing-containers.txt"
install -d -o 1000 -g 1000 -m 700 /opt/heuesta/shared-mail/data
docker build -f ops/shared-mail/Dockerfile -t heuesta-shared-mail:20260908 .
docker run --rm --network none --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  heuesta-shared-mail:20260908 python -m unittest discover -s /shared-mail -p 'test_*.py'
docker run -d --name heuesta-shared-mail --restart unless-stopped \
  --memory 160m --cpus .6 --pids-limit 80 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  --log-opt max-size=1m --log-opt max-file=2 -p 127.0.0.1:8012:8000 \
  -v /opt/heuesta/shared-mail/secrets/config.json:/run/secrets/shared-mail.json:ro \
  -v /opt/heuesta/shared-mail/data:/data \
  heuesta-shared-mail:20260908
for attempt in $(seq 1 15); do
  if curl -fsS -H 'Host: heuesta.cn' http://127.0.0.1:8012/shared-mail/ >/dev/null; then break; fi
  sleep 1
done
curl -fsS -H 'Host: heuesta.cn' http://127.0.0.1:8012/shared-mail/ >/dev/null
install -m 644 ops/shared-mail/nginx-location.conf /etc/nginx/snippets/heuesta-shared-mail.conf
install -m 700 ops/shared-mail/expire.py /opt/heuesta/shared-mail/expire.py
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/nginx/sites-available/heuesta.cn')
s = p.read_text()
needle = '    server_name heuesta.cn;'
assert s.count(needle) == 2  # HTTPS virtual host first, HTTP redirect host second.
if 'include /etc/nginx/snippets/heuesta-shared-mail' not in s:
    p.write_text(s.replace(needle, needle + '\n    include /etc/nginx/snippets/heuesta-shared-mail.conf;', 1))
PY
if ! nginx -t; then
  cp -a "$backup/heuesta.cn" /etc/nginx/sites-available/heuesta.cn
  docker stop heuesta-shared-mail
  exit 1
fi
nginx -s reload
python3 - <<'PY'
from datetime import datetime, timezone
import json
from pathlib import Path
c = json.loads(Path('/opt/heuesta/shared-mail/secrets/config.json').read_text())
end = datetime.fromisoformat(c['expires_at']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
Path('/etc/systemd/system/heuesta-shared-mail-expiry.service').write_text('[Unit]\nDescription=Stop temporary shared mailbox\nAfter=docker.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /opt/heuesta/shared-mail/expire.py\n')
Path('/etc/systemd/system/heuesta-shared-mail-expiry.timer').write_text('[Unit]\nDescription=Temporary shared mailbox expiry\n[Timer]\nOnCalendar=' + end + '\nPersistent=true\nUnit=heuesta-shared-mail-expiry.service\n[Install]\nWantedBy=timers.target\n')
PY
systemctl daemon-reload
systemctl enable --now heuesta-shared-mail-expiry.timer
docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' heuesta-app-1 heuesta-forum-forum-1 heuesta-db-1 > "$backup/existing-containers-after.txt"
diff "$backup/existing-containers.txt" "$backup/existing-containers-after.txt"
printf '%s\n' "$backup" > /opt/heuesta/shared-mail/BACKUP_PATH
date -u +%FT%TZ > /opt/heuesta/shared-mail/DEPLOYED_AT
echo 'ISOLATED_SHARED_MAIL_DEPLOYED'
