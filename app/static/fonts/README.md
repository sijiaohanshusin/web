# 自托管字体

由 `scripts/build_fonts.py` 子集化生成，更新字库时重新运行该脚本。

| 文件 | 来源 | 许可证 | 用途 |
|---|---|---|---|
| `JetBrainsMono-subset.woff2` | [JetBrains Mono v2.304](https://github.com/JetBrains/JetBrainsMono)（可变字重 100-800，拉丁子集） | SIL OFL 1.1 | 全站 mono 数字/编号/标签（`--font-mono`） |
| `SourceHanSansCN-Heavy-subset.woff2` | [思源黑体 Source Han Sans CN Heavy](https://github.com/adobe-fonts/source-han-sans)（按站内标题用字子集） | SIL OFL 1.1 | 大标题真 Heavy 字重（`--font-display`） |

注意：思源子集只覆盖模板中出现的汉字 + 常用字兜底。若新增标题包含生僻字，
该字会回退到系统黑体；批量改版后建议重新运行子集脚本。
