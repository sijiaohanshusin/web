# AI 美术资产生成记录

生成日期：2026-08-29  
生成方式：Codex 内置 `image_gen`  
需求来源：`docs/美术资产清单.md`

## 使用边界

本批文件仅属于“材质与氛围”类美术资产，不代表协会成员、实验室、设备或真实活动现场，也不作为电路、原理图、波形或器件结构的教学依据。协会现场照仍必须由成员实拍，技术图仍应使用可校验的 SVG、KiCad 或绘图程序制作。

## 文件清单

| 编号 | 文件 | 尺寸 | 主要提示词 |
| --- | --- | --- | --- |
| T1 | `app/static/img/tex-fr4-weave.png` | 2048x2048 | 极暗 FR4 玻纤布纹、哑光深绿阻焊、微弱青色侧光、正交无缝平铺 |
| T2 | `app/static/img/tex-etched-copper.png` | 2048x2048 | 极暗裸铜蚀刻纹、轻微氧化、低饱和铜色、正交无缝平铺 |
| T3 | `app/static/img/tex-solder-joint.png` | 2048x2048 | 单个哑光锡灰焊点、暖铜反光、近黑阻焊面、浅景深 |
| T4 | `app/static/img/tex-matte-solder-mask.png` | 2048x2048 | 近纯黑哑光阻焊、细微橘皮纹、极弱斜向光、无缝平铺 |
| B1 | `app/static/img/banner-intro.png` | 2560x1080 | 右侧微小青色光点与极弱同心波纹，左侧留黑 |
| B2 | `app/static/img/banner-training.png` | 2560x1080 | 右侧由密到疏的青色时基刻度，左侧留黑 |
| B3 | `app/static/img/banner-hardware.png` | 2560x1080 | 右侧半透明板层悬浮叠放，铜色与青色薄边光 |
| B4 | `app/static/img/banner-software.png` | 2560x1080 | 右侧单个青色方波脉冲，无坐标轴与界面 |
| B5 | `app/static/img/banner-contest.png` | 2560x1080 | 青色光轨向远处收束，少量暗铜微粒 |
| O1 | `app/static/img/banner-social-card.png` | 1200x630 | 右下青色上扬光轨与铜色散景，左上留黑 |
| I1 | `app/static/img/illustration-soldering-journey.png` | 2048x1536 | 暗色手绘笔触、轮廓手持单尖烙铁、抽象板面与青色小灯 |

## 统一约束

所有生成提示词均限制为近黑、信号青和少量焊锡铜，禁止文字、标志、水印、紫红或洋红色、赛博朋克城市、可辨识电路和人物身份。横幅要求左侧 40% 保持干净，插画仅保留无身份特征的手部轮廓。

原始生成图经过无拉伸比例裁切和高质量重采样后保存为 PNG。T1、T2、T4 额外经过周期边缘混合，并使用 2x2 拼接预览检查接缝；所有横幅均检查左侧平均亮度低于右侧内容区。可选插画首版出现双叉尖端，已通过局部编辑修正为单尖烙铁。
