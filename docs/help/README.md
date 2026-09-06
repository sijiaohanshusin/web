# 帮助中心与离线首次上手手册

网页帮助用于按任务搜索；离线手册用于首次操作和快速查找，不要求先通读整本。三册正文与网页共用结构化 Markdown。

## 当前交付

2026-09-06 已重建三册“成果体系首次上手版”，每册提供 DOCX、PDF、Markdown。产物位于 `docs/help/dist/2026-09-06/`；此目录不入库，生成不等于上传官网。管理册仅供内部使用，不应作为公开下载文件。

| 读者 | 网页入口 | 当前文件前缀 | 页数 / 任务数 |
| --- | --- | --- | --- |
| 招新成员 | `/help/recruit/` | `recruit-first-use-achievements` | 16 / 13 |
| 老会员 | `/help/member/` | `member-first-use-achievements` | 27 / 24 |
| 站务人员 | `/help/admin/` | `admin-first-use-achievements` | 17 / 14 |

三册都有可点击目录、第 3 页任务速查、编号步骤、关键操作截图、完成检查，以及页脚的“返回目录 / 任务速查 / 遇到 BUG”。共 60 页、54 处截图，截图编号和来源日期可追溯。

- 招新册补充注册前参与成果的邀请确认、认领与进度查询；仅关联署名，不因此获得会员资源或编辑权限。
- 老会员册覆盖个人展示作品、独立作品墙上传、共同参与者、未注册署名、关联作品的荣誉、本人预览发布与撤回、历史认领。
- 管理册补充事实核验、同名处理、禁止自审，以及作品和荣誉的排序与首页精选；站务不能代替成员公开或改写成员内容。
- 三册保留提交问题、跟进对话、匿名反馈限制、截图脱敏，以及官网不可用时通过 QQ 群 `1081376858` 联系站务的方法。当前反馈表单没有图片上传，不虚构按钮。

**发布边界：**本轮核对的正式站为 `8e7c4de`。成果体系新流程与截图在隔离环境验证，三册封面标记“待上线”，不能把推送代码当作已经部署。功能上线并核对正式链接后再对外换发；发布状态由 `first_use.json` 统一维护。

## 正确区分几个操作

个人展示中的作品模块不等于协会作品墙；保存草稿不等于公开。公开由作者本人预览并同意。站务排序不替代发布。作品与荣誉通过引用关联，一项奖不会因多人参与而增加统计数量。

未注册者可以先留署名；已注册账号由本人确认邀请，其他认领由站务核验。不能因为姓名相同就自动绑定。已有确认署名或认领记录的成果不允许作者直接删除关联历史。

## 旧版本边界

`docs/manuals/`、不带 `-first-use` 的全文导出，以及 `-selfservice-preview`、`-works-wall-preview` 均归档，不再作为成果体系最新说明发放。不带后缀的旧首次手册仅用于对照旧正式版本。保留旧文件不等于它仍然适用。

网站版本、源稿构建版本和截图日期分别记录，不拿文档提交号冒充网站版本，也不把重新导出日期当作截图日期。服务器运维仍引用内部维护手册，不写入公开用户手册。

## 内容源与隐私

- `app/helpcenter/content/<audience>/*.md` 是正文唯一来源，带权限、路由、图源和日期元数据。
- `scripts/manuals/first_use.json` 维护编排、索引、步骤引用和图源，`output_suffix=achievements` 控制当前产物命名。
- `app/helpcenter/assets/` 仅保存脱敏图。新增成果截图来自随机命名的隔离测试账号，不产生正式站演示数据。
- 管理网页及图片由服务端权限过滤；公开仓库的源稿不保密，所有截图和文字仍须脱敏，不能放入真实会员资料或凭据。
- 生成的内部 DOCX/PDF 不强制入库、不复制到公开静态目录；网站正文与截图随应用正常发布。

## 生成与检查

1. 修改正文与编排，运行 `manage.py test helpcenter`，验证任务、步骤、截图和权限契约。
2. 需要新图时，在隔离环境执行 `scripts/check_achievements.py`，再运行 `scripts/manuals/prepare_achievement_images.py`。只对原始像素裁切、分栏和添加外部标注，不生成 UI。
3. 使用文档运行时执行 `scripts/manuals/build_first_use.py`，生成三册 DOCX、Markdown 与 `first-use-evidence.json`。只重建某册可加 `--audience member`，仍需验证其他两册没有过时。
4. 运行 `scripts/manuals/render_help_word.py <render_docx.py 路径> recruit-first-use-achievements member-first-use-achievements admin-first-use-achievements --revision 2026-09-06`。当前 Windows 转换后端为 Word，渲染器生成逐页 PNG；只操作本轮文档。
5. 运行 `scripts/manuals/check_first_use.py`，检查页数、任务不跨页、目录及速查的 PDF 实际目标页、页脚反馈入口、外链、图片替代文字和发布边界。合格 PDF 才复制到交付目录。
6. 逐页查看 `.shots/documents/<册名>/page-*.png`，检查截图可读性、图注、页码、孤立标题与分页。可用 `make_contact_sheets.py` 按数字页码生成双页对照图。结构测试不能代替视觉检查。
7. 再次改图或正文时重新渲染，并检查全部变化页；保留产物哈希与本轮验收记录，不能复用旧轮次结论。

`prepare_revision_images.py`、`prepare_work_images.py` 保留早期截图加工流程。`serve_revision.py` 只允许显式本地审核设置与隔离数据库；正常结束清理演示数据，中断后按本轮临时名称核对，不能批量删除其他记录。禁止对生产环境运行写入截图脚本。

本轮记录见 `docs/audit/2026-09-06-achievement-manuals.md`；早期记录见同目录的 `offline-manuals`、`works-wall-manual` 和 `achievement-system` 文档。
