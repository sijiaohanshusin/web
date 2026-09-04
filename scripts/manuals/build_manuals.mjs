import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const sharp = require("sharp");
const {
  AlignmentType,
  BorderStyle,
  Document,
  ExternalHyperlink,
  Footer,
  Header,
  HeadingLevel,
  ImageRun,
  PageBreak,
  PageNumber,
  Paragraph,
  Packer,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  VerticalAlign,
  WidthType,
} = require("docx");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const manualsDir = path.join(repoRoot, "docs", "manuals");
const outputDir = path.join(manualsDir, "dist");
const logoPath = path.join(repoRoot, "app", "static", "img", "logo-mark.png");

const A4 = { width: 11906, height: 16838 };
const margins = { top: 900, right: 1000, bottom: 900, left: 1000 };
const contentWidthTwips = A4.width - margins.left - margins.right;

const colors = {
  ink: "17212B",
  navy: "07131D",
  navySoft: "0E2433",
  cyan: "13B5D1",
  blue: "2568C8",
  copper: "C78B47",
  muted: "657786",
  pale: "EAF8FB",
  line: "D7E2E8",
  paper: "FFFFFF",
  warning: "FFF5E8",
  warningText: "8A4D13",
};

const manuals = [
  {
    source: "招新注册手册.md",
    output: "HEU_ESTA_招新注册手册_2026.docx",
    shortTitle: "招新注册手册",
    kicker: "RECRUITMENT GUIDE",
    accent: colors.cyan,
    internal: false,
  },
  {
    source: "老会员使用手册.md",
    output: "HEU_ESTA_老会员使用手册_2026.docx",
    shortTitle: "老会员使用手册",
    kicker: "MEMBER GUIDE",
    accent: colors.blue,
    internal: false,
  },
  {
    source: "网站管理手册.md",
    output: "HEU_ESTA_网站管理手册_2026.docx",
    shortTitle: "网站管理手册",
    kicker: "ADMINISTRATION GUIDE",
    accent: colors.copper,
    internal: true,
  },
];

function parseFrontmatter(source) {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) return { metadata: {}, body: source };

  const metadata = {};
  for (const line of match[1].split(/\r?\n/)) {
    const separator = line.indexOf(":");
    if (separator < 0) continue;
    metadata[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
  }
  return { metadata, body: source.slice(match[0].length) };
}

function stripMarkdown(text) {
  return text
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<([^>]+)>/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function inlineChildren(text, base = {}) {
  const children = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\)|<https?:\/\/[^>]+>|https?:\/\/[^\s，。；）]+)/g;
  let cursor = 0;

  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) {
      children.push(new TextRun({ text: text.slice(cursor, match.index), ...base }));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      children.push(new TextRun({ text: token.slice(2, -2), bold: true, ...base }));
    } else if (token.startsWith("`")) {
      children.push(
        new TextRun({
          text: token.slice(1, -1),
          font: "Consolas",
          color: colors.navySoft,
          shading: { type: ShadingType.CLEAR, fill: "E8F0F4" },
          ...base,
        }),
      );
    } else {
      let label;
      let link;
      if (token.startsWith("[")) {
        const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
        label = linkMatch?.[1] ?? token;
        link = linkMatch?.[2] ?? token;
      } else if (token.startsWith("<")) {
        label = token.slice(1, -1);
        link = label;
      } else {
        label = token.replace(/[，。；）]+$/, "");
        link = label;
      }
      children.push(
        new ExternalHyperlink({
          link,
          children: [new TextRun({ text: label, color: colors.blue, underline: {}, ...base })],
        }),
      );
      if (label.length !== token.length && !token.startsWith("<") && !token.startsWith("[")) {
        children.push(new TextRun({ text: token.slice(label.length), ...base }));
      }
    }
    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    children.push(new TextRun({ text: text.slice(cursor), ...base }));
  }
  return children.length ? children : [new TextRun({ text, ...base })];
}

function border(color = colors.line, size = 5) {
  return { style: BorderStyle.SINGLE, color, size };
}

