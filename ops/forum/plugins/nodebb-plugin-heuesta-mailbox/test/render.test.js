'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { enhancePostContent, enhancePosts } = require('../lib/render');

const TOKEN = 'a'.repeat(64);

test('replaces preview and text markers with a sandboxed email preview', () => {
	const rendered = enhancePostContent([
		`<p>[heuesta-mailbox-preview:${TOKEN}]</p>`,
		'<p>[heuesta-mailbox-text-start]</p>',
		'<p>Plain fallback</p>',
		'<p>[heuesta-mailbox-text-end]</p>',
		'<p>&lt;!-- heuesta-mailbox:gmail:123:0 --&gt;</p>',
	].join(''));
	assert.match(rendered, new RegExp(`/api/heuesta-mailbox/preview/${TOKEN}`));
	assert.match(rendered, /<iframe/);
	assert.match(rendered, /sandbox="allow-popups allow-popups-to-escape-sandbox"/);
	assert.match(rendered, /<details/);
	assert.match(rendered, /Plain fallback/);
	assert.doesNotMatch(rendered, /heuesta-mailbox:gmail/);
});

test('enhances every post returned by NodeBB', () => {
	const data = enhancePosts({ posts: [{ content: `<p>[heuesta-mailbox-preview:${TOKEN}]</p>` }] });
	assert.match(data.posts[0].content, /<iframe/);
});
