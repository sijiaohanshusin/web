# 自托管字体

由 `scripts/build_fonts.py` 子集化生成，更新字库时重新运行该脚本。

| 文件 | 来源 | 许可证 | 用途 |
|---|---|---|---|
| `JetBrainsMono-subset.woff2` | [JetBrains Mono v2.304](https://github.com/JetBrains/JetBrainsMono)（可变字重 100-800，拉丁子集） | SIL OFL 1.1 | 全站 mono 数字/编号/标签（`--font-mono`） |
| `SourceHanSansCN-Heavy-subset.woff2` | [思源黑体 Source Han Sans CN Heavy](https://github.com/adobe-fonts/source-han-sans)（按站内标题用字子集） | SIL OFL 1.1 | 大标题真 Heavy 字重（`--font-display`） |

当前体积：mono 116 KB · 思源 333 KB（977 个汉字）。两个都在 `base.html` 里
`rel=preload` —— 不 preload 的话浏览器要等 CSS 解析完才发现它们，首屏那条大标题
会先用系统黑体画一遍再跳成真 Heavy。

## 缺字是静默故障，靠脚本兜

思源子集只覆盖**模板里出现过的**汉字 + 常用字兜底。新加的文案带进新字时，那些字
会按 `font-display: swap` 回退到系统黑体 —— 一行标题里混着两种字重两种字形，
而页面不报错、控制台干净、`collectstatic` 也照常过。

所以改完文案要跑：

```
python scripts/check_fonts.py          # 只检查，会告诉你缺几个字
python scripts/check_fonts.py --list   # 把缺的字打出来
```

它把字库的 cmap 和 `build_fonts.py` 扫出来的用字集合逐字对一遍。**「要哪些字」直接
从 build_fonts.py import，不在两处各写一份。** 真实教训：Task 10~19 加了作品墙 /
荣誉墙 / 团队页 / 注册三页的文案之后，**1097 个字里缺了 274 个（25%）**，一直没人发现。

缺字的修法是重跑子集脚本（要两个字体源文件，下载地址在 `scripts/build_fonts.py`
的文件头；需要 `pip install fonttools brotli`，**开发工具，不要写进
`app/requirements.txt`**）：

```
python scripts/build_fonts.py <JetBrainsMono[wght].ttf> <SourceHanSansCN-Heavy.otf>
```

`collect_cjk_chars()` 会先整块摘掉 `{% comment %}` 与 `<!-- -->` —— 本项目的模板
注释又长又全是中文，而注释一个字都不会渲染。不摘的话它们全进子集（实测多出
125 个字、33 KB），而且会让上面那条检查变成在要求「注释里的字也得在字库里」。
