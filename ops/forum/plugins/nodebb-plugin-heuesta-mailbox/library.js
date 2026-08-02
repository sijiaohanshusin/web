'use strict';

const winston = module.parent.require('winston');
const slugify = require.main.require('./src/slugify');
const db = require.main.require('./src/database');
const user = require.main.require('./src/user');
const groups = require.main.require('./src/groups');
const categories = require.main.require('./src/categories');
const privileges = require.main.require('./src/privileges');
const topics = require.main.require('./src/topics');
const posts = require.main.require('./src/posts');
const routeHelpers = require.main.require('./src/routes/helpers');

const MailboxStore = require('./lib/store');
const { GmailOAuth } = require('./lib/oauth');
const { ForumArchive } = require('./lib/forum');
const { MailboxSynchronizer } = require('./lib/sync');
const createControllers = require('./lib/controllers');

const CALLBACK_URL = 'https://bbs.heuesta.cn/admin/plugins/heuesta-mailbox/oauth/callback';
const plugin = {};
let services;

plugin.init = async ({ router }) => {
	const store = new MailboxStore(db, process.env.MAILBOX_TOKEN_ENCRYPTION_KEY || '');
	const oauth = new GmailOAuth({
		clientId: process.env.GMAIL_OAUTH_CLIENT_ID || '',
		clientSecret: process.env.GMAIL_OAUTH_CLIENT_SECRET || '',
		callbackUrl: CALLBACK_URL,
		store,
	});
	const archive = new ForumArchive({ db, user, groups, categories, privileges, topics, posts, slugify, store });
	await archive.ensureInfrastructure();
	const synchronizer = new MailboxSynchronizer({
		store,
		oauth,
		archive,
		logger: winston,
		pollSeconds: process.env.MAILBOX_POLL_SECONDS || 300,
	});
	services = { store, oauth, archive, synchronizer };
	const controllers = createControllers(services);

	routeHelpers.setupAdminPageRoute(router, '/admin/plugins/heuesta-mailbox', controllers.renderAdminPage);
	router.post('/admin/plugins/heuesta-mailbox/oauth/start', controllers.startOAuth);
	router.get('/admin/plugins/heuesta-mailbox/oauth/callback', controllers.oauthCallback);
	router.post('/admin/plugins/heuesta-mailbox/sync', controllers.syncNow);
	synchronizer.start();

	winston.info(`[heuesta-mailbox] ready (category ${archive.categoryCid}, poll ${synchronizer.pollSeconds}s)`);
};

plugin.addAdminNavigation = async (header) => {
	header.plugins.push({
		route: '/plugins/heuesta-mailbox',
		icon: 'fa-envelope-open-text',
		name: '公共邮箱',
	});
	return header;
};

plugin.guardTopicPost = async (data) => {
	if (services && Number(data.cid) === Number(services.archive.categoryCid) && Number(data.uid) !== Number(services.archive.botUid)) {
		throw new Error('[[error:no-privileges]]');
	}
	return data;
};

plugin.guardTopicReply = async (data) => {
	if (!services || Number(data.uid) === Number(services.archive.botUid)) {
		return data;
	}
	const cid = await topics.getTopicField(data.tid, 'cid');
	if (Number(cid) === Number(services.archive.categoryCid)) {
		throw new Error('[[error:no-privileges]]');
	}
	return data;
};

module.exports = plugin;
