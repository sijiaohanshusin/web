'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const { parseKey, encryptString, decryptString } = require('../lib/crypto');

test('encrypts and decrypts a refresh token with AES-256-GCM', () => {
	const key = crypto.randomBytes(32).toString('base64');
	const encrypted = encryptString('refresh-token-value', key);
	assert.notEqual(encrypted, 'refresh-token-value');
	assert.equal(decryptString(encrypted, key), 'refresh-token-value');
});

test('accepts 64-character hex keys and rejects the wrong length', () => {
	assert.equal(parseKey('ab'.repeat(32)).length, 32);
	assert.throws(() => parseKey(Buffer.alloc(16).toString('base64')), /32 bytes/);
});

test('detects authenticated ciphertext tampering', () => {
	const key = crypto.randomBytes(32).toString('base64');
	const payload = JSON.parse(encryptString('secret', key));
	payload.data = Buffer.from('tampered').toString('base64');
	assert.throws(() => decryptString(JSON.stringify(payload), key));
});
