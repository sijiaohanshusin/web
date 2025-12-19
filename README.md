# **哈尔滨工程大学电子科技协会 (HEU ESTA) 官网**

**立足实践，开拓创新。在科协，技术就是生命。**

这是一个为 **哈尔滨工程大学电子科技协会 (HEU ESTA)** 设计的全新官方网站。项目采用现代化的单页设计（Single Page Application 风格），旨在展示协会风采、发布培训路线以及整合学习资源。

## **✨ 项目亮点**

* **⚡️ 极速加载**：纯静态页面，无后端依赖，基于 CDN 加载资源。  
* **📱 响应式设计**：基于 Tailwind CSS，完美适配桌面端、平板和移动端。  
* **🎨 现代化 UI**：采用深色极客风与清爽白底交替，配合流畅的滚动动画。  
* **🛠 干货整合**：内置可视化的年度培训路线图（时间轴/Tab切换）及常用工具栈介绍。  
* **📺 多媒体集成**：内嵌 Bilibili 宣传视频播放器，支持高清播放。

## **🛠️ 技术栈**

本项目为了保持轻量和易于维护（方便低年级同学快速接手），采用了无构建工具的开发模式：

* **HTML5**: 语义化标签结构。  
* **Tailwind CSS (CDN)**: 使用 CDN 直接引入，无需 npm install 或复杂的构建流程即可修改样式。  
* **Vanilla JavaScript**: 原生 JS 实现简单的交互（如导航栏滚动、Tab 切换、移动端菜单）。  
* **Lucide Icons**: 轻量级图标库。  
* **Google Fonts**: 使用 Noto Sans SC 作为主要字体。

## **📂 目录结构**

HEU-ESTA-Website/  
├── index.html          \# 网站主入口文件（所有代码都在这里）  
├── image\_6662db.png    \# 协会 Logo 图片  
└── README.md           \# 项目说明文档

## **🚀 快速开始**

### **本地开发**

1. 克隆仓库到本地：  
   git clone \[https://github.com/你的用户名/你的仓库名.git\](https://github.com/你的用户名/你的仓库名.git)

2. 直接双击打开 index.html 即可在浏览器中预览。  
3. 推荐使用 VS Code 安装 **Live Server** 插件，右键选择 "Open with Live Server" 以获得实时热更新体验。

### **部署**

本项目是纯静态网页，非常适合部署在 **GitHub Pages** 或 **Gitee Pages**。

1. 在 GitHub 仓库中，点击 **Settings** \-\> **Pages**。  
2. 在 **Build and deployment** 下，选择 main 分支作为 Source。  
3. 点击 Save，几分钟后你将获得一个免费的 https://yourname.github.io/repo 域名。

## **📝 内容修改指南**

### **1\. 修改招新宣传视频**

找到 index.html 中的 \#about 部分，定位到 \<iframe\> 标签，修改 bvid 参数即可：

\<\!-- 修改 bvid 后面的字符串为你新视频的 BV 号 \--\>  
\<iframe src="\[https://player.bilibili.com/player.html?bvid=BV1AhnGzVEsD\](https://player.bilibili.com/player.html?bvid=BV1AhnGzVEsD)&..." ...\>\</iframe\>

### **2\. 修改图片/Logo**

* **Logo**: 替换根目录下的 image\_6662db.png，或者在 HTML 中修改 \<img src="..."\> 的路径。  
* **背景图/插图**: 目前使用的是 Unsplash 的占位图链接，你可以将其替换为本地图片路径（建议新建一个 assets/ 文件夹存放）。

### **3\. 更新培训路线**

找到 \#training 部分，内容被包裹在 id="content-hw" (硬件) 和 id="content-sw" (软件) 中，直接修改文本即可。

## **🤝 贡献指南**

欢迎协会的同学们提交 PR 完善这个网站！

1. Fork 本仓库  
2. 新建 Feat\_xxx 分支  
3. 提交代码  
4. 新建 Pull Request

## **📄 许可证**

本项目开源，供哈尔滨工程大学电子科技协会内部使用及技术交流。

**HEU ESTA © 1995-2025**