function noBorders() {
  return {
    top: { style: BorderStyle.NIL },
    right: { style: BorderStyle.NIL },
    bottom: { style: BorderStyle.NIL },
    left: { style: BorderStyle.NIL },
    insideHorizontal: { style: BorderStyle.NIL },
    insideVertical: { style: BorderStyle.NIL },
  };
}

function infoBand(text, accent, kind = "info") {
  const warning = kind === "warning";
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: noBorders(),
    rows: [
      new TableRow({
        cantSplit: true,
        children: [
          new TableCell({
            width: { size: 240, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, fill: warning ? colors.copper : accent },
            margins: { top: 100, right: 0, bottom: 100, left: 0 },
            children: [new Paragraph({ children: [new TextRun("")] })],
          }),
          new TableCell({
            shading: { type: ShadingType.CLEAR, fill: warning ? colors.warning : colors.pale },
            margins: { top: 150, right: 220, bottom: 150, left: 220 },
            children: [
              new Paragraph({
                spacing: { after: 0, line: 280 },
                children: inlineChildren(text, {
                  color: warning ? colors.warningText : colors.ink,
                  size: 19,
                }),
              }),
            ],
          }),
        ],
      }),
    ],
  });
}

async function imageParagraph(imagePath, alt) {
  const data = await fs.readFile(imagePath);
  const metadata = await sharp(data).metadata();
  const width = metadata.width ?? 1440;
  const height = metadata.height ?? 900;
  const portrait = height / width > 1.15;
  const maxWidth = portrait ? 315 : 635;
  const maxHeight = portrait ? 530 : 430;
  const scale = Math.min(maxWidth / width, maxHeight / height, 1);
  const displayWidth = Math.max(1, Math.round(width * scale));
  const displayHeight = Math.max(1, Math.round(height * scale));

  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    alignment: AlignmentType.CENTER,
    borders: {
      top: border(colors.line, 6),
      right: border(colors.line, 6),
      bottom: border(colors.line, 6),
      left: border(colors.line, 6),
      insideHorizontal: { style: BorderStyle.NIL },
      insideVertical: { style: BorderStyle.NIL },
    },
    rows: [
      new TableRow({
        cantSplit: true,
        children: [
          new TableCell({
            verticalAlign: VerticalAlign.CENTER,
            shading: { type: ShadingType.CLEAR, fill: "F4F7F9" },
            margins: { top: 100, right: 100, bottom: 100, left: 100 },
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 0 },
                children: [
                  new ImageRun({
                    data,
                    type: "png",
                    altText: { title: alt, description: alt, name: alt },
                    transformation: { width: displayWidth, height: displayHeight },
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
    ],
  });
}

function captionParagraph(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 70, after: 230 },
    keepLines: true,
    children: [new TextRun({ text: stripMarkdown(text), italics: true, color: colors.muted, size: 17 })],
  });
}

function makeHeader(manual, logoData) {
  return new Header({
    children: [
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: noBorders(),
        rows: [
          new TableRow({
            children: [
              new TableCell({
                width: { size: 620, type: WidthType.DXA },
                verticalAlign: VerticalAlign.CENTER,
                shading: { type: ShadingType.CLEAR, fill: colors.navy },
                margins: { top: 70, right: 70, bottom: 70, left: 70 },
                children: [
                  new Paragraph({
                    alignment: AlignmentType.CENTER,
                    spacing: { after: 0 },
                    children: [
                      new ImageRun({ data: logoData, type: "png", transformation: { width: 26, height: 26 } }),
                    ],
                  }),
                ],
              }),
              new TableCell({
                verticalAlign: VerticalAlign.CENTER,
                children: [
                  new Paragraph({
                    alignment: AlignmentType.LEFT,
                    spacing: { after: 0 },
                    children: [
                      new TextRun({ text: `HEU ESTA  /  ${manual.shortTitle}`, bold: true, color: colors.ink, size: 18 }),
                    ],
                  }),
                ],
              }),
              new TableCell({
                width: { size: 2050, type: WidthType.DXA },
                verticalAlign: VerticalAlign.CENTER,
                children: [
                  new Paragraph({
                    alignment: AlignmentType.RIGHT,
                    spacing: { after: 0 },
                    children: [
                      new TextRun({
                        text: manual.internal ? "内部使用  ·  2026" : "使用手册  ·  2026",
                        bold: true,
                        color: manual.internal ? colors.warningText : colors.muted,
                        size: 16,
                      }),
                    ],
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
      new Paragraph({
        spacing: { before: 80, after: 0 },
        border: { bottom: border(manual.accent, 12) },
        children: [new TextRun("")],
      }),
    ],
  });
}

function makeFooter(metadata) {
  return new Footer({
    children: [
      new Paragraph({
        border: { top: border(colors.line, 5) },
        spacing: { before: 100, after: 0 },
        children: [
          new TextRun({ text: `heuesta.cn  ·  截图 ${metadata.screenshot_date}  ·  站点 ${metadata.site_version}`, color: colors.muted, size: 15 }),
          new TextRun({ text: "                                             ", size: 15 }),
          new TextRun({ text: "第 ", color: colors.muted, size: 15 }),
          new TextRun({ children: [PageNumber.CURRENT], color: colors.muted, size: 15 }),
          new TextRun({ text: " 页", color: colors.muted, size: 15 }),
        ],
      }),
    ],
  });
}

function coverSection(manual, metadata, logoData) {
  const title = metadata.title || `HEU ESTA ${manual.shortTitle}`;
  const visibility = metadata.visibility || (manual.internal ? "内部使用" : "公开");
  return {
    properties: {
      page: { size: A4, margin: { top: 780, right: 780, bottom: 780, left: 780 } },
    },
    children: [
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: noBorders(),
        rows: [
          new TableRow({
            height: { value: 11800, rule: "atLeast" },
            children: [
              new TableCell({
                verticalAlign: VerticalAlign.CENTER,
                shading: { type: ShadingType.CLEAR, fill: colors.navy },
                margins: { top: 850, right: 900, bottom: 850, left: 900 },
                children: [
                  new Paragraph({
                    spacing: { after: 650 },
                    children: [
                      new ImageRun({ data: logoData, type: "png", transformation: { width: 82, height: 82 } }),
                    ],
                  }),
                  new Paragraph({
                    spacing: { after: 140 },
                    children: [new TextRun({ text: manual.kicker, color: manual.accent, bold: true, size: 18, characterSpacing: 90 })],
                  }),
                  new Paragraph({
                    spacing: { after: 260, line: 520 },
                    children: [new TextRun({ text: title.replace(/^HEU ESTA\s*/, ""), color: colors.paper, bold: true, size: 52 })],
                  }),
                  new Paragraph({
                    spacing: { after: 520 },
                    border: { bottom: border(manual.accent, 18) },
                    children: [new TextRun({ text: "哈尔滨工程大学电子科技协会", color: "C7D4DB", size: 23 })],
                  }),
                  new Paragraph({
                    spacing: { after: 120 },
                    children: [new TextRun({ text: `适用对象  /  ${metadata.audience || "网站用户"}`, color: "D8E4E9", size: 20 })],
                  }),
                  new Paragraph({
                    spacing: { after: 120 },
                    children: [new TextRun({ text: `文档属性  /  ${visibility}`, color: manual.internal ? "F2C68F" : "D8E4E9", bold: manual.internal, size: 20 })],
                  }),
                  new Paragraph({
                    spacing: { after: 120 },
                    children: [new TextRun({ text: `手册版本  /  ${metadata.manual_version || "1.0"}`, color: "D8E4E9", size: 20 })],
                  }),
                  new Paragraph({
                    spacing: { after: 120 },
                    children: [new TextRun({ text: `截图日期  /  ${metadata.screenshot_date || "2026-09-04"}`, color: "D8E4E9", size: 20 })],
                  }),
                  new Paragraph({
                    spacing: { before: 600, after: 0 },
                    children: [new TextRun({ text: "https://heuesta.cn", color: manual.accent, size: 20, bold: true })],
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        spacing: { before: 260, after: 0 },
        children: [new TextRun({ text: "探索  ·  协作  ·  创造", color: colors.muted, size: 18, characterSpacing: 40 })],
      }),
    ],
  };
}

function contentGuide(headings, manual) {
  const rows = headings.map((heading, index) =>
    new TableRow({
      cantSplit: true,
      children: [
        new TableCell({
          width: { size: 820, type: WidthType.DXA },
          margins: { top: 110, right: 100, bottom: 110, left: 120 },
          shading: { type: ShadingType.CLEAR, fill: index % 2 === 0 ? "F3F8FA" : "FFFFFF" },
          children: [
            new Paragraph({
              spacing: { after: 0 },
              children: [new TextRun({ text: String(index + 1).padStart(2, "0"), bold: true, color: manual.accent, size: 18 })],
            }),
          ],
        }),
        new TableCell({
          margins: { top: 110, right: 150, bottom: 110, left: 170 },
          shading: { type: ShadingType.CLEAR, fill: index % 2 === 0 ? "F3F8FA" : "FFFFFF" },
          children: [
            new Paragraph({
              spacing: { after: 0 },
              children: [new TextRun({ text: heading.replace(/^\d+\.\s*/, ""), color: colors.ink, size: 19 })],
            }),
          ],
        }),
      ],
    }),
  );

  return [
    new Paragraph({
      heading: HeadingLevel.TITLE,
      spacing: { before: 120, after: 120 },
      children: [new TextRun({ text: "内容导览", color: colors.navy, bold: true, size: 35 })],
    }),
    new Paragraph({
      spacing: { after: 300 },
      children: [new TextRun({ text: "按章节定位操作；截图编号与章节号一致，便于页面更新后快速替换。", color: colors.muted, size: 19 })],
    }),
    new Table({
      width: { size: 100, type: WidthType.PERCENTAGE },
      borders: {
        top: border(colors.line, 5),
        right: border(colors.line, 5),
        bottom: border(colors.line, 5),
        left: border(colors.line, 5),
        insideHorizontal: border(colors.line, 4),
        insideVertical: { style: BorderStyle.NIL },
      },
      rows,
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

async function bodyElements(body, manual) {
  const lines = body.replace(/^\s*# .*?\r?\n+/, "").split(/\r?\n/);
  const elements = [];
  let paragraphBuffer = [];
  let listBuffer = [];
  let listOrdered = false;

  const flushParagraph = () => {
    if (!paragraphBuffer.length) return;
    const text = paragraphBuffer.join(" ").replace(/\s{2,}/g, " ").trim();
    paragraphBuffer = [];
    if (!text) return;
    elements.push(
      new Paragraph({
        spacing: { after: 160, line: 330 },
        widowControl: true,
        children: inlineChildren(text, { size: 20, color: colors.ink }),
      }),
    );
  };

  const flushList = () => {
    if (!listBuffer.length) return;
    listBuffer.forEach((item, index) => {
      elements.push(
        new Paragraph({
          indent: { left: 420, hanging: 250 },
          spacing: { after: 75, line: 310 },
          widowControl: true,
          children: [
            new TextRun({ text: listOrdered ? `${index + 1}. ` : "• ", bold: true, color: manual.accent, size: 20 }),
            ...inlineChildren(item, { size: 20, color: colors.ink }),
          ],
        }),
      );
    });
    listBuffer = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index];
    const line = raw.trim();

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const imageMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      flushParagraph();
      flushList();
      const imagePath = path.resolve(manual.sourceDir, imageMatch[2]);
      elements.push(await imageParagraph(imagePath, imageMatch[1]));
      continue;
    }

    if (/^\*图.+\*$/.test(line)) {
      flushParagraph();
      flushList();
      elements.push(captionParagraph(line));
      continue;
    }

    const headingMatch = line.match(/^(#{2,3})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      const headingText = stripMarkdown(headingMatch[2]);

      elements.push(
        new Paragraph({
          heading: level === 2 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
          spacing: level === 2 ? { before: 180, after: 210 } : { before: 180, after: 100 },
          keepNext: true,
          border: level === 2 ? { bottom: border(manual.accent, 9) } : undefined,
          children: [
            new TextRun({
              text: headingText,
              color: level === 2 ? colors.navy : manual.accent,
              bold: true,
              size: level === 2 ? 31 : 23,
            }),
          ],
        }),
      );
      continue;
    }

    if (line.startsWith(">")) {
      flushParagraph();
      flushList();
      const quoteLines = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, "").replace(/\s{2}$/, ""));
        index += 1;
      }
      index -= 1;
      elements.push(infoBand(quoteLines.join("  ·  "), manual.accent, manual.internal ? "warning" : "info"));
      elements.push(new Paragraph({ spacing: { after: 110 }, children: [new TextRun("")] }));
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
    const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
    if (orderedMatch || unorderedMatch) {
      flushParagraph();
      const ordered = Boolean(orderedMatch);
      if (listBuffer.length && listOrdered !== ordered) flushList();
      listOrdered = ordered;
      listBuffer.push((orderedMatch || unorderedMatch)[1]);
      continue;
    }

    if (/^---+$/.test(line)) {
      flushParagraph();
      flushList();
      elements.push(new Paragraph({ border: { bottom: border(colors.line, 5) }, spacing: { before: 120, after: 220 }, children: [new TextRun("")] }));
      continue;
    }

    paragraphBuffer.push(line.replace(/\s{2}$/, ""));
  }

  flushParagraph();
  flushList();
  return elements;
}

async function buildManual(manual, logoData) {
  const sourcePath = path.join(manualsDir, manual.source);
  const source = await fs.readFile(sourcePath, "utf8");
  const { metadata, body } = parseFrontmatter(source);
  const headings = [...body.matchAll(/^##\s+(.+)$/gm)].map((match) => stripMarkdown(match[1]));
  const numberedHeadings = headings.filter((heading) => /^\d+\./.test(heading));
  const bodyManual = { ...manual, sourceDir: manualsDir };

  const introElements = [];
  if (manual.internal) {
    introElements.push(infoBand("本手册仅供授权站务人员内部使用。截图已脱敏；请勿将后台界面、会员资料或安全配置转发到公开渠道。", manual.accent, "warning"));
    introElements.push(new Paragraph({ spacing: { after: 180 }, children: [new TextRun("")] }));
  }

  const doc = new Document({
    creator: "哈尔滨工程大学电子科技协会",
    title: metadata.title || manual.shortTitle,
    subject: `${manual.shortTitle}，适用于站点版本 ${metadata.site_version}`,
    description: `截图日期 ${metadata.screenshot_date}，手册版本 ${metadata.manual_version}`,
    keywords: "HEU ESTA, 电子科技协会, 使用手册",
    language: "zh-CN",
    styles: {
      default: {
        document: {
          run: { font: "Microsoft YaHei", size: 20, color: colors.ink },
          paragraph: { spacing: { line: 330, after: 120 } },
        },
      },
      paragraphStyles: [
        {
          id: "Title",
          name: "Title",
          basedOn: "Normal",
          next: "Normal",
          run: { font: "Microsoft YaHei", size: 36, bold: true, color: colors.navy },
          paragraph: { spacing: { before: 240, after: 180 } },
        },
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 31, bold: true, color: colors.navy },
          paragraph: { spacing: { before: 220, after: 170 }, keepNext: true },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 23, bold: true, color: manual.accent },
          paragraph: { spacing: { before: 180, after: 100 }, keepNext: true },
        },
      ],
      characterStyles: [
        {
          id: "Hyperlink",
          name: "Hyperlink",
          basedOn: "DefaultParagraphFont",
          run: { color: colors.blue, underline: {} },
        },
      ],
    },
    sections: [
      coverSection(manual, metadata, logoData),
      {
        properties: { page: { size: A4, margin: margins } },
        headers: { default: makeHeader(manual, logoData) },
        footers: { default: makeFooter(metadata) },
        children: [
          ...contentGuide(numberedHeadings, manual),
          ...introElements,
          ...(await bodyElements(body, bodyManual)),
        ],
      },
    ],
  });

  const target = path.join(outputDir, manual.output);
  await fs.writeFile(target, await Packer.toBuffer(doc));
  return { target, chapters: numberedHeadings.length };
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const logoData = await fs.readFile(logoPath);
  const results = [];
  for (const manual of manuals) {
    results.push(await buildManual(manual, logoData));
  }
  for (const result of results) {
    const stat = await fs.stat(result.target);
    console.log(`${path.relative(repoRoot, result.target)} | ${result.chapters} chapters | ${(stat.size / 1024 / 1024).toFixed(1)} MB`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
