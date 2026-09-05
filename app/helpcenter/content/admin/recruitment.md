---
{
  "title": "招新管理",
  "summary": "管理批次和答卷，记录面试并更新录取状态。",
  "access": "officer",
  "order": 6,
  "minutes": 2,
  "routes": [
    "/dashboard/recruitment/"
  ],
  "checkpoints": [
    "已核对当前批次及开放状态",
    "面试结果对应正确的申请人",
    "已复查申请状态、等级变化和通知"
  ],
  "screenshots": [
    "admin-07-application-detail.png",
    "admin-06-recruitment-submitted.png",
    "admin-06-recruitment-first-pass.png",
    "admin-06-recruitment-second-pass.png",
    "admin-06-recruitment-rejected.png"
  ],
  "verified": "2026-09-04",
  "version": "9c9b9e8"
}
---

## 按步骤操作

1. 进入“招新管理”，确认当前批次名称、开放时间、截止时间和启用状态。
2. 同一时间通常只启用一个对外批次；截止时间留空表示长期开放。
3. 使用状态、方向和关键词筛选报名者，导出 CSV 前确认筛选范围。
4. 打开报名详情，核对账号档案和完整答卷。
5. 在“面试备注”记录内部信息，不写不必要的敏感评价。
6. 点击“一面通过”会将成员晋升为预备会员；“二面通过”会晋升为科协会员。
7. “本次未录取”是终止状态；“重置为已报名”用于纠正误操作或重新进入流程。
8. 处理后以报名详情和用户招新页双向核对状态。

![招新报名详情](asset:admin-07-application-detail.png)

*图 6-1　详情页将账号档案、答卷和处理按钮分区呈现。*

![已报名列表](asset:admin-06-recruitment-submitted.png)

*图 6-2　演示记录处于已报名状态。*

![一面通过列表](asset:admin-06-recruitment-first-pass.png)

*图 6-3　一面通过同步晋升为预备会员。*

![二面通过列表](asset:admin-06-recruitment-second-pass.png)

*图 6-4　二面通过同步晋升为科协会员。*

![未录取列表](asset:admin-06-recruitment-rejected.png)

*图 6-5　未录取可使用“重置”恢复为已报名。*

## 你应该看到

报名状态、会员等级和用户侧进度一致，导出名单与当前筛选相符。

## 遇到问题

- **直接二面通过**：系统会晋升为科协会员，提交前确认面试流程已完成。
- **误点未录取**：保留操作时间和备注，使用“重置”后按正确结果重做。
- **CSV 包含多余人员**：导出前清空或固定筛选条件，并检查文件行数。
