# 第三方前端库（自托管）

本目录的文件是**直接提交进仓库的压缩产物**，不经任何构建步骤。原因有三：

1. 本项目明确无构建链，`tokens.css` / `core.css` / `home.css` 改完即生效，前端也应保持同样的心智负担。
2. 生产服务器是 2 核 1.6G，`ops/deploy.sh` 在服务器上跑 `docker compose build`。加一个 Node 构建阶段会显著拉长部署时间并占内存。
3. 国内访问 jsdelivr / unpkg 不稳定，服务器本身连 GitHub 的 git 协议都不通，运行时依赖公共 CDN 等于给首页加一个随机故障源。

缓存与版本：`prod.py` 用 `ManifestStaticFilesStorage`，这些文件在 `collectstatic` 时会被改成内容哈希文件名（如 `gsap.a1b2c3d4e5f6.min.js`），配合 nginx 的 `expires 365d; Cache-Control: public, immutable`。升级版本时哈希自然变化，不会有陈旧缓存问题，所以文件名里不需要带版本号。

## 清单

| 文件 | 包 | 版本 | 许可 |
| --- | --- | --- | --- |
| `gsap.min.js` | gsap | 3.15.0 | GSAP Standard License（2025-04-30 起全套免费商用） |
| `ScrollTrigger.min.js` | gsap | 3.15.0 | 同上 |
| `SplitText.min.js` | gsap | 3.15.0 | 同上（原会员专属插件，现已免费） |
| `lenis.min.js` | lenis | 1.3.26 | MIT |
| `lenis.css` | lenis | 1.3.26 | MIT |
| `three.module.min.js` | three | 0.185.1 | MIT |
| `three.core.min.js` | three | 0.185.1 | MIT（被 `three.module.min.js` 内部 import） |
| `SVGLoader.js` | three | 0.185.1 | MIT（`examples/jsm/loaders/`，未压缩，官方只发源码） |
| `BufferGeometryUtils.js` | three | 0.185.1 | MIT（`examples/jsm/utils/`，3D 会标合并走线几何用） |
| `chart.umd.min.js` | chart.js | 见文件头注释 | MIT（驾驶舱图表，早于本次改造） |

## 加载方式

- **GSAP 三件套与 Lenis 是 UMD**，用普通 `<script defer>` 引入，暴露全局 `gsap` / `ScrollTrigger` / `SplitText` / `Lenis`。装配逻辑在 `js/motion-core.js`。
- **three 是 ES module**，通过 `base.html` 里的 importmap 用裸标识符引入：

  ```js
  import * as THREE from "three";
  import { SVGLoader } from "three/addons/loaders/SVGLoader.js";
  ```

  importmap 的值由 `{% static %}` 生成，因此生产环境指向哈希文件名。three 体积大（未压缩 733KB / gzip 约 170KB），只在需要 3D 的页面用动态 `import()` 按需加载，不进首屏。

## 升级步骤

不要手工下载覆盖。版本钉死在 `scripts/vendor_sync.py` 的 `PACKAGES` 里，改完版本号跑：

```powershell
python scripts/vendor_sync.py           # 同步
python scripts/vendor_sync.py --check   # 只比对，确认仓库与声明一致
cd app; python manage.py check_static_pipeline
```

脚本做三件事：用 `npm pack` 下载钉死版本的 tarball（不装依赖、不产生 node_modules）、只取需要的文件、**剥掉 `sourceMappingURL` 注释**。

最后一步不能省。`ManifestStaticFilesStorage` 会解析 JS 里的 `sourceMappingURL` 并要求那个 `.map` 文件也在静态目录里，否则 `collectstatic` 抛 `ValueError` 直接中断部署。`lenis.min.js` 就带这行注释，踩过一次。压缩库的 map 文件对线上排障没价值，还要多传 1MB 以上，统一剥除。

同步完更新上面的版本表，然后跑 `check_static_pipeline` 确认静态管线没断链，最后在浏览器里确认首页与 3D 会标正常。

## 两个必须知道的机制

**`three.core.min.js` 为什么要一起收。** `three.module.min.js` 内部有 `import{...}from"./three.core.min.js"` 和对应的 `export ... from`，两个文件必须同版本共存。

**Django 默认不会改写这条相对 import。** `ManifestStaticFilesStorage` 的 `support_js_module_import_aggregation` 默认是 `False`，只处理 CSS 的 `url()` 和 `sourceMappingURL`。若不打开，浏览器会去请求未加哈希的 `/static/vendor/three.core.min.js` —— 而磁盘上只有带哈希的那份，生产 404、3D 直接挂，且本地 `DEBUG=True` 时完全看不出来。我们在 `app/config/storage.py` 里子类化打开了这个开关，`manage.py check_static_pipeline` 会验证它确实生效。
