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
		'<p>&lt;!-- heuesta-mailbox:gmail:123:0 --&gt;<br>&lt;!-- heuesta-mailbox-sender:abc --&gt;</p>',
	].join(''));
	assert.match(rendered, new RegExp(`/api/heuesta-mailbox/preview/${TOKEN}`));
	assert.match(rendered, /<iframe/);
	assert.match(rendered, /sandbox="allow-popups allow-popups-to-escape-sandbox"/);
	assert.match(rendered, /<details/);
	assert.match(rendered, /Plain fallback/);
	assert.doesNotMatch(rendered, /heuesta-mailbox:gmail/);
	assert.doesNotMatch(rendered, /heuesta-mailbox-sender/);
});

test('enhances every post returned by NodeBB', () => {
	const data = enhancePosts({ posts: [{ content: `<p>[heuesta-mailbox-preview:${TOKEN}]</p>` }] });
	assert.match(data.posts[0].content, /<iframe/);
});

test('accepts NodeBB Markdown paragraphs with automatic text direction', () => {
	const rendered = enhancePostContent([
		`<p dir="auto">[heuesta-mailbox-preview:${TOKEN}]</p>`,
		'<p dir="auto">[heuesta-mailbox-text-start]</p>',
		'<p dir="auto">Plain fallback</p>',
		'<p dir="auto">[heuesta-mailbox-text-end]</p>',
	].join('\n'));
	assert.match(rendered, /<iframe/);
	assert.match(rendered, /<details/);
	assert.match(rendered, /Plain fallback/);
	assert.doesNotMatch(rendered, /\[heuesta-mailbox-/);
	assert.equal(enhancePostContent(rendered), rendered);
});

test('leaves ordinary posts and quoted examples unchanged', () => {
	const ordinary = '<p dir="auto">Ordinary discussion</p>';
	const code = `<pre><code>[heuesta-mailbox-preview:${TOKEN}]</code></pre>`;
	assert.equal(enhancePostContent(ordinary), ordinary);
	assert.equal(enhancePostContent(code), code);
	assert.doesNotMatch(enhancePostContent('<p>[heuesta-mailbox-preview:javascript:alert(1)]</p>'), /<iframe/);
});

test('ignores missing posts in the NodeBB post list', () => {
	const result = enhancePosts({ posts: [null, { content: '<p>Text</p>' }] });
	assert.equal(result.posts[1].content, '<p>Text</p>');
});

test('renders existing archives whose preview and text-start share a paragraph', () => {
	for (const separator of ['\n', '<br>\n', '<br />\n']) {
		const rendered = enhancePostContent([
			`<p dir="auto">[heuesta-mailbox-preview:${TOKEN}]${separator}[heuesta-mailbox-text-start]</p>`,
			'<p dir="auto">Legacy fallback</p>',
			'<p dir="auto">[heuesta-mailbox-text-end]</p>',
		].join('\n'));
		assert.match(rendered, /<iframe/);
		assert.match(rendered, /<details/);
		assert.match(rendered, /Legacy fallback/);
		assert.doesNotMatch(rendered, /\[heuesta-mailbox-/);
	}
});
