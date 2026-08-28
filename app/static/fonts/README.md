# 自托管字体

由 `scripts/build_fonts.py` 子集化生成，更新字库时重新运行该脚本。

| 文件 | 来源 | 许可证 | 用途 |
|---|---|---|---|
| `JetBrainsMono-subset.woff2` | [JetBrains Mono v2.304](https://github.com/JetBrains/JetBrainsMono)（可变字重 100-800，拉丁子集） | SIL OFL 1.1 | 全站 mono 数字/编号/标签（`--font-mono`） |
| `SourceHanSansCN-Heavy-subset.woff2` | [思源黑体 Source Han Sans CN Heavy](https://github.com/adobe-fonts/source-han-sans)（按站内标题用字子集） | SIL OFL 1.1 | 大标题真 Heavy 字重（`--font-display`） |
| `SourceHanSansCN-Regular-subset.woff2` | 同上，Regular（GB2312 一级字全集） | SIL OFL 1.1 | **正文**（`--font-body`） |
| `SourceHanSansCN-Bold-subset.woff2` | 同上，Bold（同一份字表） | SIL OFL 1.1 | 正文加粗，`<strong>` 与 600/700/800 |
| `SourceHanSerifCN-SemiBold-subset.woff2` | [思源宋体 Source Han Serif CN SemiBold](https://github.com/adobe-fonts/source-han-serif)（按模板用字子集） | SIL OFL 1.1 | **第二声音**：各页导语（`--font-serif`） |

当前体积：mono 116 KB · 标题 333 KB（977 字）· 正文 1030 + 1041 KB（3760 字）·
宋体 461 KB（977 字）。五个都在 `base.html` 里 `rel=preload` —— 不 preload 的话
浏览器要等 CSS 解析完才发现它们，整页先用系统黑体画一遍再换字。

## 第二声音（宋体）只能用在模板文案上

全站原来只有「几何无衬线 + 等宽」两种声音，温度是平的。宋体加的是**种类**上的
对比，比再加一档字号有效得多 —— 但它的字表和标题字体一样是**按模板取字**的
（按正文那份 GB2312 全集做出来是 1456 KB，宋体轮廓比黑体复杂，同样字数多花 40%）。

所以：**数据库里的文字不许用它。** `.wk-detail-lede`（作品简介，会员自己写的）
就是刻意留成黑体的，CSS 里写了原因。这条约束没法靠脚本证明，只能靠注释 ——
`check_fonts.py` 能保证的是「模板里的字都在宋体子集里」。

现在用在哪（全是「导语」这一个角色）：`.page-hero-sub`（每页页头）、
`.recruit-hero p`、`.rec-hero-sub`、`.auth-lede`、`.nf-join-sub`。
另外它只做 SemiBold 一档：宋体横画在纯黑底上本来就细，Regular 会发虚。

## 正文两档的两条硬要求

**一、字表不按模板取字，取 GB2312 一级字全集。** 标题字体的用字是固定的（内容
作者改不到标题），而正文要承载站务以后随时写的公告、活动、作品简介、成员姓名 ——
模板扫不到那些字。正文缺字比标题缺字难看得多：一段话里混进两种字形。
字表从 Python 自带的 `gb2312` 编码枚举出来，**确定、离线、可复现**，不依赖某个
网页上的「常用 3500 字表」哪天改了内容。

**二、Regular 和 Bold 必须成对，而且覆盖逐字一致。** 只自托管 Regular 的话，
`<strong>` 与 `font-weight: 700` 会让浏览器把 Regular 描粗（合成假粗）——
而系统黑体本来有真 Bold，等于自托管之后反倒变差。两档字表不一致会更隐蔽：
只有被加粗的那几个字掉回系统字体。`check_fonts.py` 两条都钉住了。

代价是首访多约 2MB。这是明确的用体积换效果（展示效果优先、一年 immutable 缓存 +
EdgeOne）。哪天嫌重，**下一步是按 `unicode-range` 切片，而不是砍字表** ——
砍字表换来的是「某些字突然变成另一种字体」，那是又一个静默故障。

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

## 重建不是逐字节可复现的

连续两次跑 `build_fonts.py` 构建同一个字体，产出的 woff2 字节就不一样（体积相同、
哈希不同）。所以「顺手重跑一遍」会把五个文件全标成 modified，入库后哈希全变一遍，
所有回访用户白下 2.5MB。

**只在真的要改字表时重建**，并且把这次没必要变的那几个 `git checkout HEAD --` 回去。
