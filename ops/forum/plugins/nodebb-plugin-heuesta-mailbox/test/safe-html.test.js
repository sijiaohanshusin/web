'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {
	buildPreviewDocument,
	previewTokenFor,
	sanitizeEmailHtml,
} = require('../lib/safe-html');

test('sanitizes active content and remote resources while preserving email layout', () => {
	const result = sanitizeEmailHtml(`
		<style>@import url(https://tracker.invalid/a.css)</style>
		<script>alert(1)</script>
		<form action="https://evil.invalid"><input name="secret"></form>
		<table width="600" style="background-color:#fff;text-align:center;background-image:url(https://tracker.invalid/bg)">
			<tr><td><a href="https://example.com/action">Continue</a><img src="https://tracker.invalid/pixel" alt="pixel"></td></tr>
		</table>
	`);
	assert.match(result, /<table/);
	assert.match(result, /background-color:#fff/);
	assert.match(result, /Continue/);
	assert.match(result, /target="_blank"/);
	assert.doesNotMatch(result, /script|form|input|tracker\.invalid|background-image/i);
});

test('builds a standalone preview document and stable opaque token', () => {
	const token = previewTokenFor('gmail:123');
	assert.match(token, /^[a-f0-9]{64}$/);
	assert.equal(token, previewTokenFor('gmail:123'));
	const document = buildPreviewDocument('<div style="color:#123">Visible</div>');
	assert.match(document, /<!doctype html>/i);
	assert.match(document, /Visible/);
});
