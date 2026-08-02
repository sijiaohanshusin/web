'use strict';

const { htmlToText } = require('html-to-text');
const iconv = require('iconv-lite');
const libmime = require('libmime');
const addressparser = require('nodemailer/lib/addressparser');

const DEFAULT_CHARSET = 'utf-8';

function decodeBase64Url(value) {
	if (!value) {
		return Buffer.alloc(0);
	}
	return Buffer.from(value.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
}

function headerMap(headers = []) {
	return headers.reduce((result, header) => {
		const key = String(header.name || '').toLowerCase();
		if (key && result[key] === undefined) {
			result[key] = libmime.decodeWords(String(header.value || ''));
		}
		return result;
	}, {});
}

function getCharset(headers) {
	const contentType = headers['content-type'] || '';
	const match = contentType.match(/charset\s*=\s*["']?([^;\s"']+)/i);
	return match ? match[1].trim().toLowerCase() : DEFAULT_CHARSET;
}

function decodePart(part) {
	const headers = headerMap(part.headers);
	const charset = getCharset(headers);
	const data = decodeBase64Url(part.body && part.body.data);
	try {
		return iconv.decode(data, iconv.encodingExists(charset) ? charset : DEFAULT_CHARSET);
	} catch (err) {
		return data.toString('utf8');
	}
}

function isAttachment(part) {
	const headers = headerMap(part.headers);
	return Boolean(part.filename) || /attachment/i.test(headers['content-disposition'] || '');
}

function walkParts(part, result) {
	if (!part) {
		return;
	}
	if (isAttachment(part)) {
		result.attachments.push({
			filename: libmime.decodeWords(part.filename || '(未命名附件)'),
			mimeType: part.mimeType || 'application/octet-stream',
			size: Number(part.body && part.body.size) || 0,
		});
		return;
	}

	const mimeType = String(part.mimeType || '').toLowerCase();
	if (mimeType === 'text/plain' && part.body && part.body.data) {
		result.plain.push(decodePart(part));
	} else if (mimeType === 'text/html' && part.body && part.body.data) {
		result.html.push(decodePart(part));
	}
	for (const child of part.parts || []) {
		walkParts(child, result);
	}
}

function parseFrom(value, messageId) {
	const addresses = addressparser(value || '');
	const first = addresses.find(item => item && item.address);
	if (!first) {
		return {
			displayName: '无法识别发件人',
			email: `unknown-${messageId}@mail.invalid`,
		};
	}
	return {
		displayName: String(first.name || '').trim(),
		email: String(first.address).trim().toLowerCase(),
	};
}

function parseMessage(message) {
	const headers = headerMap(message.payload && message.payload.headers);
	const parts = { plain: [], html: [], attachments: [] };
	walkParts(message.payload, parts);

	let body = parts.plain.join('\n\n').trim();
	if (!body && parts.html.length) {
		body = htmlToText(parts.html.join('\n'), {
			wordwrap: false,
			selectors: [
				{ selector: 'img', format: 'skip' },
				{ selector: 'script', format: 'skip' },
				{ selector: 'style', format: 'skip' },
			],
		}).trim();
	}
	if (!body) {
		body = '(邮件没有可显示的文本正文)';
	}

	const from = parseFrom(headers.from, message.id);
	return {
		id: String(message.id),
		historyId: String(message.historyId || ''),
		internalDate: Number(message.internalDate) || Date.now(),
		subject: String(headers.subject || '(无主题)').trim() || '(无主题)',
		fromName: from.displayName,
		fromEmail: from.email,
		senderKey: from.email.toLowerCase(),
		body,
		attachments: parts.attachments,
		labelIds: message.labelIds || [],
	};
}

module.exports = {
	decodeBase64Url,
	headerMap,
	parseMessage,
	walkParts,
};
