'use strict';

const crypto = require('crypto');

function parseKey(value) {
	if (!value) {
		throw new Error('MAILBOX_TOKEN_ENCRYPTION_KEY is not configured');
	}
	const trimmed = value.trim();
	let key;
	if (/^[0-9a-f]{64}$/i.test(trimmed)) {
		key = Buffer.from(trimmed, 'hex');
	} else {
		key = Buffer.from(trimmed, 'base64');
	}
	if (key.length !== 32) {
		throw new Error('MAILBOX_TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes');
	}
	return key;
}

function encryptString(value, keyValue) {
	const key = parseKey(keyValue);
	const iv = crypto.randomBytes(12);
	const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
	const encrypted = Buffer.concat([cipher.update(String(value), 'utf8'), cipher.final()]);
	return JSON.stringify({
		v: 1,
		iv: iv.toString('base64'),
		tag: cipher.getAuthTag().toString('base64'),
		data: encrypted.toString('base64'),
	});
}

function decryptString(payload, keyValue) {
	const key = parseKey(keyValue);
	const parsed = JSON.parse(payload);
	if (parsed.v !== 1 || !parsed.iv || !parsed.tag || !parsed.data) {
		throw new Error('Unsupported encrypted token format');
	}
	const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(parsed.iv, 'base64'));
	decipher.setAuthTag(Buffer.from(parsed.tag, 'base64'));
	return Buffer.concat([
		decipher.update(Buffer.from(parsed.data, 'base64')),
		decipher.final(),
	]).toString('utf8');
}

module.exports = { parseKey, encryptString, decryptString };
