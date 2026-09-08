# Shared mailbox acceptance, 2026-09-08

- Public route: `https://heuesta.cn/shared-mail/`.
- Scope: independent visitor-password-protected, read-only Gmail INBOX. Old mail
  excluded using INTERNALDATE, not sender-controlled Date. Latest visible count: 0.
- Expiry: 2026-10-08 19:19 Asia/Shanghai. Server-side request gate and persistent
  systemd timer enabled; the timer changes this route to 410 and stops only this
  container. Gmail app password still needs owner revocation afterwards.
- 22 isolated tests pass locally and inside the deployment image. Covers CSRF,
  authentication, expiry (including during fetch), logout, rotation, rate limiting,
  UID/UIDVALIDITY scope, HTML/MIME safety, no-cache headers, TLS identity, encrypted
  DNS, oversized mail, total deadlines and bounded lock waits.
- Real Gmail IMAPS login and EXAMINE succeeded from the production host and
  isolated container. System DNS returned an unreachable address during setup;
  scoped AliDNS HTTPS resolution resolved it without global DNS changes or TLS
  verification bypass. Google access still showed intermittent timeouts. Added
  an 18-second per-session deadline and a one-second queue limit.
- Live HTTPS checks through EdgeOne passed: visitor login, actual empty INBOX,
  no-store headers, anonymous rejection immediately after authenticated reads,
  logout rejection, main homepage/team/forum HTTP 200. Observed EO cache MISS.
- Browser fixture checks use the exact same templates and sanitizer, with fake
  local-only messages: desktop login/list/body/logout and 390/320px viewport
  frames. Mobile password form is first. No live demo emails were created.
- Browser form testing found a Referrer-Policy / CSRF incompatibility, fixed by
  same-origin referrers on application forms; sandboxed email bodies retain
  no-referrer and no-script restrictions. CSRF remains enabled.
- The in-app browser's production navigation timed out on this machine; direct
  public HTTPS tests succeeded, then were repeated successfully from the server
  through EdgeOne after a local TLS connection failure. This is not evidence of
  a real-device/mobile-browser test or of guaranteed availability on every network.
- Main website, NodeBB and PostgreSQL container IDs/start times unchanged. No
  main database changes, dependency upgrades, DNS/certificate changes or forum
  restart. Existing runtime image reused; new service memory approximately 55MB.
- Nginx backup and rollback image retained. Optional Nginx include in the tracked
  deployment template preserves the mailbox route during later main-site releases.
- Credentials were not committed. Gmail credential stored in a root-protected
  host directory and mounted read-only. Visitor instructions saved separately to
  an owner-only local file. No mail-body/credential logging or persistent mail store.

Remaining user check: send a new message to the shared Gmail account and refresh
the inbox. Authentication and empty-inbox reads are verified; an actual new-mail
arrival has not been demonstrated because no test message was sent on the user's
behalf. Only share the visitor password with intended readers.
