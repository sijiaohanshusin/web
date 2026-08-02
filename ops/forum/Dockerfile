# NodeBB 论坛镜像（自构建：Docker Hub 官方镜像标签陈旧且国内镜像源拉不到，
# 改为 node 基础镜像 + GitHub codeload 源码，全链路国内可达）
# 注意：NodeBB v4.14+ 要求 Node >= 22
FROM node:22-slim

ARG NODEBB_VERSION=4.14.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

ADD https://codeload.github.com/NodeBB/NodeBB/tar.gz/refs/tags/v${NODEBB_VERSION} /tmp/nodebb.tar.gz
RUN tar -xzf /tmp/nodebb.tar.gz -C /usr/src/app --strip-components=1 \
    && rm /tmp/nodebb.tar.gz \
    && cp install/package.json package.json  # NodeBB 的依赖清单在 install/ 下

# npm 走国内镜像；先安装 NodeBB 与账号互通插件。此层保持稳定，避免每次改自研插件都重装整个论坛。
# 注：表情(emoji)、@提及(mentions)、Markdown 均为 NodeBB 自带插件，无需额外安装
RUN npm config set registry https://registry.npmmirror.com \
    && npm install --omit=dev \
    && npm install nodebb-plugin-session-sharing \
    && npm cache clean --force \
    && chown -R node:node /usr/src/app

# 自研插件单独成层，日常更新只安装它及其少量依赖。
COPY plugins/nodebb-plugin-heuesta-mailbox /tmp/nodebb-plugin-heuesta-mailbox
RUN npm config set registry https://registry.npmmirror.com \
    && cd /tmp/nodebb-plugin-heuesta-mailbox \
    && npm pack --pack-destination /tmp \
    && cd /usr/src/app \
    && npm install --omit=dev /tmp/nodebb-plugin-heuesta-mailbox-*.tgz \
    && rm -f /tmp/nodebb-plugin-heuesta-mailbox-*.tgz \
    && rm -rf /tmp/nodebb-plugin-heuesta-mailbox \
    && npm cache clean --force \
    && chown -R node:node /usr/src/app/node_modules/nodebb-plugin-heuesta-mailbox

COPY --chmod=755 entrypoint.sh /entrypoint.sh

USER node
EXPOSE 4567
ENTRYPOINT ["/entrypoint.sh"]
