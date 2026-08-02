'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { GmailImap, normalizeAppPassword } = require('../lib/imap');

test('normalizes grouped app passwords without accepting the regular Gmail password', () => {
	assert.equal(normalizeAppPassword('abcd efgh ijkl mnop'), 'abcdefghijklmnop');
	assert.equal(new GmailImap({ user: 'heuesta@gmail.com', appPassword: 'abcd efgh ijkl mnop' }).isConfigured(), true);
	assert.equal(new GmailImap({ user: 'heuesta@gmail.com', appPassword: 'regular-password' }).isConfigured(), false);
	assert.equal(new GmailImap({ user: 'other@gmail.com', appPassword: 'abcdefghijklmnop' }).isConfigured(), false);
});
