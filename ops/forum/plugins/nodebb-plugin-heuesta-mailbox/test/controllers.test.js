'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const createControllers = require('../lib/controllers');

function response() {
	return {
		statusCode: 0,
		headers: {},
		body: '',
		status(code) { this.statusCode = code; return this; },
		type(value) { this.contentType = value; return this; },
		set(headers) { Object.assign(this.headers, headers); return this; },
		send(value) { this.body = value; return this; },
	};
}

function services(canRead) {
	return {
		archive: {
			categoryCid: 28,
			privileges: { categories: { can: async () => canRead } },
		},
		store: { getPreview: async () => ({ html: '<p>Visible</p>' }) },
	};
}

test('requires mailbox read permission for HTML previews', async () => {
	const token = 'b'.repeat(64);
	const denied = response();
	await createControllers(services(false)).renderPreview({ params: { token }, uid: 2 }, denied);
	assert.equal(denied.statusCode, 404);

	const allowed = response();
	await createControllers(services(true)).renderPreview({ params: { token }, uid: 3 }, allowed);
	assert.equal(allowed.statusCode, 200);
	assert.equal(allowed.contentType, 'html');
	assert.match(allowed.body, /Visible/);
	assert.match(allowed.headers['Content-Security-Policy'], /default-src 'none'/);
	assert.equal(allowed.headers['Cache-Control'], 'private, no-store');
});
