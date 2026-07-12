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

# npm 走国内镜像；预装 session-sharing 插件（账号互通）
RUN npm config set registry https://registry.npmmirror.com \
    && npm install --omit=dev \
    && npm install nodebb-plugin-session-sharing \
    && npm cache clean --force \
    && chown -R node:node /usr/src/app

COPY --chmod=755 entrypoint.sh /entrypoint.sh

USER node
EXPOSE 4567
ENTRYPOINT ["/entrypoint.sh"]
