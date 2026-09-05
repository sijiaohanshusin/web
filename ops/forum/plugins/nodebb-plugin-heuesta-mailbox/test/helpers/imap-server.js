'use strict';

// Deliberately small, strict IMAP fixture. Never listens outside loopback or contacts Gmail.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const tls = require('node:tls');
const { GmailImap, EXPECTED_ACCOUNT } = require('../../lib/imap');

const quoted = value => `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
const encoded = value => `=?UTF-8?B?${Buffer.from(value).toString('base64')}?=`;

function syntheticMail(uid, options = {}) {
	const sender = options.sender || 'Sender.One+test@example.invalid';
	const name = options.name || '手册演示发件人';
	const subject = options.subject || '手册演示：活动安排';
	const body = options.body || '这是一封隔离环境的合成邮件，不包含真实邮箱内容。';
	const html = options.html || '<h2>手册演示</h2><p>活动安排仅用于验证私密版块。</p><script>alert(1)</script><img src="https://tracking.invalid/pixel">';
	const parts = new Map();
	function textPart(part, subtype, value) {
		const data = Buffer.from(Buffer.from(value).toString('base64'));
		parts.set(part, data);
		parts.set(`${part}.MIME`, Buffer.from(`Content-Type: text/${subtype}; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n`));
		return `("TEXT" "${subtype.toUpperCase()}" ("CHARSET" "UTF-8") NIL NIL "BASE64" ${data.length} 1 NIL NIL NIL NIL)`;
	}
	let structure;
	if (options.htmlOnly) {
		structure = textPart('TEXT', 'html', html);
		parts.set('HEADER', parts.get('TEXT.MIME'));
		parts.delete('TEXT.MIME');
	} else {
		const plain = textPart('1.1', 'plain', body);
		const rich = textPart('1.2', 'html', html);
		const attachment = '("APPLICATION" "PDF" ("NAME" "fixture.pdf") NIL NIL "BASE64" 1024 NIL ("ATTACHMENT" ("FILENAME" "fixture.pdf")) NIL NIL)';
		structure = `((${plain} ${rich} "ALTERNATIVE") ${attachment} "MIXED")`;
	}
	const [local, domain] = sender.split('@');
	const address = `((${quoted(encoded(name))} NIL ${quoted(local)} ${quoted(domain)}))`;
	const envelope = `(NIL ${quoted(encoded(subject))} ${address} ${address} ${address} NIL NIL NIL NIL ${quoted(`<fixture-${uid}@example.invalid>`)})`;
	return {
		uid, id: String(options.id || (9000000000000000000n + BigInt(uid))),
		date: options.date || new Date(Date.now() + 60000 + uid * 1000),
		parts, structure, envelope,
	};
}

function imapDate(date) {
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const pad = value => String(value).padStart(2, '0');
	return `${pad(date.getUTCDate())}-${months[date.getUTCMonth()]}-${date.getUTCFullYear()} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} +0000`;
}

class ImapTestServer {
	constructor() {
		this.password = [...randomBytes(16)].map(value => String.fromCharCode(97 + value % 26)).join('');
		this.messages = [];
		this.uidValidity = 123;
		this.uidNext = 1;
		this.commands = [];
		this.unexpected = [];
		this.sockets = new Set();
		this.connections = 0;
		this.authAttempts = 0;
		this.rejectAuth = false;
		this.dropGreetings = 0;
		this.failBodyOnce = new Set();
		this.dropBodyOnce = new Set();
	}

	add(mail) {
		assert.ok(Number.isSafeInteger(mail.uid) && mail.uid > 0);
		assert.ok(!this.messages.some(item => item.uid === mail.uid));
		this.messages.push(mail);
		this.messages.sort((a, b) => a.uid - b.uid);
		this.uidNext = Math.max(this.uidNext, mail.uid + 1);
		return mail;
	}

	async start() {
		this.directory = fs.mkdtempSync(path.join(os.tmpdir(), 'heuesta-imap-test-'));
		try {
			execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
				'-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
				'-keyout', path.join(this.directory, 'key.pem'), '-out', path.join(this.directory, 'cert.pem')], { stdio: 'ignore' });
			this.cert = fs.readFileSync(path.join(this.directory, 'cert.pem'));
			this.server = tls.createServer({
				key: fs.readFileSync(path.join(this.directory, 'key.pem')), cert: this.cert, minVersion: 'TLSv1.2',
			}, socket => this.accept(socket));
			this.server.on('tlsClientError', () => {});
			await new Promise((resolve, reject) => {
				this.server.once('error', reject);
				this.server.listen(0, '127.0.0.1', resolve);
			});
			return this;
		} catch (error) {
			await this.close();
			throw error;
		}
	}

	client({ trusted = true, attempts = 3 } = {}) {
		assert.equal(this.server.address().address, '127.0.0.1');
		const imap = new GmailImap({ appPassword: this.password, retryDelayMs: 0, connectAttempts: attempts });
		imap.host = '127.0.0.1';
		imap.port = this.server.address().port;
		const original = imap.createClient.bind(imap);
		imap.createClient = () => {
			const client = original();
			client.servername = 'localhost';
			client.options.servername = 'localhost';
			if (trusted) client.options.tls.ca = this.cert;
			client.options.connectionTimeout = 2000;
			client.options.greetingTimeout = 1000;
			client.socketTimeout = 3000;
			return client;
		};
		return imap;
	}

	accept(socket) {
		this.connections += 1;
		this.sockets.add(socket);
		socket.on('close', () => this.sockets.delete(socket));
		socket.on('error', () => {});
		if (this.dropGreetings > 0) {
			this.dropGreetings -= 1;
			socket.destroy();
			return;
		}
		let input = '';
		let authTag = '';
		let authenticated = false;
		let examined = false;
		const send = line => socket.write(`${line}\r\n`);
		send('* OK isolated synthetic IMAP fixture');
		socket.on('data', buffer => {
			input += buffer.toString('utf8');
			while (input.includes('\r\n')) {
				const end = input.indexOf('\r\n');
				const line = input.slice(0, end);
				input = input.slice(end + 2);
				if (authTag) {
					// Do not record AUTH payloads, even though all credentials are generated test data.
					this.authAttempts += 1;
					const [, user, password] = Buffer.from(line, 'base64').toString().split('\0');
					authenticated = !this.rejectAuth && user === EXPECTED_ACCOUNT && password === this.password;
					send(`${authTag} ${authenticated ? 'OK authenticated' : 'NO [AUTHENTICATIONFAILED] SYNTHETIC-PRIVATE-CANARY'}`);
					authTag = '';
					continue;
				}
				const [, tag, rawCommand, args = ''] = line.match(/^(\S+) (\S+)(?: (.*))?$/) || [];
				const command = String(rawCommand).toUpperCase();
				this.commands.push({ command, args: command === 'UID' ? args : '' });
				if (command === 'CAPABILITY') {
					send('* CAPABILITY IMAP4rev1 AUTH=PLAIN X-GM-EXT-1');
				} else if (command === 'AUTHENTICATE' && args === 'PLAIN') {
					authTag = tag;
					send('+');
					continue;
				} else if (command === 'LOGOUT') {
					send('* BYE closing fixture');
					send(`${tag} OK LOGOUT`);
					socket.end();
					continue;
				} else if (authenticated && (command === 'LIST' || command === 'LSUB')) {
					send(`* ${command} () "/" ${args === '"" ""' ? '""' : '"INBOX"'}`);
				} else if (authenticated && command === 'EXAMINE' && /^"?INBOX"?$/.test(args)) {
					examined = true;
					send('* FLAGS (\\Seen)');
					send(`* ${this.messages.length} EXISTS`);
					send('* 0 RECENT');
					send(`* OK [UIDVALIDITY ${this.uidValidity}] validity`);
					send(`* OK [UIDNEXT ${this.uidNext}] next`);
					send(`${tag} OK [READ-ONLY] EXAMINE`);
					continue;
				} else if (examined && command === 'UID' && args.startsWith('FETCH ')) {
					this.fetch(socket, tag, args, send);
					continue;
				} else if (authenticated && command === 'NOOP') {
					// Nothing to notify.
				} else {
					this.unexpected.push(command);
					send(`${tag || '*'} BAD unsupported fixture command`);
					continue;
				}
				send(`${tag} OK ${command}`);
			}
		});
	}

	fetch(socket, tag, args, send) {
		const [, range, query] = args.match(/^FETCH ([\d:*]+) (.*)$/) || [];
		if (!range || !query) {
			this.unexpected.push('FETCH_RANGE');
			send(`${tag} BAD unsupported range`);
			return;
		}
		const bounds = range.split(':').map(value => value === '*' ? this.uidNext - 1 : Number(value));
		const sections = [...query.matchAll(/BODY\.PEEK\[([^\]]*)\](?:<(\d+)\.(\d+)>)?/gi)];
		for (const [index, mail] of this.messages.entries()) {
			if (mail.uid < bounds[0] || mail.uid > (bounds[1] || bounds[0])) continue;
			if (sections.length && (this.failBodyOnce.delete(mail.uid) || this.dropBodyOnce.has(mail.uid))) {
				if (this.dropBodyOnce.delete(mail.uid)) socket.destroy();
				else send(`${tag} NO [UNAVAILABLE] SYNTHETIC-PRIVATE-CANARY`);
				return;
			}
			let response = `* ${index + 1} FETCH (UID ${mail.uid}`;
			if (query.includes('X-GM-MSGID')) response += ` X-GM-MSGID ${mail.id}`;
			if (query.includes('ENVELOPE')) response += ` ENVELOPE ${mail.envelope}`;
			if (query.includes('INTERNALDATE')) response += ` INTERNALDATE ${quoted(imapDate(mail.date))}`;
			if (query.includes('BODYSTRUCTURE')) response += ` BODYSTRUCTURE ${mail.structure}`;
			if (query.includes('RFC822.SIZE')) response += ' RFC822.SIZE 4096';
			const chunks = [Buffer.from(response)];
			for (const [, section, start, length] of sections) {
				const data = mail.parts.get(section.toUpperCase());
				if (!data) {
					this.unexpected.push(`BODY[${section}]`);
					send(`${tag} BAD attachment or unsupported body requested`);
					return;
				}
				const slice = start === undefined ? data : data.subarray(Number(start), Number(start) + Number(length));
				chunks.push(Buffer.from(` BODY[${section}]${start === undefined ? '' : `<${start}>`} {${slice.length}}\r\n`), slice);
			}
			chunks.push(Buffer.from(')\r\n'));
			socket.write(Buffer.concat(chunks));
		}
		send(`${tag} OK FETCH`);
	}

	assertReadOnly() {
		assert.deepEqual(this.unexpected, []);
		assert.ok(this.commands.some(item => item.command === 'EXAMINE'));
		assert.ok(this.commands.every(item => ['CAPABILITY', 'AUTHENTICATE', 'LIST', 'LSUB', 'EXAMINE', 'UID', 'LOGOUT', 'NOOP'].includes(item.command)));
		const fetches = this.commands.filter(item => item.command === 'UID');
		assert.ok(fetches.every(item => item.args.startsWith('FETCH ')));
		assert.ok(fetches.every(item => !/BODY\[|BODY\.PEEK\[\]|RFC822(?:\s|\))/i.test(item.args)));
	}

	async close() {
		for (const socket of this.sockets) socket.destroy();
		if (this.server?.listening) await new Promise(resolve => this.server.close(resolve));
		if (this.directory) {
			const target = path.resolve(this.directory);
			assert.equal(path.dirname(target), path.resolve(os.tmpdir()));
			assert.ok(path.basename(target).startsWith('heuesta-imap-test-'));
			fs.rmSync(target, { recursive: true, force: true });
		}
	}
}

module.exports = { ImapTestServer, syntheticMail };
