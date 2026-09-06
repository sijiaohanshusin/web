# 成果体系三册手册更新与推送验收

日期：2026-09-06。按当前成员作品、荣誉、共同署名与认领实现更新文档；不是对旧 PDF 简单换日期。网站新功能在隔离环境验证，正式站只读核对，未创建演示数据、未部署应用。

## 查出的过时点

- 旧 `member-first-use-works-wall-preview` 只有作品上墙，缺少荣誉、参与者、邀请确认、同名认领和管理核验。
- 三册索引没有成果任务；招新读者不知道可以关联注册前参与的成果，也容易误解为获得编辑权限。
- 原删除说明未体现“已有确认署名或认领记录时不得直接删除关联历史”。正文和离线步骤已同步修正。
- 原手机认领整张长图缩小后不易辨认，改为同一表单的两个编号阅读面板；关联作品与证书截图裁到关键字段。
- README 中“本轮未重新导出”的说明过时，已明确最新版文件前缀、归档范围和发布边界。

## 当前输出

产物在 `docs/help/dist/2026-09-06/`，三种格式为 DOCX、PDF、Markdown。生成文件不自动入库或上传，内部管理手册不进入公开静态目录。

| 文件前缀 | 页数 | 操作任务 | 截图 | 内部链接 |
| --- | --- | --- | --- | --- |
| recruit-first-use-achievements | 16 | 13 | 13 | 30 |
| member-first-use-achievements | 27 | 24 | 26 | 50 |
| admin-first-use-achievements | 17 | 14 | 15 | 33 |

总计 60 页、51 个首次操作任务、54 处截图。每册有目录、任务速查、步骤、完成检查、页脚反馈导航；每个任务独占一页。正式站基线 `8e7c4de` 与本地候选功能分别说明，封面保留“待上线”。

## 验证过程

- 先新增 `HelpAccessTests.test_offline_guides_cover_shared_achievement_workflows`，原编排因缺章失败；更新后帮助中心 21 项测试通过。
- 本轮完整 Django 测试 728 项，722 通过，6 项 PostgreSQL 专属并发测试在本机跳过，交由远端 CI 验证。
- `scripts/check_achievements.py` 重新完成六组真实浏览器流程：参与者候选与发布、本人确认、荣誉与证书、手机认领、站务核验排序、撤回后资源失效。
- 截图均来自隔离测试账号；未使用真实会员资料，未将凭据、手机号、邮箱或存储路径加入文档。
- 重新生成三册 DOCX，以文档渲染器及 Word 转换后端逐页生成 PNG/PDF。默认 LibreOffice 不可用，没有跳过渲染。
- `scripts/manuals/check_first_use.py` 三册零错误：页数、任务完整性、目录及速查实际目标页、反馈链接、图源、外链与图片替代文字均通过。
- 完整看过 60 页真实渲染图。最后一次改图/正文后，用 PNG 哈希识别 8 张变化页并重新查看：招新 3、14；会员 20、22、23、25；管理 3、14。其余 52 页与已检查画面逐字节相同。
- 最终截图无重叠、孤立标题、异常跨页或控件被导航遮挡；手机表单分栏后可辨认。
- 证据：`.shots/first-use/structural-checks.json`、`.shots/achievement-manual-qa/`、`.shots/documents/`、`.shots/achievements/`。

## 最终产物 SHA-256

| 产物 | SHA-256 |
| --- | --- |
| recruit DOCX | `637f39655e7801bb3bb52fa92539708a95be0b78b70647fb9a1928518d23419b` |
| recruit PDF | `ecc9c1bb4cd47e0897f9d29dcaaf7085d93952acbfd9bcd3cccaa6f323a394fd` |
| member DOCX | `039266cda0291a2c592db1d0b4fcbfe2e45b3df92f1e981379b2eb2dc2bab9be` |
| member PDF | `c4d6bb61b857edae14e203cbaa6f8e71d2a5d040680d287c128b878f8097cc98` |
| admin DOCX | `24ac136a4377d753c70ed9bd25a7f18515974b89cb92af200f97caba919afda9` |
| admin PDF | `7f04c4e129c1e38c4154eb5a9a344c682a11043453f3144924f2ac4d7915f688` |

## 推送与部署边界

用户本轮要求更新手册并推送网站改动。推送代码与正式站部署是不同步骤；不能改动生产数据来取得测试证据。

成果体系上线必须先部署私有作品图片和荣誉证书的 Nginx 保护规则，再执行应用迁移。主分支接收前运行 GitHub Actions PostgreSQL、浏览器及论坛检查；运行结果按真实 CI 状态记录，不把 SQLite 跳过项算通过。

功能正式部署并验证后，更新三册 `release_status`、实际网站版本和相关入口，再换发正式文件。旧 PDF/DOCX 仅保留历史参考，不覆盖成员已下载副本，也不把内部管理手册作为公共附件上传。
