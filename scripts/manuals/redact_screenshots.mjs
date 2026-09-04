import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const sharp = require("sharp");
const root = path.resolve(import.meta.dirname, "..", "..", "docs", "manuals", "assets", "screenshots");

const edits = [
  ["recruitment/07-application-step-direction.png", { left: 1138, top: 430, width: 165, height: 32 }],
  ["recruitment/08-application-step-interests.png", { left: 1138, top: 214, width: 165, height: 32 }],
  ["recruitment/09-application-step-profile.png", { left: 1138, top: 214, width: 165, height: 32 }],
  ["recruitment/10-application-step-introduction.png", { left: 1138, top: 170, width: 165, height: 32 }],
  ["returning-member/15-forum-sso.png", { left: 1055, top: 579, width: 315, height: 421 }],
];

for (const [relativePath, rect] of edits) {
  const input = path.join(root, relativePath);
  const output = `${input}.redacted.png`;
  await sharp(input)
    .composite([{
      input: { create: { ...rect, channels: 4, background: "#071018" } },
      left: rect.left,
      top: rect.top,
    }])
    .png()
    .toFile(output);
  fs.renameSync(output, input);
}
