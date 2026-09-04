import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import net from "node:net";
import os from "node:os";
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

function status(username) {
  const output = djangoShell(`
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(username=${JSON.stringify(username)})
print(f'STATUS={u.member_level}:{u.is_active}')
`);
  return output.match(/STATUS=(\d+):(True|False)/)?.slice(1) || [];
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
  await page.waitForTimeout(700);
  await prepare(page);
}

async function shot(page, group, name, masks = []) {
  const folder = path.join(SHOTS, group);
  fs.mkdirSync(folder, { recursive: true });
  const maskLocators = masks.map((item) => typeof item === "string" ? page.locator(item) : item);
  await page.screenshot({
    path: path.join(folder, `${name}.png`),
    fullPage: false,
    mask: maskLocators,
    maskColor: "#071018",
  });
}

async function makeContext(browser, session) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    ignoreHTTPSErrors: true,
  });
  if (session) {
    await context.addCookies([{
      name: "sessionid",
      value: session,
      domain: "heuesta.cn",
      path: "/",
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    }]);
  }
  return context;
}

async function capturePendingLogin(browser, password) {
  const context = await makeContext(browser);
  const page = await context.newPage();
  await visit(page, "/accounts/login/");
  await page.locator("#id_username").fill("manual_demo_return");
  await page.locator("#id_password").fill(password);
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    page.getByRole("button", { name: "登录" }).click(),
  ]);
  await page.waitForTimeout(500);
  await prepare(page);
  await shot(page, "returning-member", "06-pending-login-blocked", ["#id_password"]);
  await context.close();
}

async function approveReturning(adminPage) {
  await visit(adminPage, "/dashboard/members/?tab=returning&q=manual_demo_return");
  const row = adminPage.locator("tbody tr").filter({ hasText: "manual_demo_return" });
  await row.waitFor({ state: "visible" });
  await shot(adminPage, "admin", "03-returning-review", [
    row.locator("td:first-child small"),
  ]);
  await row.locator('select[name="role"]').selectOption("member");
  await row.locator('input[name="note"]').fill("手册演示：资料核验通过");
  await Promise.all([
    adminPage.waitForLoadState("domcontentloaded"),
    row.getByRole("button", { name: "通过并激活" }).click(),
  ]);
  await visit(adminPage, "/dashboard/members/?tab=all&q=manual_demo_return");
  await shot(adminPage, "admin", "04-returning-approved", [
    adminPage.locator("tbody tr td:nth-child(2) small"),
  ]);
  const [level, active] = status("manual_demo_return");
  if (level !== "3" || active !== "True") {
    throw new Error(`Returning member approval failed: ${level}/${active}`);
  }
}

async function captureAdminPages(adminPage) {
  const routes = [
    ["01-dashboard-overview", "/dashboard/"],
    ["02-member-search", "/dashboard/members/?tab=all&q=manual_demo"],
    ["10-news-management", "/dashboard/news/"],
    ["11-news-editor", "/dashboard/news/new/"],
    ["12-event-management", "/dashboard/events/"],
    ["13-event-editor", "/dashboard/events/new/"],
    ["14-resource-management", "/dashboard/resources/"],
    ["15-project-management", "/dashboard/projects/"],
    ["16-project-editor", "/dashboard/projects/new/"],
    ["17-honor-management", "/dashboard/honors/"],
    ["18-media-center", "/dashboard/media/"],
    ["19-feedback-management", "/dashboard/feedbacks/"],
    ["20-showcase-moderation", "/showcase/moderation/"],
    ["21-medal-management", "/dashboard/medals/"],
    ["22-position-management", "/dashboard/positions/?candidate_q=manual_demo_return"],
    ["23-site-settings", "/dashboard/site/"],
  ];
  for (const [name, route] of routes) {
    await visit(adminPage, route);
    const masks = [];
    if (name === "19-feedback-management") masks.push(adminPage.locator("tbody tr"));
    if (name === "02-member-search") masks.push(adminPage.locator("tbody tr td:nth-child(2) small"));
    await shot(adminPage, "admin", name, masks);
  }
}

