'use strict';

const { safeError } = require('./sync');

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
		async renderAdminPage(req, res) {
			const state = await services.store.getState();
			const retries = await services.store.listRetries();
			res.render('admin/plugins/heuesta-mailbox', {
				title: '公共邮箱',
				configured: services.oauth.isConfigured(),
				connected: Boolean(state.connectedEmail && await services.store.hasRefreshToken()),
				connectedEmail: state.connectedEmail || '未连接',
				lastSuccessAt: formatDate(state.lastSuccessAt),
				syncCount: Number(state.syncCount || 0),
				publishedCount: Number(state.publishedCount || 0),
				retryCount: retries.length,
				lastError: state.lastError || state.recentError || '无',
				needsReauthorization: Boolean(Number(state.needsReauthorization)),
				categoryCid: Number(state.categoryCid || 0),
				pollSeconds: services.synchronizer.pollSeconds,
				callbackUrl: services.oauth.callbackUrl,
				notice: cleanNotice(req.query.notice),
			});
		},

		async startOAuth(req, res) {
			const url = await services.oauth.authorizationUrl(req.uid);
			res.redirect(url);
		},

		async oauthCallback(req, res) {
			try {
				const result = await services.oauth.completeAuthorization(req.uid, req.query);
				const notice = result.initialConnection ?
					`已连接 ${result.email}，同步基线已建立，不会导入历史邮件。` :
					`已重新连接 ${result.email}，将从原同步游标继续处理。`;
				res.redirect(`/admin/plugins/heuesta-mailbox?notice=${encodeURIComponent(notice)}`);
			} catch (error) {
				await services.store.updateState({ lastError: safeError(error) });
				res.redirect(`/admin/plugins/heuesta-mailbox?notice=${encodeURIComponent('授权失败，请查看最近错误。')}`);
			}
		},

		async syncNow(req, res) {
			try {
				const result = await services.synchronizer.syncNow();
				const notice = result.skipped ? '尚未连接 Gmail，未执行同步。' : `同步完成：发现 ${result.candidates} 封候选邮件，发布 ${result.published} 封。`;
				res.redirect(`/admin/plugins/heuesta-mailbox?notice=${encodeURIComponent(notice)}`);
			} catch (error) {
				res.redirect(`/admin/plugins/heuesta-mailbox?notice=${encodeURIComponent('同步失败，请查看最近错误。')}`);
			}
		},
	};
};
