<div class="acp-page-container">
	<div class="d-flex justify-content-between align-items-center mb-4">
		<div>
			<h3 class="mb-1">公共邮箱</h3>
			<p class="text-muted mb-0">Gmail API 只读同步状态与授权管理</p>
		</div>
	</div>

	{{{ if notice }}}
	<div class="alert alert-info">{notice}</div>
	{{{ end }}}
	{{{ if needsReauthorization }}}
	<div class="alert alert-danger"><strong>需要重新授权。</strong> 当前刷新令牌已失效，自动同步已暂停。</div>
	{{{ end }}}
	<div class="alert alert-warning">
		<strong>敏感信息提示：</strong>本功能会把上线后进入 heuesta@gmail.com 收件箱的全部邮件归档到会员私密版块，包括验证码、密码重置和安全提醒。请严格控制会员组权限。
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
			<form method="post" action="/admin/plugins/heuesta-mailbox/oauth/start">
				<input type="hidden" name="_csrf" value="{config.csrf_token}" />
				<button class="btn btn-primary" type="submit"{{{ if !configured }}} disabled{{{ end }}}>连接 / 重新连接 Gmail</button>
			</form>
			<form method="post" action="/admin/plugins/heuesta-mailbox/sync">
				<input type="hidden" name="_csrf" value="{config.csrf_token}" />
				<button class="btn btn-outline-primary" type="submit"{{{ if !connected }}} disabled{{{ end }}}>立即同步</button>
			</form>
			{{{ if categoryCid }}}<a class="btn btn-outline-secondary" href="/category/{categoryCid}" target="_blank" rel="noopener">打开公共邮箱版块</a>{{{ end }}}
		</div>
	</div>

	<div class="card mb-4">
		<div class="card-header fw-semibold">运行信息</div>
		<div class="card-body">
			<dl class="row mb-0">
				<dt class="col-sm-3">环境配置</dt><dd class="col-sm-9">{{{ if configured }}}已配置{{{ else }}}缺少 OAuth 客户端或令牌加密密钥{{{ end }}}</dd>
				<dt class="col-sm-3">轮询间隔</dt><dd class="col-sm-9">{pollSeconds} 秒</dd>
				<dt class="col-sm-3">OAuth 回调</dt><dd class="col-sm-9"><code>{callbackUrl}</code></dd>
				<dt class="col-sm-3">最近错误</dt><dd class="col-sm-9 text-break">{lastError}</dd>
			</dl>
		</div>
	</div>
</div>