async function setRecruitmentStatus(adminPage, memberPage, key, suffix) {
  await visit(adminPage, "/dashboard/recruitment/");
  const row = adminPage.locator("tbody tr").filter({ hasText: "manual_demo_new" });
  await row.waitFor({ state: "visible" });
  const privateRows = adminPage.locator("tbody tr").filter({ hasNotText: "manual_demo_new" });
  await shot(adminPage, "admin", `06-recruitment-${suffix}`, [privateRows]);
  await row.getByRole("link", { name: "详情" }).click();
  await adminPage.waitForLoadState("domcontentloaded");
  await prepare(adminPage);
  if (suffix === "submitted") {
    await shot(adminPage, "admin", "07-application-detail", [
      adminPage.locator(".dash-dl dd").nth(2),
      adminPage.locator(".dash-dl dd").nth(6),
      adminPage.locator(".dash-dl dd").nth(7),
      adminPage.locator(".dash-dl dd").nth(8),
      adminPage.locator(".dash-dl dd").nth(9),
    ]);
  }
  await adminPage.locator("#id_note").fill(`手册演示：${suffix}`);
  await Promise.all([
    adminPage.waitForLoadState("domcontentloaded"),
    adminPage.locator(`[data-recruit-result="${key}"]`).click(),
  ]);
  await visit(memberPage, "/recruitment/");
  await memberPage.locator("#rec-apply").scrollIntoViewIfNeeded();
  await shot(memberPage, "recruitment", `13-status-${suffix}`);
}

async function captureReturningMember(browser, password) {
  const context = await makeContext(browser);
  const page = await context.newPage();
  await visit(page, "/accounts/login/");
  await page.locator("#id_username").fill("manual_demo_return");
  await page.locator("#id_password").fill(password);
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    page.getByRole("button", { name: "登录" }).click(),
  ]);
  await page.waitForTimeout(500);
  await prepare(page);
  await shot(page, "returning-member", "07-first-login-success");

  const pages = [
    ["08-profile-center", "/accounts/profile/", [".profile-grid"]],
    ["09-profile-edit", "/accounts/profile/edit/", ["#id_phone", "#id_qq", "#id_birthday"]],
    ["10-notifications", "/notify/", []],
    ["11-member-resources", "/resources/", []],
    ["12-member-events", "/events/", []],
    ["13-member-projects", "/projects/", []],
    ["14-public-works", "/works/", []],
  ];
  for (const [name, route, masks] of pages) {
    await visit(page, route);
    await shot(page, "returning-member", name, masks);
  }

  await visit(page, "https://bbs.heuesta.cn/");
  await shot(page, "returning-member", "15-forum-sso");
  await context.close();
}

async function main() {
  const secrets = JSON.parse(fs.readFileSync(path.join(os.tmpdir(), "heuesta-manual-demo-secrets.json"), "utf8"));
  const adminSession = fs.readFileSync(path.join(os.tmpdir(), "heuesta_manual_admin_session.txt"), "utf8").trim();
  const newSession = fs.readFileSync(path.join(os.tmpdir(), "heuesta_manual_new_session.txt"), "utf8").trim();
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
    await capturePendingLogin(browser, secrets.returningPassword);

    const adminContext = await makeContext(browser, adminSession);
    const adminPage = await adminContext.newPage();
    await approveReturning(adminPage);

    const newContext = await makeContext(browser, newSession);
    const memberPage = await newContext.newPage();
    await setRecruitmentStatus(adminPage, memberPage, "reject", "rejected");
    await setRecruitmentStatus(adminPage, memberPage, "reset", "submitted");
    await setRecruitmentStatus(adminPage, memberPage, "first_pass", "first-pass");
    await setRecruitmentStatus(adminPage, memberPage, "second_pass", "second-pass");

    await captureAdminPages(adminPage);
    await captureReturningMember(browser, secrets.returningPassword);

    await newContext.close();
    await adminContext.close();
  } finally {
    await browser.close();
    for (const socket of proxy.sockets) socket.destroy();
    await new Promise((resolve) => proxy.server.close(resolve));
  }

  console.log(`manual_demo_new=${status("manual_demo_new").join(":")}`);
  console.log(`manual_demo_return=${status("manual_demo_return").join(":")}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
