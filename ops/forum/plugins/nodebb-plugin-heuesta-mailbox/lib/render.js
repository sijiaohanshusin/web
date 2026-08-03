'use strict';

const PREVIEW_MARKER = /<p>\s*\[heuesta-mailbox-preview:([a-f0-9]{64})\]\s*<\/p>/gi;
const TEXT_BLOCK = /<p>\s*\[heuesta-mailbox-text-start\]\s*<\/p>([\s\S]*?)<p>\s*\[heuesta-mailbox-text-end\]\s*<\/p>/gi;
const ARCHIVE_MARKER = /(?:&lt;|<)!--\s*heuesta-mailbox(?:-sender)?:.*?--(?:&gt;|>)/gi;

function previewFrame(token) {
	return [
		'<section style="margin:1rem 0;border:1px solid #d8c69e;border-radius:10px;overflow:hidden;background:#fff">',
		'<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:#f4ead3;color:#3f3a2f;font-weight:700">',
		'<span>邮件原始排版（已安全处理）</span>',
		`<a href="/api/heuesta-mailbox/preview/${token}" target="_blank" rel="noopener noreferrer" style="font-size:.9em">单独打开</a>`,
		'</div>',
		`<iframe src="/api/heuesta-mailbox/preview/${token}" title="邮件原始排版" loading="lazy" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" style="display:block;width:100%;height:760px;border:0;background:#fff"></iframe>`,
		'</section>',
	].join('');
}

function enhancePostContent(value) {
	return String(value || '')
		.replace(PREVIEW_MARKER, (match, token) => previewFrame(token))
		.replace(TEXT_BLOCK, (match, content) => [
			'<details style="margin:1rem 0;border:1px solid #ded7c8;border-radius:8px;padding:10px 12px">',
			'<summary style="cursor:pointer;font-weight:700">查看纯文本版本</summary>',
			`<div style="margin-top:12px">${content}</div>`,
			'</details>',
		].join(''))
		.replace(ARCHIVE_MARKER, '')
		.replace(/<p>\s*<\/p>/gi, '');
}

function enhancePosts(data) {
	for (const post of data && Array.isArray(data.posts) ? data.posts : []) {
		post.content = enhancePostContent(post.content);
	}
	return data;
}

module.exports = { enhancePostContent, enhancePosts, previewFrame };
