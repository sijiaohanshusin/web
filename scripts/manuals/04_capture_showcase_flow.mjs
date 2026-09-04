import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import net from "node:net";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const SHOTS = path.join(ROOT, "docs", "manuals", "assets", "screenshots", "returning-member");
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://heuesta.cn";
const ORIGIN_IP = process.env.MANUAL_ORIGIN_IP?.trim();
const SSH_TARGET = process.env.MANUAL_SSH_TARGET?.trim();
const ASSETS = [
  path.join(ROOT, "app", "static", "img", "photo", "bench-scopes.webp"),
  path.join(ROOT, "app", "static", "img", "photo", "rf-modules-board.webp"),
];

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
  if (!match) throw new Error("Could not create returning-member session");
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

async function shot(page, name, masks = []) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({
    path: path.join(SHOTS, `${name}.png`),
    fullPage: false,
    mask: masks,
    maskColor: "#071018",
  });
}

async function makeContext(browser, session, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, ignoreHTTPSErrors: true });
  await context.addCookies([{
    name: "sessionid",
    value: session,
    domain: "heuesta.cn",
    path: "/",
    httpOnly: true,
    secure: true,
    sameSite: "Lax",
  }]);
  return context;
}

async function waitForEditor(page) {
  await page.waitForSelector("#showcase-editor");
  await page.waitForFunction(() => {
    const text = document.querySelector("#save-state")?.textContent || "";
    return text && !text.includes("正在加载");
  });
}

async function section(page, name) {
  const link = page.locator(`[data-section-link="${name}"]`).first();
  await link.click();
  await page.waitForFunction((target) => document.querySelector(".se-workbench")?.dataset.section === target, name);
  await page.waitForTimeout(500);
}

async function setField(page, name, value) {
  const field = page.locator(`[data-field="${name}"]`);
  await field.fill(String(value));
  await field.dispatchEvent("input");
}

async function chooseAsset(page, pathName, index = 0) {
  await page.locator(`[data-pick="${pathName}"]`).click();
  const dialog = page.locator("#asset-picker");
  await dialog.waitFor({ state: "visible" });
  const options = dialog.locator("[data-select-asset]");
  const count = await options.count();
  if (!count) throw new Error(`No assets available for ${pathName}`);
  await options.nth(Math.min(index, count - 1)).click();
  await dialog.waitFor({ state: "hidden" });
  await page.waitForTimeout(500);
}

async function uploadIfNeeded(page) {
  await section(page, "assets");
  let count = await page.locator(".se-asset-grid .se-asset").count();
  for (const file of ASSETS.slice(count, 2)) {
    const input = page.locator("[data-file-input]").first();
    await input.setInputFiles(file);
    await page.waitForFunction((previous) => document.querySelectorAll(".se-asset-grid .se-asset").length > previous, count);
    count = await page.locator(".se-asset-grid .se-asset").count();
  }
  await shot(page, "23-showcase-assets");
}

