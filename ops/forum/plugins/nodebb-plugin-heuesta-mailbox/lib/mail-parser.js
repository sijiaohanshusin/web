'use strict';

const { htmlToText } = require('html-to-text');

const MAX_TEXT_PART_BYTES = 512 * 1024;
const MAX_BODY_CHARS = 120000;

function partFilename(node) {
	return String(
		node && node.dispositionParameters && node.dispositionParameters.filename ||
		node && node.parameters && node.parameters.name ||
		''
	).trim();
}

function isAttachment(node) {
	const type = String(node && node.type || '').toLowerCase();
	const topType = type.split('/')[0];
	return String(node && node.disposition || '').toLowerCase() === 'attachment' ||
		Boolean(partFilename(node)) ||
		Boolean(type && topType !== 'text' && topType !== 'multipart' && !node.childNodes);
}

function inspectBodyStructure(node, result = { plain: [], html: [], attachments: [] }, isRoot = true) {
	if (!node) {
		return result;
	}
	if (isAttachment(node)) {
		result.attachments.push({
			filename: partFilename(node) || '(未命名附件)',
			mimeType: String(node.type || 'application/octet-stream').toLowerCase(),
			size: Number(node.size) || 0,
		});
		return result;
	}

	const type = String(node.type || '').toLowerCase();
	// IMAP body structures omit the part number for a single-part root message.
	// ImapFlow maps logical part "1" to BODY[TEXT] for that message shape.
	const textNode = !node.part && isRoot ? { ...node, part: '1' } : node;
	if (type === 'text/plain' && textNode.part) {
		result.plain.push(textNode);
	} else if (type === 'text/html' && textNode.part) {
		result.html.push(textNode);
	}
	for (const child of node.childNodes || []) {
		inspectBodyStructure(child, result, false);
	}
	return result;
}

async function streamToText(stream) {
	const chunks = [];
	for await (const chunk of stream) {
		chunks.push(Buffer.from(chunk));
	}
	return Buffer.concat(chunks).toString('utf8');
}

async function downloadTextParts(client, uid, nodes) {
	const values = [];
	for (const node of nodes) {
		const result = await client.download(uid, node.part, {
			uid: true,
			maxBytes: MAX_TEXT_PART_BYTES,
		});
		if (!result || !result.content) {
			// ImapFlow can return false after disconnection or removal, not just throw.
			throw Object.assign(new Error('Mail text part is not available'), { code: 'MAIL_PART_UNAVAILABLE' });
		}
		values.push(await streamToText(result.content));
	}
	return values.join('\n\n').trim();
}

function firstSender(envelope, messageId) {
	const sender = envelope && Array.isArray(envelope.from) ? envelope.from.find(item => item && item.address) : null;
	if (!sender) {
		return { displayName: '无法识别发件人', email: `unknown-${messageId}@mail.invalid` };
	}
	return {
		displayName: String(sender.name || '').trim(),
		email: String(sender.address).trim().toLowerCase(),
	};
}

function stableMessageId(message, uidValidity) {
	const emailId = String(message && message.emailId || '').trim();
	return emailId ? `gmail:${emailId}` : `imap:${uidValidity}:${Number(message && message.uid)}`;
}

async function parseImapMessage(client, message, uidValidity) {
	const id = stableMessageId(message, uidValidity);
	const parts = inspectBodyStructure(message.bodyStructure);
	const html = parts.html.length ? await downloadTextParts(client, message.uid, parts.html) : '';
	let body = await downloadTextParts(client, message.uid, parts.plain);
	if (!body && html) {
		body = htmlToText(html, {
			wordwrap: false,
			selectors: [
				{ selector: 'a', options: { ignoreHref: true } },
				{ selector: 'img', format: 'skip' },
				{ selector: 'script', format: 'skip' },
				{ selector: 'style', format: 'skip' },
			],
		}).trim();
	}
	if (!body) {
		body = '(邮件没有可显示的文本正文)';
	} else if (body.length > MAX_BODY_CHARS) {
		body = `${body.slice(0, MAX_BODY_CHARS)}\n\n[正文过长，论坛归档已截断]`;
	}

	const envelope = message.envelope || {};
	const from = firstSender(envelope, id.replace(/[^a-z0-9]/gi, '').slice(-32));
	return {
		id,
		internalDate: new Date(message.internalDate || envelope.date || Date.now()).getTime(),
		subject: String(envelope.subject || '(无主题)').trim() || '(无主题)',
		fromName: from.displayName,
		fromEmail: from.email,
		senderKey: from.email.toLowerCase(),
		body,
		html,
		attachments: parts.attachments,
	};
}

module.exports = {
	MAX_TEXT_PART_BYTES,
	MAX_BODY_CHARS,
	downloadTextParts,
	inspectBodyStructure,
	isAttachment,
	parseImapMessage,
	stableMessageId,
};
