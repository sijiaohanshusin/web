#!/usr/bin/env bash
# 部署后抽查：确认那几条「配错了也不报错」的东西真的生效了。
#
# 用法（在服务器上）：sudo /opt/heuesta/web/ops/verify.sh
# 从开发机跑：先 scp 过去再执行，**不要用管道喂给 ssh** —— PowerShell 的管道会
# 按控制台编码重编码脚本内容，UTF-8 注释会被搞坏、连带把引号配对搞乱。
#
# 走 https 而不是 http：80 端口上 certbot 那个块会 301 跳 HTTPS，否则抽查全是 301。
# 用 curl --resolve 把域名钉到本机 —— 真实 SNI、真实证书，但绕开 EdgeOne 缓存。
# 不绕的话验出来的是「CDN 上次抓到的是什么」，而不是这台机器现在的配置。
#
# 只读，不改任何东西。
set -uo pipefail

DOMAIN=heuesta.cn
R="--resolve $DOMAIN:443:127.0.0.1"
BASE="https://$DOMAIN"
STATIC=/srv/heuesta/static
fails=0

ok()   { printf '  OK   %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; fails=$((fails + 1)); }
note() { printf '  --   %s\n' "$*"; }

echo "应用"
for path in / /recruit/ /works/ /honors/ /team/ /news/ /accounts/register/ /recruitment/; do
    c=$(curl -sS $R -o /dev/null -w '%{http_code}' "$BASE$path")
    if [ "$c" = "200" ]; then ok "$path 200"; else bad "$path 返回 $c"; fi
done

echo
echo "X-Frame-Options（Django 发不出来：simpleui 把那个中间件摘了，靠 nginx 补）"
xfo=$(curl -sS $R -I "$BASE/" | tr -d '\r' | grep -i '^x-frame-options:' | head -1)
if [ -z "$xfo" ]; then
    bad "首页没有 X-Frame-Options —— 登录页与注册表单能被任意站点套进 iframe"
elif echo "$xfo" | grep -qi sameorigin; then
    ok "$xfo"
else
    bad "取值不是 SAMEORIGIN: $xfo"
fi

echo
echo "静态资源压缩（nginx 1.21.1 起 .js 的默认 MIME 是 text/javascript；"
echo "gzip_types 只写 application/javascript 的话，所有 JS 都是原样发的）"
js=$(ls -S "$STATIC"/vendor/*.js "$STATIC"/js/*.js 2>/dev/null | head -1)
if [ -z "$js" ]; then
    bad "$STATIC 下找不到 JS，collectstatic 没跑过？"
else
    rel="/static${js#"$STATIC"}"
    raw=$(stat -c %s "$js")
    hdrs=$(curl -sS $R -I -H 'Accept-Encoding: gzip' "$BASE$rel" | tr -d '\r')
    sent=$(curl -sS $R -o /dev/null -w '%{size_download}' \
           -H 'Accept-Encoding: gzip' "$BASE$rel")
    note "取样 $(basename "$js")  原始 $((raw / 1024)) KB"
    note "$(echo "$hdrs" | grep -i '^content-type:' | head -1)"
    if echo "$hdrs" | grep -qi '^content-encoding:.*gzip'; then
        ok "JS 走了 gzip：实收 $((sent / 1024)) KB，压到 $((sent * 100 / raw))%"
    else
        bad "JS 没有压缩：实收 $((sent / 1024)) KB / 原始 $((raw / 1024)) KB"
    fi
fi

css=$(ls -S "$STATIC"/css/*.css 2>/dev/null | head -1)
if [ -n "$css" ]; then
    rel="/static${css#"$STATIC"}"
    hdrs=$(curl -sS $R -I -H 'Accept-Encoding: gzip' "$BASE$rel" | tr -d '\r')
    if echo "$hdrs" | grep -qi '^content-encoding:.*gzip'; then
        ok "CSS 走了 gzip"
    else
        bad "CSS 没有压缩"
    fi
    n=$(echo "$hdrs" | grep -ci '^cache-control:')
    line=$(echo "$hdrs" | grep -i '^cache-control:' | tr '\n' ' ')
    if [ "$n" = "1" ]; then
        ok "静态资源只有一条 Cache-Control: $line"
    else
        bad "静态资源有 $n 条 Cache-Control（CDN 取哪条不好说）: $line"
    fi
    if echo "$line" | grep -qi immutable; then ok "带 immutable"; else bad "缺 immutable"; fi
fi

echo
echo "自托管字体（少一个，首屏大标题会先用系统黑体画一遍再跳成真 Heavy）"
for stem in JetBrainsMono-subset SourceHanSansCN-Heavy-subset; do
    p=$(ls "$STATIC"/fonts/ 2>/dev/null | grep -F "$stem" | head -1)
    if [ -z "$p" ]; then
        bad "$stem 不在 $STATIC/fonts 下"
    else
        c=$(curl -sS $R -o /dev/null -w '%{http_code}' "$BASE/static/fonts/$p")
        kb=$(( $(stat -c %s "$STATIC/fonts/$p") / 1024 ))
        if [ "$c" = "200" ]; then ok "$p 可达（$kb KB）"; else bad "$p 返回 $c"; fi
    fi
done

echo
echo "首页真的是新版（找几个改版才有的标记）"
html=$(curl -sS $R "$BASE/")
for probe in 'skip-link' 'view-transitions' 'nf-hero' 'SourceHanSansCN-Heavy-subset'; do
    if echo "$html" | grep -q "$probe"; then
        ok "首页含 $probe"
    else
        bad "首页找不到 $probe —— 装上去的可能还是旧版"
    fi
done

echo
echo "容器"
docker compose -f /opt/heuesta/web/ops/docker-compose.yml \
    --env-file /opt/heuesta/.env ps \
    --format '  --   {{.Service}}  {{.Status}}' 2>/dev/null \
    || note "docker compose ps 读不到"

echo
if [ "$fails" -gt 0 ]; then
    echo "$fails 项未通过"
    exit 1
fi
echo "部署后抽查全部通过"
