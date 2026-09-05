# Mailbox Verification

Run `npm ci` and `npm test` with Node.js 22 or newer and OpenSSL on PATH.
Dependencies stay pinned to the deployed versions. No mail credentials are needed.

## Test Layers

- Unit tests cover permissions, rendering, sanitization, parsing, cursor updates, and safe errors.
- `imap-transport.test.js` uses the real pinned ImapFlow client over a loopback TLS socket.
- `scripts/forum_fixture/library.js` reuses that transport in the disposable NodeBB/PostgreSQL CI job. It verifies transport, parsing, durable archiving, and browser access together.

The IMAP fixture binds only to `127.0.0.1` on an ephemeral port. It generates a temporary one-day certificate and synthetic password, trusts that certificate only in its test client, and removes the temporary files when closed. A separate test confirms an untrusted certificate is rejected. Production TLS settings and the fixed Gmail host are not weakened.

The server implements only the protocol subset requested by the pinned client: capability discovery, SASL PLAIN, folder listing, read-only EXAMINE, UID FETCH with body literals, NOOP, and LOGOUT. Unsupported commands or body parts fail assertions. Transcripts exclude authentication payloads and contain synthetic data only. Tests verify that text reads use BODY.PEEK and never request attachments, a full message body, or write operations.

Coverage includes baseline-only startup, nested MIME and single-part HTML, Chinese headers, sender plus-tags, date ordering, Gmail message ID deduplication, reconnects, missing retry messages, UIDVALIDITY reset, credential rejection, and interrupted downloads. The store used in transport-only tests is in memory; persistence claims rely on the separate real PostgreSQL/NodeBB job.

This is not a Gmail emulator or a claim of successful delivery through Gmail. It does not validate public DNS, Google availability, real account authorization, the entire IMAP protocol, or production network connectivity. It deliberately makes no external mail requests.

Protocol references: [IMAP4rev1](https://www.rfc-editor.org/rfc/rfc3501.html), [ImapFlow client API](https://imapflow.com/docs/api/imapflow-client/). Exact command behavior is checked against the locally pinned ImapFlow source, not a newer dependency version.
