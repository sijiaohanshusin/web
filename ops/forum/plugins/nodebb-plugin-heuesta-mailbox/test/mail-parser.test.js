'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const iconv = require('iconv-lite');
const { parseMessage } = require('../lib/mail-parser');

function encoded(value, encoding = 'utf8') {
	const buffer = encoding === 'utf8' ? Buffer.from(value) : iconv.encode(value, encoding);
	return buffer.toString('base64url');
}

function message(payload, overrides = {}) {
	return {
		id: 'gmail-1',
		historyId: '101',
		internalDate: '1785657600000',
		labelIds: ['INBOX'],
		payload,
		...overrides,
	};
}

test('prefers plain text and preserves a normalized full sender address', () => {
	const parsed = parseMessage(message({
		mimeType: 'multipart/alternative',
		headers: [
			{ name: 'From', value: 'Alice <Alice+Tag@example.com>' },
			{ name: 'Subject', value: 'Hello' },
		],
		parts: [
			{ mimeType: 'text/plain', headers: [], body: { data: encoded('plain body'), size: 10 } },
			{ mimeType: 'text/html', headers: [], body: { data: encoded('<b>html body</b>'), size: 16 } },
		],
	}));
	assert.equal(parsed.body, 'plain body');
	assert.equal(parsed.fromEmail, 'alice+tag@example.com');
	assert.equal(parsed.senderKey, 'alice+tag@example.com');
});

test('converts HTML to text without retaining remote images or scripts', () => {
	const parsed = parseMessage(message({
		mimeType: 'text/html',
		headers: [{ name: 'From', value: 'sender@example.com' }],
		body: { data: encoded('<p>Visible</p><img src="https://tracker.invalid/pixel"><script>alert(1)</script>') },
	}));
	assert.match(parsed.body, /Visible/);
	assert.doesNotMatch(parsed.body, /tracker|alert/);
});

test('decodes non-UTF-8 Chinese text and keeps attachment metadata only', () => {
	const parsed = parseMessage(message({
		mimeType: 'multipart/mixed',
		headers: [{ name: 'From', value: '测试 <test@example.com>' }],
		parts: [
			{
				mimeType: 'text/plain',
				headers: [{ name: 'Content-Type', value: 'text/plain; charset=gb18030' }],
				body: { data: encoded('中文正文', 'gb18030'), size: 8 },
			},
			{
				mimeType: 'application/pdf',
				filename: '说明.pdf',
				headers: [{ name: 'Content-Disposition', value: 'attachment' }],
				body: { attachmentId: 'must-not-be-downloaded', size: 4096 },
			},
		],
	}));
	assert.equal(parsed.body, '中文正文');
	assert.deepEqual(parsed.attachments, [{ filename: '说明.pdf', mimeType: 'application/pdf', size: 4096 }]);
});
