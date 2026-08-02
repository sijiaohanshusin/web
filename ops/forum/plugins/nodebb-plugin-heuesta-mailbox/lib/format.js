'use strict';

const MAX_BODY_CHARS = 12000;

function escapeMarkdown(value) {
	return String(value || '')
		.replace(/\\/g, '\\\\')
		.replace(/([`*_[\]{}()#+\-.!|>~=])/g, '\\$1')
		.replace(/@/g, '&#64;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
}

function formatBytes(bytes) {
	const value = Number(bytes) || 0;
	if (value < 1024) {
		return `${value} B`;
	}
	if (value < 1024 * 1024) {
		return `${(value / 1024).toFixed(1)} KiB`;
	}
	return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function formatBeijingTime(timestamp) {
	return new Intl.DateTimeFormat('zh-CN', {
		timeZone: 'Asia/Shanghai',
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hour12: false,
	}).format(new Date(timestamp));
}

function splitParagraphs(body, maxLength = MAX_BODY_CHARS) {
	const paragraphs = String(body || '').split(/\n{2,}/);
	const chunks = [];
	let current = '';

	function pushCurrent() {
		if (current) {
			chunks.push(current);
			current = '';
		}
	}

	for (const paragraph of paragraphs) {
		if (paragraph.length > maxLength) {
			pushCurrent();
			for (let offset = 0; offset < paragraph.length; offset += maxLength) {
				chunks.push(paragraph.slice(offset, offset + maxLength));
			}
			continue;
		}
		const candidate = current ? `${current}\n\n${paragraph}` : paragraph;
		if (candidate.length > maxLength) {
			pushCurrent();
			current = paragraph;
		} else {
			current = candidate;
		}
	}
	pushCurrent();
	return chunks.length ? chunks : [''];
}

function topicTitle(mail) {
	const clean = value => String(value || '').replace(/[\u0000-\u001f<>]/g, ' ').replace(/\s+/g, ' ').trim();
	const name = clean(mail.fromName);
	const email = clean(mail.fromEmail);
	return `${name ? `${name} · ` : ''}${email}`.slice(0, 250);
}

function formatPosts(mail, senderHash) {
	const chunks = splitParagraphs(mail.body);
	const attachmentLines = mail.attachments.length ? mail.attachments.map((attachment) => (
		`- ${escapeMarkdown(attachment.filename)} | ${escapeMarkdown(attachment.mimeType)} | ${formatBytes(attachment.size)}`
	)) : ['- 无'];

	return chunks.map((chunk, index) => {
		const part = chunks.length > 1 ? `（第 ${index + 1}/${chunks.length} 段）` : '';
		const senderMarker = index === 0 ? `\n<!-- heuesta-mailbox-sender:${senderHash} -->` : '';
		const attachments = index === 0 ? `\n\n**附件（仅元数据，未下载）**\n${attachmentLines.join('\n')}` : '';
		return [
			`### ${escapeMarkdown(mail.subject)} ${part}`.trim(),
			'',
			`**发件人：** ${escapeMarkdown(mail.fromName || '(无显示名称)')} &lt;${escapeMarkdown(mail.fromEmail)}&gt;  `,
			`**接收时间：** ${formatBeijingTime(mail.internalDate)}（北京时间）`,
			'',
			escapeMarkdown(chunk),
			attachments,
			'',
			`<!-- heuesta-mailbox:${mail.id}:${index} -->${senderMarker}`,
		].join('\n');
	});
}

module.exports = {
	MAX_BODY_CHARS,
	escapeMarkdown,
	formatBytes,
	formatBeijingTime,
	splitParagraphs,
	topicTitle,
	formatPosts,
};
