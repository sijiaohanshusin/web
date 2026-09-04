import { execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const OUT = path.join(ROOT, "docs", "manuals", "assets", "screenshots");
const SECRET_FILE = path.join(os.tmpdir(), "heuesta-manual-demo-secrets.json");
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://heuesta.cn";
const ORIGIN_IP = process.env.MANUAL_ORIGIN_IP?.trim();
const SSH_TARGET = process.env.MANUAL_SSH_TARGET?.trim();

if (!ORIGIN_IP || !SSH_TARGET) {
  throw new Error("Set MANUAL_ORIGIN_IP and MANUAL_SSH_TARGET before running production capture tools.");
}

const USERS = {
  new: {
    username: "manual_demo_new",
    realName: "手册演示新成员",
    studentId: "9999000001",
    college: "信息与通信工程学院",
    grade: "2026",
    specialty: "hardware",
    email: "heuesta+manual-new@gmail.com",
    phone: "19999999991",
    qq: "123456789",
  },
  returning: {
    username: "manual_demo_return",
    realName: "手册演示老会员",
    studentId: "9999000002",
    college: "信息与通信工程学院",
    grade: "2024",
    specialty: "software",
    requestedRole: "member",
    email: "heuesta+manual-returning@gmail.com",
    phone: "19999999992",
    qq: "123456788",
  },
};

function djangoShell(source) {
  const encoded = Buffer.from(source, "utf8").toString("base64");
  return execFileSync(
    "ssh",
    [
      SSH_TARGET,
      `echo ${encoded} | base64 -d | docker exec -i heuesta-app-1 python manage.py shell`,
    ],
    { encoding: "utf8", windowsHide: true },
  );
}

function userExists(username) {
  const output = djangoShell(`
from django.contrib.auth import get_user_model
print("RESULT=" + str(get_user_model().objects.filter(username=${JSON.stringify(username)}).exists()))
`);
  return /RESULT=True/.test(output);
}

function latestCode(email) {
  const output = djangoShell(`
from accounts.models import VerificationCode
r = VerificationCode.objects.filter(email=${JSON.stringify(email)}, purpose="register", used=False).order_by("-created_at").first()
print("CODE=" + (r.code if r else ""))
`);
  const match = output.match(/CODE=(\d{6})/);
  if (!match) throw new Error(`No verification code found for ${email}`);
  return match[1];
}

function loadSecrets() {
  if (fs.existsSync(SECRET_FILE)) {
    return JSON.parse(fs.readFileSync(SECRET_FILE, "utf8"));
  }
  const secrets = {
    newPassword: `Hm!${crypto.randomBytes(12).toString("base64url")}`,
    returningPassword: `Hm!${crypto.randomBytes(12).toString("base64url")}`,
  };
  fs.writeFileSync(SECRET_FILE, `${JSON.stringify(secrets, null, 2)}\n`, { mode: 0o600 });
  return secrets;
}

function startOriginProxy() {
  const server = http.createServer((request, response) => {
    response.writeHead(405);
    response.end();
  });
  server.on("connect", (request, clientSocket, head) => {
    const [requestedHost, rawPort] = request.url.split(":");
    const targetHost = requestedHost.endsWith("heuesta.cn") ? ORIGIN_IP : requestedHost;
    const targetPort = Number(rawPort || 443);
    const upstream = net.connect(targetPort, targetHost, () => {
      clientSocket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
      if (head.length) upstream.write(head);
      upstream.pipe(clientSocket);
      clientSocket.pipe(upstream);
    });
    const closeBoth = () => {
      upstream.destroy();
      clientSocket.destroy();
    };
    upstream.on("error", closeBoth);
    clientSocket.on("error", closeBoth);
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, port: address.port });
    });
  });
}

async function preparePage(page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        caret-color: transparent !important;
      }
      html { scroll-behavior: auto !important; }
    `,
  });
}

async function shot(page, group, name, { fullPage = false, masks = [] } = {}) {
  const folder = path.join(OUT, group);
  fs.mkdirSync(folder, { recursive: true });
  await page.waitForTimeout(250);
  await page.screenshot({
    path: path.join(folder, `${name}.png`),
    fullPage,
    mask: masks.map((selector) => page.locator(selector)),
    maskColor: "#071018",
  });
}

async function goto(page, url) {
  await page.goto(`${BASE}${url}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(700);
  await preparePage(page);
}