async function fillShowcase(page) {
  await section(page, "card-layout");
  await page.locator('[data-set="card.template"][data-value="gallery"]').click();
  await setField(page, "nickname", "电路旅人");
  await page.locator('[data-field="cohort"]').selectOption("2024");
  await page.locator('[data-field="direction"]').selectOption("software");
  await chooseAsset(page, "content.avatar", 1);
  await shot(page, "17-showcase-card-layout");

  await section(page, "card-background");
  await page.locator('[data-set="card.background.mode"][data-value="photo"]').click();
  await chooseAsset(page, "card.background.image", 0);
  await setField(page, "card.background.x", 58);
  await setField(page, "card.background.y", 46);
  await setField(page, "card.background.zoom", 1.12);
  await page.locator('[data-field="card.background.blur"]').selectOption("soft");
  await page.locator('[data-field="card.background.mask"]').selectOption("strong");
  await shot(page, "18-showcase-card-background");

  await section(page, "card-content");
  await setField(page, "content.intro", "喜欢把想法焊进电路，也把过程认真记录下来。");
  for (const tag of ["嵌入式", "PCB 设计", "开源硬件"]) {
    await page.locator("#tag-entry").fill(tag);
    await page.locator("[data-add-tag]").click();
  }
  await shot(page, "19-showcase-card-content");

  await section(page, "page-layout");
  await page.locator('[data-set="page.template"][data-value="plate"]').click();
  await setField(page, "content.about", "我喜欢从问题出发，把模糊的想法变成可以运行、可以验证的作品。希望在协会里认识更多愿意一起动手的人。");
  await setField(page, "content.skills", "嵌入式开发、PCB 设计、焊接调试、技术写作");
  await chooseAsset(page, "content.cover", 0);
  await shot(page, "20-showcase-page-layout");

  await section(page, "page-works");
  if (await page.locator("[data-add-work]").isVisible()) await page.locator("[data-add-work]").click();
  await setField(page, "content.works.0.title", "桌面信号观察器");
  await setField(page, "content.works.0.description", "用于学习波形测量与基础调试的小型实验作品。");
  await setField(page, "content.works.0.url", "https://heuesta.cn/projects/");
  await chooseAsset(page, "content.works.0.image", 0);
  const featured = page.locator("[data-feature-work]").first();
  if (!(await featured.isChecked())) await featured.check();
  await shot(page, "21-showcase-works");

  await section(page, "page-gallery");
  await page.locator("[data-add-gallery]").click();
  const dialog = page.locator("#asset-picker");
  await dialog.waitFor({ state: "visible" });
  await dialog.locator("[data-select-asset]").nth(1).click();
  await setField(page, "content.gallery.0.caption", "调试台上的一次信号排查记录");
  await page.locator("[data-add-link]").click();
  await setField(page, "content.links.0.label", "协会官网");
  await setField(page, "content.links.0.url", "https://heuesta.cn/");
  await shot(page, "22-showcase-gallery-links");
}

async function saveDraft(page) {
  await page.locator('[data-operation="save"]').first().click();
  await page.waitForFunction(() => document.querySelector("#save-state")?.textContent.includes("草稿已保存"));
  await page.waitForTimeout(900);
}

async function captureMobile(browser, session) {
  const context = await makeContext(browser, session, { width: 390, height: 844 });
  const page = await context.newPage();
  await visit(page, "/accounts/showcase/?section=card-background");
  await waitForEditor(page);
  await page.locator("#mobile-preview").click();
  await page.waitForTimeout(600);
  await shot(page, "18b-showcase-mobile-preview");
  await context.close();
}

async function publishAndWithdraw(page) {
  await section(page, "publish");
  await page.waitForFunction(() => {
    const consent = document.querySelector("#publish-consent");
    return consent && !consent.disabled;
  });
  await shot(page, "24-showcase-publish-review");
  await page.locator("#publish-consent").check();
  await page.locator('[data-operation="publish"]').click();
  await page.waitForFunction(() => document.querySelector(".se-public-state")?.textContent.includes("已有公开版本"));
  await page.waitForTimeout(700);
  await shot(page, "24b-showcase-published-state");

  const publicUrl = await page.locator(".se-public-state a").getAttribute("href");
  await visit(page, "/team/");
  await shot(page, "25-team-wall-published");
  await visit(page, publicUrl);
  await shot(page, "26-public-showcase");

  await visit(page, "/accounts/showcase/?section=publish");
  await waitForEditor(page);
  await page.waitForFunction(() => document.querySelector('[data-operation="withdraw"]'));
  await page.locator('[data-operation="withdraw"]').click();
  await page.locator("#editor-confirm").waitFor({ state: "visible" });
  await page.locator("[data-confirm-accept]").click();
  await page.waitForFunction(() => document.querySelector(".se-public-state")?.textContent.includes("已撤回"));
  await page.waitForTimeout(500);
  await shot(page, "27-showcase-withdrawn");
}

async function captureProfile(page) {
  await visit(page, "/accounts/profile/");
  const masks = [page.locator(".profile-username")];
  for (const label of ["学号", "手机", "邮箱", "QQ"]) {
    masks.push(page.locator(".profile-meta li").filter({ hasText: label }).locator("span").nth(1));
  }
  await shot(page, "08-profile-center", masks);
}

async function main() {
  const session = createSession("manual_demo_return");
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
    const context = await makeContext(browser, session);
    const page = await context.newPage();
    await captureProfile(page);
    await visit(page, "/accounts/showcase/?section=card-layout");
    await waitForEditor(page);
    await uploadIfNeeded(page);
    await fillShowcase(page);
    await saveDraft(page);
    await captureMobile(browser, session);
    await publishAndWithdraw(page);
    await context.close();
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
