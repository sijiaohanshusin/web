# 官网候选发布与回退

本轮不迁移数据、不修复或调整备份服务，也不新增付费平台。发布仅在没有待执行数据库迁移时进行；有迁移会在候选阶段停止。

1. 完成 GitHub 三组质量检查，确认待发布的完整提交号。
2. 在服务器运行 `bash ops/release.sh <40位SHA>`。首次使用须先把此脚本放到服务器的独立临时路径执行。
   只验证候选可先加 `HEUESTA_CANDIDATE_ONLY=1`；候选验证结束后自动移除临时容器，不切换生产。
3. 脚本按提交号下载、构建带 revision 标签的镜像。候选容器使用独立静态目录和只读媒体挂载，跳过会迁移数据库的入口脚本；检查数据库状态、关键页面和动态站点地图。
4. 检查通过后切换版本，更新 app 和荣誉处理 worker，保留旧镜像、源码及哈希静态资源。对照运行容器标签与提交号，检查内部就绪接口和公网隔离，再写入 DEPLOYED_SHA。
5. 执行 `bash /opt/heuesta/web/ops/verify.sh`，检查官网与论坛、压缩、缓存、字体及实际版本。启动一次 B 站刷新并确认成功快照，后续每30分钟运行。
6. 发布失败自动恢复代码、镜像和 nginx；人工回退使用新版本脚本的绝对路径：`bash <release目录>/ops/rollback-release.sh <release元数据目录>`。该路径在发布输出中显示。没有删除或还原业务数据的操作。

第一次发布将原 `/opt/heuesta/web` 实体目录保留到 releases 下，再让 web 指向候选目录；原有定时任务仍可使用同一路径。发布脚本不会删除旧版本，也不会清理 Docker 镜像。

路径和资源可通过 HEUESTA_ROOT、HEUESTA_ENV_FILE、HEUESTA_DATA_ROOT、HEUESTA_PORT、HEUESTA_NETWORK、POSTGRES_HOST、APP_MEMORY、DB_MEMORY、HONOR_WORKER_MEMORY、GUNICORN_WORKERS/THREADS/TIMEOUT 配置。域名更换还须核对 TLS 证书、nginx server_name、Django ALLOWED_HOSTS 和论坛 SSO；仅更换本地源站可继续沿用现有域名。

本轮内容操作单独执行：`restrict_launch_test_files` 默认预览，仅精确匹配已审计的两份测试资料，`--apply --snapshot <新文件>` 改为站务可见，保留文件；`ops/forum/launch-content.js` 同样默认预览，更新前保存官方旧帖内容。作品和纪事在 `docs/content/2026-launch-review.md` 中待事实审核，不自动发布。
