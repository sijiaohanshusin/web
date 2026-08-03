'use strict';

const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const test = require('node:test');
const {
	inspectBodyStructure,
	parseImapMessage,
	stableMessageId,
} = require('../lib/mail-parser');

function textNode(part, type = 'text/plain') {
	return { part, type, size: 20, parameters: { charset: 'utf-8' } };
}

function message(overrides = {}) {
	return {
		uid: 42,
		emailId: '1789000000000000',
		internalDate: new Date('2026-08-02T10:00:00Z'),
		envelope: {
			subject: 'Hello',
			from: [{ name: 'Alice', address: 'Alice+Tag@example.com' }],
		},
		bodyStructure: textNode('1'),
		...overrides,
	};
}

test('uses Gmail emailId for permanent deduplication and preserves the full sender address', async () => {
	const requested = [];
	const client = {
		download: async (uid, part) => {
			requested.push({ uid, part });
			return { content: Readable.from(['plain body']) };
		},
	};
	const parsed = await parseImapMessage(client, message(), '123');
	assert.equal(parsed.id, 'gmail:1789000000000000');
	assert.equal(parsed.body, 'plain body');
	assert.equal(parsed.fromEmail, 'alice+tag@example.com');
	assert.deepEqual(requested, [{ uid: 42, part: '1' }]);
});

test('converts HTML to text without retaining remote images or scripts', async () => {
	const client = {
		download: async () => ({
			content: Readable.from(['<p>Visible</p><img src="https://tracker.invalid/pixel"><script>alert(1)</script>']),
		}),
	};
	const parsed = await parseImapMessage(client, message({ bodyStructure: textNode('1', 'text/html') }), '123');
	assert.match(parsed.body, /Visible/);
	assert.doesNotMatch(parsed.body, /tracker|alert/);
});

test('downloads a single-part root HTML message through logical part 1', async () => {
	const requested = [];
	const client = {
		download: async (uid, part) => {
			requested.push({ uid, part });
			return { content: Readable.from(['<main><h1>Login code</h1><p>Visible body</p></main>']) };
		},
	};
	const parsed = await parseImapMessage(client, message({
		bodyStructure: { type: 'text/html', size: 100, parameters: { charset: 'utf-8' } },
	}), '123');
	assert.deepEqual(requested, [{ uid: 42, part: '1' }]);
	assert.match(parsed.body, /Login code/i);
	assert.match(parsed.body, /Visible body/);
});

test('downloads a single-part root plain text message through logical part 1', async () => {
	const requested = [];
	const client = {
		download: async (uid, part) => {
			requested.push({ uid, part });
			return { content: Readable.from(['plain root body']) };
		},
	};
	const parsed = await parseImapMessage(client, message({
		bodyStructure: { type: 'text/plain', size: 20, parameters: { charset: 'utf-8' } },
	}), '123');
	assert.deepEqual(requested, [{ uid: 42, part: '1' }]);
	assert.equal(parsed.body, 'plain root body');
});

test('collects attachment metadata but never requests attachment body parts', async () => {
	const structure = {
		type: 'multipart/mixed',
		childNodes: [
			textNode('1'),
			{
				part: '2',
				type: 'application/pdf',
				size: 4096,
				disposition: 'attachment',
				dispositionParameters: { filename: '说明.pdf' },
			},
		],
	};
	const requested = [];
	const client = {
		download: async (uid, part) => {
			requested.push(part);
			return { content: Readable.from(['中文正文']) };
		},
	};
	const parsed = await parseImapMessage(client, message({ bodyStructure: structure }), '123');
	assert.deepEqual(requested, ['1']);
	assert.deepEqual(parsed.attachments, [{ filename: '说明.pdf', mimeType: 'application/pdf', size: 4096 }]);
});

test('falls back to UIDVALIDITY and UID when Gmail emailId is unavailable', () => {
	assert.equal(stableMessageId({ uid: 77 }, '987'), 'imap:987:77');
});

test('prefers plain parts while retaining HTML as a fallback', () => {
	const parts = inspectBodyStructure({
		type: 'multipart/alternative',
		childNodes: [textNode('1', 'text/plain'), textNode('2', 'text/html')],
	});
	assert.deepEqual(parts.plain.map(node => node.part), ['1']);
	assert.deepEqual(parts.html.map(node => node.part), ['2']);
});
