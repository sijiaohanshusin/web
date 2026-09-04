# HEU ESTA 网站使用手册

本目录保存三套独立手册及其可复用截图。手册内容以 2026 年 9 月 4 日正式站、网站版本 `9c9b9e8` 为准。

## 交付清单

| 手册 | 公开范围 | Markdown | DOCX | PDF |
|---|---|---|---|---|
| 招新注册手册 | 可公开 | `招新注册手册.md` | `dist/HEU_ESTA_招新注册手册_2026.docx` | `dist/HEU_ESTA_招新注册手册_2026.pdf` |
| 老会员使用手册 | 可公开 | `老会员使用手册.md` | `dist/HEU_ESTA_老会员使用手册_2026.docx` | `dist/HEU_ESTA_老会员使用手册_2026.pdf` |
| 网站管理手册 | 内部使用 | `网站管理手册.md` | `dist/HEU_ESTA_网站管理手册_2026.docx` | `dist/HEU_ESTA_网站管理手册_2026.pdf` |

## 目录说明

- `assets/screenshots/`：正式站原始截图，按 `admin`、`recruitment`、`returning-member` 和 `shared` 分类。
- `dist/`：最终 DOCX 与 PDF。
- `rendered/`：DOCX 逐页渲染验收图，不作为正式发布文件。
- `验收与问题记录.md`：端到端测试、隐私检查、已知问题和演示数据清理状态。

## 更新规则

1. 页面或流程变更后，优先更新对应编号截图，再更新 Markdown 正文。
2. 修改 Markdown 后运行 `scripts/manuals/build_manuals.mjs` 生成 DOCX。
3. Windows 环境运行 `scripts/manuals/export_manuals.ps1`，使用 Microsoft Word 将同一份 DOCX 导出为 PDF。
4. 运行 `scripts/manuals/render_manual_pdfs.py` 生成逐页验收图，再用 `scripts/manuals/make_contact_sheets.py` 检查分页、图片和文字。
5. 运行 `scripts/manuals/validate_manuals.py` 检查截图引用、PDF 页数、可提取正文和敏感信息模式。
6. PDF 必须由通过视觉检查的同一份 DOCX 转换，不能单独维护另一套正文。
7. 发布前搜索并确认文档不含密码、验证码、Cookie、密钥、服务器信息或真实会员隐私。

## 构建说明

- Node.js 需要能够加载 `docx` 与 `sharp`；本项目可使用 Codex 工作区依赖提供的 `NODE_PATH`。
- PDF 导出脚本依赖本机 Microsoft Word。若改用 LibreOffice，仍须重新逐页验收，不能假定两种排版引擎完全一致。
- `rendered/` 是本地验收输出，不进入正式交付；最终发布文件只取 `dist/`、三份 Markdown 及 `assets/screenshots/`。

管理手册引用服务器运维内容时，只链接现有维护文档，不在本目录复制凭据或部署配置。
