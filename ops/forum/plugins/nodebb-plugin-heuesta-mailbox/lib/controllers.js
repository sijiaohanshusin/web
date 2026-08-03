'use strict';

const { buildPreviewDocument } = require('./safe-html');

function formatDate(value) {
	if (!value) {
		return '尚无';
	}
	return new Intl.DateTimeFormat('zh-CN', {
		timeZone: 'Asia/Shanghai',
		dateStyle: 'medium',
		timeStyle: 'medium',
	}).format(new Date(Number(value)));
}

function cleanNotice(value) {
	return String(value || '').replace(/[<>&"']/g, '').slice(0, 300);
}

module.exports = function createControllers(services) {
	return {
		async renderPreview(req, res) {
			const token = String(req.params.token || '').toLowerCase();
			const canRead = /^[a-f0-9]{64}$/.test(token) && await services.archive.privileges.categories.can(
				'topics:read',
				services.archive.categoryCid,
				req.uid
			);
			if (!canRead) {
				return res.status(404).type('text/plain').send('Not found');
			}
			const preview = await services.store.getPreview(token);
			if (!preview || !preview.html) {
				return res.status(404).type('text/plain').send('Not found');
			}
			res.set({
				'Cache-Control': 'private, no-store',
				'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",
				'Referrer-Policy': 'no-referrer',
				'X-Content-Type-Options': 'nosniff',
				'X-Frame-Options': 'SAMEORIGIN',
			});
			return res.status(200).type('html').send(buildPreviewDocument(preview.html));
		},

		async renderAdminPage(req, res) {
			const state = await services.store.getState();
			const retries = await services.store.listRetries();
			const configured = services.imap.isConfigured();
			res.render('admin/plugins/heuesta-mailbox', {
				title: '公共邮箱',
				configured,
				connected: Boolean(configured && state.imapUidValidity),
				connectedEmail: state.imapUidValidity ? (state.connectedEmail || services.imap.user) : '尚未建立基线',
				lastSuccessAt: formatDate(state.lastSuccessAt),
				syncCount: Number(state.syncCount || 0),
				publishedCount: Number(state.publishedCount || 0),
				retryCount: retries.filter(item => item.transport === 'imap').length,
				lastError: state.lastError || state.recentError || '无',
				needsCredentialUpdate: Boolean(Number(state.needsCredentialUpdate)),
				categoryCid: Number(state.categoryCid || 0),
				pollSeconds: services.synchronizer.pollSeconds,
				imapHost: `${services.imap.host}:${services.imap.port}`,
				notice: cleanNotice(req.query.notice),
			});
		},

		async syncNow(req, res) {
			try {
				const result = await services.synchronizer.syncNow();
				let notice;
				if (result.skipped) {
					notice = '尚未配置 Gmail 应用专用密码，未执行同步。';
				} else if (result.baseline) {
					notice = 'IMAP 连接成功，同步基线已建立，不会导入历史邮件。';
				} else if (result.reset) {
					notice = 'INBOX 游标发生变化，已安全重建基线；请查看运行信息。';
				} else {
					notice = `同步完成：发现 ${result.candidates} 封候选邮件，发布 ${result.published} 封，剩余 UID 范围 ${result.remaining}。`;
				}
				res.redirect(`/admin/plugins/heuesta-mailbox?notice=${encodeURIComponent(notice)}`);
			} catch (error) {
				res.redirect(`/admin/plugins/heuesta-mailbox?notice=${encodeURIComponent('同步失败，请查看最近错误。')}`);
			}
		},
	};
};
