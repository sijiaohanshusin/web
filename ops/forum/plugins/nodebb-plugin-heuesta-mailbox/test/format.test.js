'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { escapeMarkdown, formatPosts, splitParagraphs, topicTitle } = require('../lib/format');

test('escapes HTML, Markdown images, and mention syntax from email content', () => {
	const escaped = escapeMarkdown('<script>alert(1)</script> ![pixel](https://tracker.invalid) @everyone');
	assert.doesNotMatch(escaped, /<script>/);
	assert.match(escaped, /\\!/);
	assert.match(escaped, /\\\[/);
	assert.doesNotMatch(escaped, /@everyone/);
});

test('splits oversized bodies and assigns a stable marker to every floor', () => {
	const mail = {
		id: 'abc123',
		internalDate: Date.UTC(2026, 7, 2, 8, 0, 0),
		subject: '长邮件',
		fromName: '发件人',
		fromEmail: 'sender@example.com',
		body: `${'甲'.repeat(12000)}\n\n${'乙'.repeat(12000)}`,
		attachments: [],
	};
	const posts = formatPosts(mail, 'sender-hash');
	assert.equal(posts.length, 2);
	assert.match(posts[0], /heuesta-mailbox:abc123:0/);
	assert.match(posts[1], /heuesta-mailbox:abc123:1/);
	assert.match(posts[0], /附件（仅元数据，未下载）/);
	assert.equal(splitParagraphs('a\n\nb', 2).length, 2);
});

test('topic titles retain plus tags and dots in the full sender address', () => {
	assert.equal(topicTitle({ fromName: 'Alice', fromEmail: 'first.last+tag@example.com' }), 'Alice · first.last+tag@example.com');
	assert.equal(topicTitle({ fromName: '<script>\nAlice', fromEmail: 'alice@example.com' }), 'script Alice · alice@example.com');
});

test('adds an original-layout preview marker and collapsible text markers', () => {
	const token = 'c'.repeat(64);
	const posts = formatPosts({
		id: 'gmail:123',
		internalDate: Date.UTC(2026, 7, 3, 4, 0, 0),
		subject: 'HTML mail',
		fromName: 'Sender',
		fromEmail: 'sender@example.com',
		body: 'Plain fallback',
		attachments: [],
	}, 'sender-hash', token);
	assert.match(posts[0], new RegExp(`heuesta-mailbox-preview:${token}`));
	assert.match(posts[0], /heuesta-mailbox-text-start/);
	assert.match(posts[0], /heuesta-mailbox-text-end/);
});
