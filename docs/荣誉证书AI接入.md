# 荣誉证书多模态识别接入

## 当前边界

实现位于 `achievements`，复用既有荣誉、参与者、预览及受保护证书。默认关闭，仅完成模拟供应商与本地浏览器验证；不要将其宣传为已经验证真实识别准确率的服务。

候选模型是北京地域 `qwen3.7-flash`，不是仅输出文字的 OCR 通道。使用图片输入、关闭思考模式、JSON 输出及服务端字段白名单。原始证书文字、模型原始响应和 Key 不写日志。阿里提供的 JSON 不是可信指令，不会被执行、直接入库或公开。

## 上线前配置

1. 核对该模型在北京业务空间的免费额度余额、到期时间和通用 API Key 权限，并在阿里云控制台开启“免费额度用完即停”。本地限流和 `HONOR_AI_FREE_TIER_CONFIRMED` 只是额外门槛，不能替代阿里侧计费保护。
2. 通过服务器受保护环境文件设置 `DASHSCOPE_API_KEY`、`DASHSCOPE_WORKSPACE_ID`、`HONOR_AI_FREE_TIER_EXPIRES`。到期时间必须为含时区的 ISO 格式。实际 Key 不进入聊天、仓库、脚本或前端。聊天中使用过的临时 Key 测试后撤销。
3. 使用获授权且已脱敏的少量样本评估完整、模糊、多人、省赛与全国赛事同名等情况，核对实际 Token 消耗及字段准确率。不能根据模拟结果推算准确率，也不能保证几十张一定免费。
4. 验收后设置 `HONOR_AI_FREE_TIER_CONFIRMED=1`，最后才设置 `HONOR_AI_ENABLED=1`；默认用户每天20次，全站100次、每用户每分钟3次。第一次联调可先缩小为2次/5次。

## 进程与发布顺序

1. 备份主站数据及配置，完成完整 CI、迁移与静态检查。论坛不作变更。
2. 先部署应用并运行 `python manage.py migrate --noinput`。新增表为任务队列及单例调度门；不修改会员等级、认领、荣誉或公开记录。
3. 确认现有 Nginx 仍禁止直接访问 `/media/honors/member/`；图片只通过带归属与公开引用校验的证书接口读取。
4. 同一版本应用镜像启动独立识别进程：`docker compose -f ops/docker-compose.yml --env-file /opt/heuesta/.env --profile honor-ai up -d --build honor-ai-worker`。默认 compose 不启动这个可选 profile。
5. 新进程入口为 `python manage.py honor_ai_worker`，无 Redis/Celery。数据库门控制单并发；调用不占用网页进程。连接/读取分别超时5秒/45秒，异常只返回固定错误，不自动重试。超过120秒的运行记录标为超时；有效结果24小时后清理。
6. 只在用户有资格、拥有证书并确认向阿里发送时建立任务。重复点击同一素材复用未过期任务；删任务/图片不能重置当日次数或绕过正在执行的调度锁。

## 接口

所有接口均要求登录和荣誉维护资格，禁止缓存。写接口保留 CSRF。

| 方法 | 路由 | 用途 |
| --- | --- | --- |
| POST | `/achievements/honors/<uuid>/images/upload/` | 单张静态安全图片，携带版本；不选择公开证书 |
| POST | `/achievements/honors/<uuid>/recognize/` | 本人图片 ID 与本次外部发送同意，返回任务 |
| GET | `/achievements/recognition/<uuid>/` | 仅本人可查状态和受限结构化建议 |

识别仅建议标题、赛事、年份、层级、团队、说明及最多20位参与者的姓名/身份。无法确认的字段为空并提示核对；同名账号不绑定，关联作品仍通过原搜索选择。近似记录仅从公开荣誉中检索，不包含他人草稿。

## 故障与回退

- `AllocationQuota.FreeTierOnly`：记录当前配置停用标记，拒绝后续模型调用；不改用付费模型，不无限重试。
- 不知道额度状态或到期时间时，保持 AI 关闭。环境变量误填和401均不可用，原手工录入不受影响。
- 识别失败时保留输入；上传已成功时选择已上传证书重试即可。发布流程仍需人工检查和公开同意。
- 回退先将 `HONOR_AI_ENABLED=0` 并重建应用/worker使环境生效，再停止识别进程。保留新增表和已有草稿，不反向迁移、不恢复旧数据库、不重新公开已撤回的证书。
- 进程关闭时不会继续做24小时清理；重新启动会清理。若长期停用，应保留关闭状态的 worker 仅执行清理，或安排运行 `honor_ai_worker --once`。
- 网页帮助见“作品、荣誉与成果认领”。问题反馈经 `/feedback/`，站点不可用时 QQ 群1081376858，不提交密钥和未脱敏证书。

## 官方依据

- [千问 Flash 多模态能力](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)
- [结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
- [免费额度规则](https://help.aliyun.com/zh/model-studio/new-free-quota)
- [用量及免费额度停用开关](https://help.aliyun.com/zh/model-studio/model-usage-statistics)

网页帮助和老会员首次上手体验版以同一 Markdown 正文构建。运行 `scripts/manuals/build_first_use.py --audience member --variant honor-ai` 生成候选册，不覆盖已发布手册；模型真实验收通过后再变更发布状态。
