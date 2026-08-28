"""生产静态文件存储。

Django 的 ManifestStaticFilesStorage 默认**不**改写 JS 里的 ES module import
路径（`support_js_module_import_aggregation = False`，见
django/contrib/staticfiles/storage.py）。它默认只处理 CSS 的 url()/@import
和两种 sourceMappingURL 注释。

这对我们是个硬问题：`vendor/three.module.min.js` 内部有

    import{...}from"./three.core.min.js";
    export{...}from"./three.core.min.js";

如果不改写，浏览器会去请求未加哈希的 `/static/vendor/three.core.min.js`，
而 collectstatic 只产出了带哈希的那份 —— 生产环境 404，3D 会标直接挂掉，
且本地 DEBUG=True 时不会暴露（DEBUG 下不走哈希存储）。

打开这个开关后，Django 会改写四种形式：
    import ... from "./x.js"      export ... from "./x.js"
    import "./x.js"               import("./x.js")     ← 动态导入也覆盖

最后一条让按需加载 3D 模块（`import("../js/logo-3d.js")`）同样拿到哈希 URL。

注意开关打开后的副作用：任何相对 import 指向不存在的文件都会让
collectstatic 直接抛 ValueError 中断部署。这是好事（早于上线暴露断链），
但意味着新增 ES module 时要在本地跑一次 collectstatic。

静态形式的裸标识符（`import ... from "three"`）不受影响：Django 那三条正则把
URL 限定成 `(?P<url>[./].*?)`，必须以 . 或 / 开头才匹配。

但**动态** import 那一条没有这个限定，写的是 `(?P<url>.*?)` —— 于是
`import("esta/logo-3d")` 会被当成相对路径，Django 去找
`js/scenes/esta/logo-3d`，找不到就抛 ValueError 中断 collectstatic。
裸标识符本该由 importmap 解析，所以下面把这一条的行为补齐。
"""

import re

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage

# ES module 规范里的「裸标识符」：既不是相对路径也不带协议，必须由 importmap 解析
_BARE_SPECIFIER = re.compile(r"^(?![a-z][a-z0-9+.\-]*:)(?!//)(?![./])", re.IGNORECASE)


class ESTAManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """带 ES module 相对路径改写的清单式静态存储。"""

    support_js_module_import_aggregation = True

    # Django 用它渲染改写后的动态 import。拿它当判据来认出「当前正在处理哪条
    # 正则」，比复制一份 Django 的正则元组更耐升级：万一 Django 改了这个模板，
    # 我们的覆盖会退化成不生效，于是 check_static_pipeline 重新报错 —— 是响亮
    # 的失败而不是静默放过。core.tests.StaticStorageTests 盯着这个耦合。
    DYNAMIC_IMPORT_TEMPLATE = 'import("%(url)s")'

    def url_converter(self, name, hashed_files, template=None):
        converter = super().url_converter(name, hashed_files, template)
        if template != self.DYNAMIC_IMPORT_TEMPLATE:
            return converter

        def convert_dynamic_import(match):
            # 只放过裸标识符。以 . 或 / 开头的相对/绝对路径照旧交给 Django 解析，
            # 断链仍然要在部署前炸出来 —— 那正是打开这个开关的意义。
            if _BARE_SPECIFIER.match(match.groupdict().get("url") or "x"):
                return match["matched"]
            return converter(match)

        return convert_dynamic_import