async function fillFirstStep(page, user, group) {
  await page.locator("#id_real_name").fill(user.realName);
  await page.locator("#id_student_id").fill(user.studentId);
  await page.locator("#id_college").selectOption({ label: user.college });
  await page.locator("#id_grade").selectOption(user.grade);
  if (user.requestedRole) {
    await page.locator("#id_requested_role").selectOption(user.requestedRole);
  }
  await page.locator("#id_specialty").selectOption(user.specialty);
  await shot(page, group, "02-register-step-identity", {
    masks: ["#id_student_id"],
  });
  await page.locator("[data-step-next]").click();
}

async function fillContactStep(page, user, group) {
  await page.locator("#id_email").fill(user.email);
  await page.getByRole("button", { name: "获取验证码" }).click();
  await page.getByText(/验证码已发送/).waitFor({ state: "visible", timeout: 15_000 });
  const code = latestCode(user.email);
  await page.locator("#id_code").fill(code);
  await page.locator("#id_phone").fill(user.phone);
  await page.locator("#id_qq").fill(user.qq);
  await shot(page, group, "03-register-step-contact", {
    masks: ["#id_email", "#id_code", "#id_phone", "#id_qq"],
  });
  await page.locator("[data-step-next]").click();
}

async function fillLoginStep(page, user, password, group) {
  await page.locator("#id_username").fill(user.username);
  await page.locator("#id_password1").fill(password);
  await page.locator("#id_password2").fill(password);
  await page.locator("#id_privacy_consent").check();
  await shot(page, group, "04-register-step-review", {
    masks: ["#id_email", "#id_phone", "#id_student_id", "#id_password1", "#id_password2"],
  });
}

async function register(page, channel, user, password) {
  const group = channel === "new" ? "recruitment" : "returning-member";
  console.log(`Preparing ${channel} registration`);
  await goto(page, `/accounts/register/${channel}/`);
  await shot(page, group, "01-register-entry");
  await fillFirstStep(page, user, group);
  await fillContactStep(page, user, group);
  await fillLoginStep(page, user, password, group);

  const submitName = channel === "new" ? "完成注册" : "提交身份恢复申请";
  console.log(`Submitting ${channel} registration`);
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    page.getByRole("button", { name: submitName }).click(),
  ]);
  await page.waitForTimeout(800);
  await preparePage(page);
  await shot(page, group, "05-register-success");
  return page.url();
}

async function captureChoice(page) {
  await goto(page, "/accounts/register/");
  await shot(page, "shared", "01-register-channel-choice");
}

async function captureMobileForm(browser) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  await goto(page, "/accounts/register/new/");
  await page.locator("#id_real_name").fill("手册演示新成员");
  await page.locator("#id_student_id").fill("9999000001");
  await page.locator("#id_college").selectOption({ label: "信息与通信工程学院" });
  await page.locator("#id_grade").selectOption("2026");
  await page.locator("#id_specialty").selectOption("hardware");
  await shot(page, "recruitment", "06-register-mobile", {
    masks: ["#id_student_id"],
  });
  await context.close();
}

async function main() {
  const secrets = loadSecrets();
  const proxy = await startOriginProxy();
  console.log("Launching browser");
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
      deviceScaleFactor: 1,
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();
    console.log("Capturing channel choice");
    await captureChoice(page);

    if (!userExists(USERS.new.username)) {
      console.log("New-member account does not exist");
      const result = await register(page, "new", USERS.new, secrets.newPassword);
      if (!result.includes("/recruitment/")) {
        throw new Error(`Unexpected new-member result URL: ${result}`);
      }
    }

    await context.clearCookies();
    if (!userExists(USERS.returning.username)) {
      console.log("Returning-member account does not exist");
      const result = await register(
        page,
        "returning",
        USERS.returning,
        secrets.returningPassword,
      );
      if (!result.includes("/accounts/register/")) {
        throw new Error(`Unexpected returning-member result URL: ${result}`);
      }
    }

    await context.close();
    await captureMobileForm(browser);
  } finally {
    await browser.close();
    for (const socket of proxy.sockets) socket.destroy();
    await new Promise((resolve) => proxy.server.close(resolve));
  }

  const status = djangoShell(`
from django.contrib.auth import get_user_model
U = get_user_model()
for username in ["manual_demo_new", "manual_demo_return"]:
    u = U.objects.get(username=username)
    print(f"DEMO={u.username}:{u.member_level}:{u.is_active}")
`);
  console.log(status.split(/\r?\n/).filter((line) => line.startsWith("DEMO=")).join("\n"));
  console.log(`Screenshots: ${OUT}`);
  console.log(`Secrets: ${SECRET_FILE}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
