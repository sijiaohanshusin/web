import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const OUT = path.join(ROOT, "docs", "manuals", "assets", "screenshots", "recruitment");
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://heuesta.cn";
const ORIGIN_IP = process.env.MANUAL_ORIGIN_IP?.trim();

if (!ORIGIN_IP) {
  throw new Error("Set MANUAL_ORIGIN_IP before running production capture tools.");
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
    server.listen(0, "127.0.0.1", () => resolve({
      server,
      sockets,
      port: server.address().port,
    }));
  });
}

async function prepare(page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addStyleTag({ content: `
    *, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
    html { scroll-behavior: auto !important; }
  ` });
}

async function shot(page, name, masks = []) {
  fs.mkdirSync(OUT, { recursive: true });
  await page.waitForTimeout(250);
  await page.screenshot({
    path: path.join(OUT, `${name}.png`),
    fullPage: false,
    mask: masks.map((selector) => page.locator(selector)),
    maskColor: "#071018",
  });
}

async function main() {
  const session = fs.readFileSync(path.join(os.tmpdir(), "heuesta_manual_new_session.txt"), "utf8").trim();
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
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      ignoreHTTPSErrors: true,
    });
    await context.addCookies([{
      name: "sessionid",
      value: session,
      domain: "heuesta.cn",
      path: "/",
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    }]);
    const page = await context.newPage();
    await page.goto(`${BASE}/recruitment/`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(800);
    await prepare(page);

    if (await page.getByText("你的报名", { exact: true }).isVisible().catch(() => false)) {
      console.log("Application already exists; captured current status only");
      await shot(page, "12-application-status-submitted");
      return;
    }

    await page.locator("#rec-apply").scrollIntoViewIfNeeded();
    await page.locator('input[name="department"][value="hardware"]').check();
    await shot(page, "07-application-step-direction", [".rec-identity dd:nth-of-type(2)"]);
    await page.locator("[data-step-next]").click();

    await page.locator('input[name="interests"][value="mcu"]').check();
    await page.locator('input[name="interests"][value="embedded"]').check();
    await page.locator('input[name="interests"][value="analog"]').check();
    await shot(page, "08-application-step-interests");
    await page.locator("[data-step-next]").click();

    await page.locator("#id_gender").selectOption("male");
    await page.locator("#id_birthday").fill("2007-09-01");
    await page.locator("#id_skills").fill("会一点 C 语言，做过循迹小车，希望系统学习焊接和单片机开发。");
    await shot(page, "09-application-step-profile", ["#id_birthday"]);
    await page.locator("[data-step-next]").click();

    await page.locator("#id_self_intro").fill("我喜欢把想法做成可以运行的实物，希望在协会里学习电路设计并认识一起做项目的同学。");
    await page.locator("#id_first_impression").fill("看过协会的电赛作品，感觉大家既专业也愿意分享。");
    await page.locator("#id_motto").fill("完成一个真正解决问题、能够长期维护的作品。");
    await shot(page, "10-application-step-introduction");

    await page.setViewportSize({ width: 390, height: 844 });
    await shot(page, "10b-application-mobile");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("[data-step-next]").click();

    await page.locator('input[name="heard_from"][value="online"]').check();
    await page.locator('input[name="heard_from"][value="senior"]').check();
    await shot(page, "11-application-step-confirm");

    await Promise.all([
      page.waitForLoadState("domcontentloaded"),
      page.getByRole("button", { name: "提交报名" }).click(),
    ]);
    await page.waitForTimeout(800);
    await prepare(page);
    await page.locator("#rec-apply").scrollIntoViewIfNeeded();
    await shot(page, "12-application-status-submitted");
    console.log(`Submitted application at ${page.url()}`);
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
