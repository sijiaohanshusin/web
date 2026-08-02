<div class="acp-page-container">
	<div class="d-flex justify-content-between align-items-center mb-4">
		<div>
			<h3 class="mb-1">公共邮箱</h3>
			<p class="text-muted mb-0">Gmail IMAP 只读归档状态</p>
		</div>
	</div>

	{{{ if notice }}}<div class="alert alert-info">{notice}</div>{{{ end }}}
	{{{ if needsCredentialUpdate }}}
	<div class="alert alert-danger"><strong>Gmail 登录失败。</strong> 请重新生成应用专用密码并更新服务器环境变量。</div>
	{{{ end }}}
	<div class="alert alert-warning">
		<strong>敏感信息提示：</strong>本功能会把启用后进入 heuesta@gmail.com 收件箱的全部邮件归档到会员私密版块，包括验证码、密码重置和安全提醒。请严格控制会员组权限。
	</div>

	<div class="row g-3 mb-4">
		<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body"><div class="text-muted small">连接账号</div><div class="fw-semibold mt-1">{connectedEmail}</div></div></div></div>
		<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body"><div class="text-muted small">最后成功</div><div class="fw-semibold mt-1">{lastSuccessAt}</div></div></div></div>
		<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body"><div class="text-muted small">同步 / 发布</div><div class="fw-semibold mt-1">{syncCount} / {publishedCount}</div></div></div></div>
		<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body"><div class="text-muted small">待重试</div><div class="fw-semibold mt-1">{retryCount}</div></div></div></div>
	</div>

	<div class="card mb-4">
		<div class="card-header fw-semibold">操作</div>
		<div class="card-body d-flex flex-wrap gap-2">
			<form method="post" action="/admin/plugins/heuesta-mailbox/sync">
				<input type="hidden" name="_csrf" value="{config.csrf_token}" />
				<button class="btn btn-primary" type="submit"{{{ if !configured }}} disabled{{{ end }}}>建立基线 / 立即同步</button>
			</form>
			{{{ if categoryCid }}}<a class="btn btn-outline-secondary" href="/category/{categoryCid}" target="_blank" rel="noopener">打开公共邮箱版块</a>{{{ end }}}
		</div>
	</div>

	<div class="card mb-4">
		<div class="card-header fw-semibold">运行信息</div>
		<div class="card-body">
			<dl class="row mb-0">
				<dt class="col-sm-3">环境配置</dt><dd class="col-sm-9">{{{ if configured }}}已配置 Gmail 应用专用密码{{ else }}}缺少 GMAIL_APP_PASSWORD 或账号不匹配{{{ end }}}</dd>
				<dt class="col-sm-3">IMAP 源站</dt><dd class="col-sm-9"><code>{imapHost}</code>（TLS，只读 INBOX）</dd>
				<dt class="col-sm-3">轮询间隔</dt><dd class="col-sm-9">{pollSeconds} 秒</dd>
				<dt class="col-sm-3">最近错误</dt><dd class="col-sm-9 text-break">{lastError}</dd>
			</dl>
		</div>
	</div>
</div>
