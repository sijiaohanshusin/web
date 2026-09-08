# Temporary Shared Mail

Independent read-only Gmail viewer mounted at `/shared-mail/`. Does not use the
main Django database, forum mailbox, member roles, or website session cookies.

## Boundaries

- Only mail received in INBOX after activation; newest 100 matching UIDs.
- Absolute one-calendar-month expiry, checked on every protected request and
  reinforced by a persistent systemd timer that returns HTTP 410 and stops this
  container. Gmail app-password revocation remains an owner action.
- IMAPS with certificate verification, read-only SELECT/EXAMINE, BODY.PEEK.
  Never SMTP, STORE, DELETE, CLOSE-with-expunge, APPEND, or EXPUNGE.
- Resolves only `imap.gmail.com` using AliDNS HTTPS (two-minute in-memory cache),
  with normal system resolution as fallback. Never changes host-wide DNS; TLS
  still verifies `imap.gmail.com`, not the resolved IP. Rejects private DNS answers.
- Each connection/read session has an 18-second total deadline and five-second
  socket limits. Unreachable cached DNS answers are dropped; failures show a
  retry message rather than indefinitely waiting on Gmail. Network access is not
  guaranteed merely because authentication succeeded once.
- Website visitor password is separately generated and PBKDF2-hashed. Gmail
  app password is broader than read-only and must never be given to visitors.
- Signed eight-hour access cookie scoped to `/shared-mail/`, separate CSRF cookie,
  secure/HTTP-only cookies, password-rotation invalidation, persistent login limits.
- No mail database, file attachments or remote images. Only short-lived in-memory
  headers (30 seconds), sanitized email HTML in a no-script sandbox, plaintext
  fallback, and attachment names. The original message's styling is not preserved.
- Messages over 5MB are not downloaded. HTML text is bounded to 300k characters.
- Login, message, error and body responses send private/no-store/noindex headers.

## Configuration

`SHARED_MAIL_CONFIG` points to an outside-repository JSON secret containing:
`account`, `app_password`, `password_hash`, `session_secret`, `starts_at`,
`expires_at`, and `rate_db`. The image contains no credentials. All dates are
timezone-aware ISO timestamps. Rate SQLite contains only salted IP hashes and
aggregate counters. The service has no user account registration or admin UI.

`setup_local.py` is an optional one-shot loopback form that sends a user-approved
app password via host-key-verified SSH to `provision_secret.py`. It verifies actual
IMAP login and read-only selection before creating a new server secret. It refuses
to overwrite an existing configuration. Visitor instructions are written only to
an explicitly supplied private local path, never this repository. Do not run the
setup form on a public interface.

## Tests And Deployment

```powershell
python -m unittest discover -s ops/shared-mail -p 'test_*.py' -v
```

Deploy using the reviewed `deploy.sh` from an isolated release directory. It pins
the existing main-site runtime image, runs tests without network, backs up Nginx,
starts only `heuesta-shared-mail` on loopback port 8012, validates/reloads Nginx,
and compares existing main/forum/database container identities and start times.
No dependency upgrades, main database migrations, DNS changes or forum restarts.

Verify EdgeOne returns no-store and never serves authenticated content to an
unauthenticated request; origin headers alone do not prove CDN configuration.
Before deployment, validate the live main SHA and port availability. Read-only
verification cannot demonstrate future message delivery: use an owner-sent test
email after activation to verify real receipt without importing historical mail.

## Rollback And Removal

The independent backup directory is recorded in `BACKUP_PATH`. To roll back,
stop the mailbox container, restore only the reviewed Nginx configuration from
that backup (account for any newer unrelated edits), run `nginx -t`, reload, and
disable the dedicated expiry timer. Do not roll back the main-site database or
restart the forum. Keep the secret private until the owner revokes the app
password. Do not extend expiry or import old mail without owner authorization.

Owners: anyone with the visitor password can read new mail, including verification
codes and account alerts. Share narrowly; do not use this Gmail account for private
mail during the shared period. Password withdrawal cannot recall already read or
copied messages. The website password is not a Google app password.
