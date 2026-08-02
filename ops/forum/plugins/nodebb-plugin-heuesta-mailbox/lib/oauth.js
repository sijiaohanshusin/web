'use strict';

const crypto = require('crypto');
const { google } = require('googleapis');
const { parseKey } = require('./crypto');

const GMAIL_READONLY = 'https://www.googleapis.com/auth/gmail.readonly';
const EXPECTED_ACCOUNT = 'heuesta@gmail.com';

class GmailOAuth {
	constructor(options) {
		this.clientId = options.clientId;
		this.clientSecret = options.clientSecret;
		this.callbackUrl = options.callbackUrl;
		this.store = options.store;
		this.expectedAccount = String(options.expectedAccount || EXPECTED_ACCOUNT).toLowerCase();
	}

	isConfigured() {
		if (!this.clientId || !this.clientSecret || !this.store.encryptionKey) {
			return false;
		}
		try {
			parseKey(this.store.encryptionKey);
			return true;
		} catch (error) {
			return false;
		}
	}

	client() {
		if (!this.isConfigured()) {
			throw new Error('Gmail OAuth environment variables are incomplete');
		}
		return new google.auth.OAuth2(this.clientId, this.clientSecret, this.callbackUrl);
	}

	async authorizationUrl(uid) {
		const state = crypto.randomBytes(32).toString('base64url');
		await this.store.saveOAuthState(state, uid);
		return this.client().generateAuthUrl({
			access_type: 'offline',
			prompt: 'consent',
			include_granted_scopes: true,
			scope: [GMAIL_READONLY],
			state,
		});
	}

	async completeAuthorization(uid, query) {
		if (query.error) {
			throw new Error(`Google authorization was not completed (${String(query.error).slice(0, 80)})`);
		}
		if (!query.code || !await this.store.consumeOAuthState(query.state, uid)) {
			throw new Error('OAuth state is invalid or expired');
		}

		const auth = this.client();
		const { tokens } = await auth.getToken(query.code);
		const refreshToken = tokens.refresh_token || await this.store.getRefreshToken();
		if (!refreshToken) {
			throw new Error('Google did not return an offline refresh token; reconnect and grant access again');
		}
		auth.setCredentials({ ...tokens, refresh_token: refreshToken });
		const gmail = google.gmail({ version: 'v1', auth });
		const now = Date.now();
		const profile = await gmail.users.getProfile({ userId: 'me' });
		const connectedEmail = String(profile.data.emailAddress || '').toLowerCase();
		if (connectedEmail !== this.expectedAccount) {
			throw new Error(`Only ${this.expectedAccount} can be connected to the public mailbox`);
		}

		const existing = await this.store.getState();
		const initialConnection = !existing.historyId || String(existing.connectedEmail || '').toLowerCase() !== connectedEmail;
		await this.store.storeRefreshToken(refreshToken);
		const stateUpdate = {
			connectedEmail,
			lastError: '',
			needsReauthorization: 0,
		};
		if (initialConnection) {
			stateUpdate.historyId = String(profile.data.historyId || '');
			stateUpdate.startedAt = now;
			stateUpdate.lastSuccessAt = now;
		}
		await this.store.updateState(stateUpdate);
		return { email: connectedEmail, initialConnection };
	}

	async gmail() {
		const refreshToken = await this.store.getRefreshToken();
		if (!refreshToken) {
			throw new Error('Gmail is not connected');
		}
		const auth = this.client();
		auth.setCredentials({ refresh_token: refreshToken });
		return google.gmail({ version: 'v1', auth });
	}
}

module.exports = { GmailOAuth, GMAIL_READONLY, EXPECTED_ACCOUNT };
