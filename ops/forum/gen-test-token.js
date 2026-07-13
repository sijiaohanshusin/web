'use strict';
/* 生成模拟新用户的 SSO JWT（仅测试用）：node gen-test-token.js */
const jwt = require('/usr/src/app/node_modules/jsonwebtoken');
const payload = {
    id: 99901,
    username: 'betatest01',
    fullname: '内测演习号',
    groups: ['会员'],
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
};
process.stdout.write(jwt.sign(payload, process.env.S));
