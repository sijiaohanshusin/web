'use strict';

const NETWORK_CODES = new Set([
	'CONNECT_TIMEOUT', 'GREETING_TIMEOUT', 'ETIMEDOUT', 'ECONNRESET', 'ECONNREFUSED',
	'EAI_AGAIN', 'ENETUNREACH', 'ENOTFOUND', 'EHOSTUNREACH', 'CONNECTIONNOTAVAILABLE',
	'NOCONNECTION', 'UNEXPECTEDCLOSE',
]);
const TLS_CODES = new Set([
	'DEPTH_ZERO_SELF_SIGNED_CERT', 'SELF_SIGNED_CERT_IN_CHAIN', 'CERT_HAS_EXPIRED',
	'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
	'ERR_TLS_CERT_ALTNAME_INVALID', 'ERR_SSL_WRONG_VERSION_NUMBER',
]);

function codes(error) {
	return [error?.code, error?.responseCode, error?.serverResponseCode]
		.filter(value => typeof value === 'string').map(value => value.toUpperCase());
}

function isCredentialError(error) {
	const message = String(error?.message || '').toLowerCase();
	return error?.authenticationFailed === true || codes(error).some(code => code.includes('AUTH')) ||
		message.includes('invalid credentials') || message.includes('application-specific password required') ||
		message.includes('username and password not accepted');
}

function classifyError(error) {
	if (isCredentialError(error)) {
		return 'AUTHENTICATIONFAILED';
	}
	return codes(error).find(code => NETWORK_CODES.has(code) || TLS_CODES.has(code) || code === 'MESSAGE_MISSING') || 'SYNC_FAILED';
}

function safeError(error) {
	const code = classifyError(error);
	if (code === 'AUTHENTICATIONFAILED') {
		return 'Gmail IMAP 登录失败，请检查账号、两步验证和应用专用密码';
	}
	if (NETWORK_CODES.has(code)) {
		return `Gmail IMAP 暂时无法连接（${code}），稍后自动重试`;
	}
	if (TLS_CODES.has(code)) {
		return `Gmail IMAP 安全连接验证失败（${code}），请检查证书与网络，勿关闭证书校验`;
	}
	if (code === 'MESSAGE_MISSING') {
		return '邮件在重试前已离开收件箱，已跳过';
	}
	// Server responses and arbitrary error codes can contain credentials or mail content.
	return 'Gmail IMAP 同步失败，系统将自动重试；如持续失败，请联系维护人员检查同步服务';
}

function sanitizedError(error) {
	return Object.assign(new Error(safeError(error)), { code: classifyError(error) });
}

module.exports = { isCredentialError, safeError, sanitizedError };
