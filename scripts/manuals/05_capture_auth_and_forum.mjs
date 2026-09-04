import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import net from "node:net";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const SHOTS = path.join(ROOT, "docs", "manuals", "assets", "screenshots");
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://heuesta.cn";
const ORIGIN_IP = process.env.MANUAL_ORIGIN_IP?.trim();
const SSH_TARGET = process.env.MANUAL_SSH_TARGET?.trim();

if (!ORIGIN_IP || !SSH_TARGET) {
  throw new Error("Set MANUAL_ORIGIN_IP and MANUAL_SSH_TARGET before running production capture tools.");
}

function djangoShell(source) {
  const encoded = Buffer.from(source, "utf8").toString("base64");
  return execFileSync("ssh", [
    SSH_TARGET,
    `echo ${encoded} | base64 -d | docker exec -i heuesta-app-1 python manage.py shell`,
  ], { encoding: "utf8", windowsHide: true });
}

function createSession(username) {
  const output = djangoShell(`
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
u = get_user_model().objects.get(username=${JSON.stringify(username)})
s = SessionStore()
s['_auth_user_id'] = str(u.pk)
s['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
s['_auth_user_hash'] = u.get_session_auth_hash()
s.set_expiry(21600)
s.save()
print('SESSION=' + s.session_key)
`);
  const match = output.match(/SESSION=([a-z0-9]+)/);
  if (!match) throw new Error(`Could not create session for ${username}`);
  return match[1];
}

function startOriginProxy() {
  const sockets = new Set();
  const server = http.createServer((_request, response) => {
    response.writeHead(405);
    response.end();
  });
  server.on("connect", (request, clientSocket, head) => {
    const [requestedHost, rawPort] = request.url.split(":");
    const targetHost = requestedHost.endsWith("heuesta.cn") ? ORIGIN_IP : requestedHost;
    const upstream = net.connect(Number(rawPort || 443), targetHost, () => {
      clientSocket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
      if (head.length) upstream.write(head);
      upstream.pipe(clientSocket);
      clientSocket.pipe(upstream);
    });
    sockets.add(clientSocket);
    sockets.add(upstream);
    const forget = (socket) => sockets.delete(socket);
    clientSocket.on("close", () => forget(clientSocket));
    upstream.on("close", () => forget(upstream));
    clientSocket.on("error", () => clientSocket.destroy());
    upstream.on("error", () => upstream.destroy());
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve({ server, sockets, port: server.address().port }));
  });
}

async function prepare(page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addStyleTag({ content: `
    *, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
    html { scroll-behavior: auto !important; }
  ` });
}

async function visit(page, url) {
  await page.goto(url.startsWith("http") ? url : `${BASE}${url}`, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  await page.waitForTimeout(800);
  await prepare(page);
}

async function shot(page, group, name, masks = []) {
  const folder = path.join(SHOTS, group);
  fs.mkdirSync(folder, { recursive: true });
  await page.screenshot({
    path: path.join(folder, `${name}.png`),
    fullPage: false,
    mask: masks,
    maskColor: "#071018",
  });
}

async function context(browser, session, viewport = { width: 1440, height: 1000 }) {
  const result = await browser.newContext({ viewport, ignoreHTTPSErrors: true });
  if (session) {
    await result.addCookies([{
      name: "sessionid",
      value: session,
      domain: "heuesta.cn",
      path: "/",
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    }]);
  }
  return result;
}

async function capturePublicAuth(browser) {
  const desktop = await context(browser);
  const page = await desktop.newPage();
  await visit(page, "/accounts/login/");
  await shot(page, "shared", "02-password-login");
  await visit(page, "/accounts/login/code/");
  await shot(page, "shared", "03-email-code-login");
  await visit(page, "/accounts/forgot/");
  await shot(page, "shared", "04-password-reset");
  await desktop.close();

  const mobile = await context(browser, null, { width: 390, height: 844 });
  const mobilePage = await mobile.newPage();
  await visit(mobilePage, "/accounts/login/");
  await shot(mobilePage, "shared", "05-login-mobile");
  await mobile.close();
}

async function captureMemberAuth(browser, session) {
  const member = await context(browser, session);
  const page = await member.newPage();
  await visit(page, "/accounts/password/change/");
  await shot(page, "returning-member", "09b-password-change", [
    page.locator('input[type="password"]'),
  ]);

  await visit(page, "https://bbs.heuesta.cn/");
  await page.evaluate(() => {
    const heading = [...document.querySelectorAll("*")].find((node) => node.children.length === 0 && node.textContent.trim() === "最新主题");
    let panel = heading;
    while (panel?.parentElement && panel.getBoundingClientRect().height < 260) panel = panel.parentElement;
    if (panel) panel.dataset.manualMask = "latest-topics";
  });
  const topicMasks = [
    page.locator('[component="category/topic"]'),
    page.locator('[component="topic/teaser"]'),
    page.locator(".topic-list"),
    page.locator(".recent-card"),
    page.locator('[data-manual-mask="latest-topics"]'),
  ];
  await shot(page, "returning-member", "15-forum-sso", topicMasks);
  const mailbox = page.getByRole("link", { name: /公共邮箱/ }).first();
  if (await mailbox.count()) {
    await mailbox.click();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(800);
    await prepare(page);
    await shot(page, "returning-member", "15b-forum-public-mailbox", [
      page.locator('[component="category/topic"]'),
      page.locator('[component="topic/teaser"]'),
      page.locator(".topic-list"),
      page.locator("tbody"),
    ]);
  }
  await member.close();
}

async function captureForumAdmin(browser, session) {
  const admin = await context(browser, session);
  const page = await admin.newPage();
  await visit(page, "https://bbs.heuesta.cn/");
  await visit(page, "https://bbs.heuesta.cn/admin/plugins/heuesta-mailbox");
  const body = await page.locator("body").innerText();
  if (!/禁止访问|Access Denied|登录/.test(body)) {
    await shot(page, "admin", "24-forum-mailbox-status", [
      page.locator('input[type="password"]'),
      page.locator("[data-secret]"),
    ]);
  }
  await admin.close();
}

async function main() {
  const memberSession = createSession("manual_demo_return");
  const adminSession = createSession("admin");
  const proxy = await startOriginProxy();
  const browser = await chromium.launch({
    headless: true,
    executablePath: EDGE,
    args: [
      `--proxy-server=http://127.0.0.1:${proxy.port}`,
      "--disable-quic",
      "--disable-features=UseDnsHttpsSvcbAlpn,AsyncDns",
    ],
  });
  try {
    await capturePublicAuth(browser);
    await captureMemberAuth(browser, memberSession);
    await captureForumAdmin(browser, adminSession);
  } finally {
    await browser.close();
    for (const socket of proxy.sockets) socket.destroy();
    await new Promise((resolve) => proxy.server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
