'use strict';
// Append a scoped logo contrast fix; preserve the current pixel theme and HTML.
const fs = require('fs');
const APP = process.env.NODEBB_APP_DIR || '/usr/src/app';
const nconf = require(APP + '/node_modules/nconf');
nconf.file({file:APP+'/config.json'});
nconf.defaults({base_dir:APP,views_dir:APP+'/build/public/templates',upload_path:'public/uploads'});
(async()=>{
    const db=require(APP+'/src/database');await db.init();
    const meta=require(APP+'/src/meta');await meta.configs.init();
    const before=await db.getObjectFields('config',['customCSS','useCustomCSS']);
    const marker='/* ESTA launch: logo contrast */';
    if ((before.customCSS||'').includes(marker)) { console.log('Logo contrast fix already present.');process.exit(0); }
    console.log('Existing theme retained; add dark cyan logo backing on its light header.');
    if (!process.argv.includes('--apply')) { console.log('Dry run; no changes.');process.exit(0); }
    const i=process.argv.indexOf('--snapshot');if(i<0||!process.argv[i+1])throw Error('--snapshot required');
    fs.writeFileSync(process.argv[i+1],JSON.stringify(before,null,2),{flag:'wx',mode:0o600});
    await meta.configs.setMultiple({customCSS:(before.customCSS||'')+'\n'+marker+'\nimg[component="brand/logo"] { background:#061c20; border:1px solid #0bb3c7; padding:6px; border-radius:8px; object-fit:contain; }',useCustomCSS:1});
    console.log('Logo contrast CSS compiled.');process.exit(0);
})().catch(error=>{console.error(error);process.exit(1);});
