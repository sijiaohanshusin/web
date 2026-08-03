'use strict';

const crypto = require('node:crypto');
const sanitizeHtml = require('sanitize-html');

const MAX_HTML_CHARS = 512 * 1024;
const SAFE_STYLE_VALUE = /^(?!.*(?:url\s*\(|expression\s*\(|@import|javascript\s*:|behavior\s*:|-moz-binding))[^<>]*$/i;
const SAFE_STYLE_PROPERTIES = [
	'background', 'background-color', 'border', 'border-bottom', 'border-collapse',
	'border-color', 'border-left', 'border-radius', 'border-right', 'border-spacing',
	'border-style', 'border-top', 'border-width', 'box-sizing', 'color', 'display',
	'font', 'font-family', 'font-size', 'font-style', 'font-weight', 'height',
	'letter-spacing', 'line-height', 'margin', 'margin-bottom', 'margin-left',
	'margin-right', 'margin-top', 'max-height', 'max-width', 'min-height', 'min-width',
	'opacity', 'overflow', 'padding', 'padding-bottom', 'padding-left', 'padding-right',
	'padding-top', 'text-align', 'text-decoration', 'text-indent', 'text-transform',
	'vertical-align', 'white-space', 'width', 'word-break', 'word-spacing', 'word-wrap',
];

function previewTokenFor(messageId) {
	return crypto.createHash('sha256').update(`heuesta-mailbox-preview:${messageId}`).digest('hex');
}

function sanitizeEmailHtml(value) {
	const allowedStyles = Object.fromEntries(SAFE_STYLE_PROPERTIES.map(property => [property, [SAFE_STYLE_VALUE]]));
	return sanitizeHtml(String(value || '').slice(0, MAX_HTML_CHARS), {
		allowedTags: [...new Set([
			...sanitizeHtml.defaults.allowedTags,
			'center', 'font', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr',
		])],
		allowedAttributes: {
			'*': ['class', 'id', 'dir', 'lang', 'title', 'role', 'aria-*', 'style'],
			a: ['href', 'title', 'target', 'rel'],
			font: ['color', 'face', 'size'],
			img: ['src', 'alt', 'width', 'height', 'title', 'style'],
			table: ['align', 'bgcolor', 'border', 'cellpadding', 'cellspacing', 'height', 'width', 'style'],
			td: ['align', 'bgcolor', 'colspan', 'height', 'rowspan', 'valign', 'width', 'style'],
			th: ['align', 'bgcolor', 'colspan', 'height', 'rowspan', 'scope', 'valign', 'width', 'style'],
			tr: ['align', 'bgcolor', 'height', 'valign', 'style'],
		},
		allowedSchemes: ['http', 'https', 'mailto'],
		allowedSchemesByTag: { img: ['data'] },
		allowProtocolRelative: false,
		allowedStyles: { '*': allowedStyles },
		transformTags: {
			a: (tagName, attribs) => ({
				tagName,
				attribs: { ...attribs, target: '_blank', rel: 'noopener noreferrer nofollow' },
			}),
		},
		exclusiveFilter: frame => frame.tag === 'img' && !/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(frame.attribs.src || ''),
	}).trim();
}

function buildPreviewDocument(fragment) {
	const safeFragment = sanitizeEmailHtml(fragment);
	return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html { color-scheme: light; background: #fff; }
body { margin: 0; padding: 20px 12px; overflow-wrap: anywhere; background: #fff; color: #222; font-family: Arial, sans-serif; }
table { max-width: 100%; }
img { max-width: 100%; height: auto; }
a { color: #075bbb; }
@media (max-width: 640px) { body { padding: 12px 6px; } }
</style>
</head>
<body>${safeFragment}</body>
</html>`;
}

module.exports = {
	MAX_HTML_CHARS,
	buildPreviewDocument,
	previewTokenFor,
	sanitizeEmailHtml,
};
