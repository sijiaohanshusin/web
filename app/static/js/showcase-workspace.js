/* The workspace owns one draft. Sections are views of that draft, not separate forms. */
(() => {
  "use strict";
  const root = document.querySelector("#showcase-editor");
  if (!root) return;
  const { EditorState, clone, move, removeWork, references } = window.ShowcaseState;
  const boot = JSON.parse(document.querySelector("#showcase-bootstrap").textContent);
  const model = new EditorState(boot), options = boot.options, projects = boot.projects;
  const $ = (selector, scope = root) => scope.querySelector(selector);
  const $$ = (selector, scope = root) => [...scope.querySelectorAll(selector)];
  const content = $("#section-content"), stage = $("#preview-stage"), inspector = $("#inspector");
  const csrf = $("input[name=csrfmiddlewaretoken]").value;
  const names = { "card-layout":"版式与身份", "card-background":"背景与照片", "card-content":"内容与排序", "page-layout":"布局与内容", "page-works":"精选作品", "page-gallery":"图集与链接", assets:"素材库", publish:"预览与发布" };
  let section = names[new URL(location.href).searchParams.get("section")] ? new URL(location.href).searchParams.get("section") : "card-layout";
  let device = "desktop", composing = false, previewTimer, previewAbort, templateAbort, messageTimer;
  let pickerPath = "", selectedAsset = "", workId = "", templates = {}, documents = {}, confirmed = false, lastPreview = -1;
  let conflictServer = null, drag = null, confirmationResolve, saveError = "";
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const get = path => path.split(".").reduce((v, k) => v?.[k], model.draft);
  const asset = id => model.server.assets.find(a => a.id === id);
  const imageUrl = id => asset(id)?.url || "";
  const btn = (label, attrs="", cls="") => '<button type="button" class="se-button '+cls+'" '+attrs+'>'+label+'</button>';
  const help = text => '<p class="se-help">'+text+'</p>';
  const panel = (title, body, extra="") => '<section class="se-panel"><div class="se-panel-heading"><h2>'+title+'</h2>'+extra+'</div>'+body+'</section>';
  const field = (path, label, config={}) => {
    let input;
    const attrs = 'data-field="'+path+'" id="field-'+path.replaceAll(".","-")+'" '+(config.disabled?"disabled ":"")+(config.max?'maxlength="'+config.max+'" ':'');
    if (config.choices) input = '<select '+attrs+'>'+Object.entries(config.choices).map(([key,name])=>'<option value="'+esc(key)+'" '+(String(get(path))===key?"selected":"")+'>'+esc(name)+'</option>').join("")+'</select>';
    else if (config.area) input = '<textarea '+attrs+' rows="'+(config.rows||3)+'" placeholder="'+esc(config.placeholder||"")+'">'+esc(get(path))+'</textarea>';
    else input = '<input '+attrs+' type="'+(config.type||"text")+'" value="'+esc(get(path))+'" placeholder="'+esc(config.placeholder||"")+'">';
    return '<label class="se-field"><span>'+label+'</span>'+input+(config.hint?'<small>'+config.hint+'</small>':"")+'</label>';
  };
  const segment = (path, choices) => '<div class="se-segment">'+Object.entries(choices).map(([key,label])=>'<button type="button" data-set="'+path+'" data-value="'+key+'" aria-pressed="'+(get(path)===key)+'">'+esc(label)+'</button>').join("")+'</div>';
  const range = (path, label, min, max, step=1) => '<label class="se-field"><span class="se-row-between">'+label+' <output data-output="'+path+'">'+get(path)+'</output></span><input type="range" data-field="'+path+'" min="'+min+'" max="'+max+'" step="'+step+'" value="'+get(path)+'"></label>';
  const imageControl = (path, label="选择图片") => '<div class="se-image-control">'+(imageUrl(get(path))?'<img src="'+imageUrl(get(path))+'" alt="'+esc(label)+'">':'<div class="se-image-empty">尚未选择图片 · 上传或从素材库选择</div>')+'<div class="se-row">'+btn(label,'data-pick="'+path+'"')+(get(path)?btn("移除引用",'data-clear="'+path+'"',"se-subtle"):"")+'</div></div>';
  const templateGrid = target => '<div class="se-template-grid">'+Object.entries(options.templates).map(([id,name])=>'<button type="button" class="se-template" data-set="'+target+'.template" data-value="'+id+'" aria-pressed="'+(get(target+".template")===id)+'"><div class="se-thumb" data-template-frame="'+target+'-'+id+'"></div><strong>'+name+'</strong><small>'+({plate:"秩序清晰 · 工程感",gallery:"照片主导 · 沉浸表达",type:"文字留白 · 个人叙事"}[id])+'</small></button>').join("")+'</div>';
  const sharedStyles = target => '<div class="se-grid-two">'+field(target+".palette","点缀配色",{choices:options.palettes})+field(target+".texture","背景纹理",{choices:options.textures})+'</div><div class="se-spaced">'+field(target+".avatar_shape","头像形状",{choices:options.shapes})+'</div>';
  const orderControls = (path,index,length) => '<button type="button" class="se-icon-button" data-move="'+path+'" data-index="'+index+'" data-to="'+(index-1)+'" aria-label="向前移动" '+(index===0?"disabled":"")+'>↑</button><button type="button" class="se-icon-button" data-move="'+path+'" data-index="'+index+'" data-to="'+(index+1)+'" aria-label="向后移动" '+(index===length-1?"disabled":"")+'>↓</button>';
  function moduleList(target) {
    const selected = get(target+".modules"), choices = target==="card"?options.cardModules:options.pageModules;
    const ordered = [...selected,...Object.keys(choices).filter(k=>!selected.includes(k))];
    return '<div class="se-module-list">'+ordered.map(key=>{
      const active=selected.includes(key), index=selected.indexOf(key), official=["history","medals"].includes(key);
      return '<div class="se-module" draggable="'+active+'" data-drag-path="'+target+'.modules" data-drag-index="'+index+'"><span class="se-grip" aria-hidden="true">⠿</span><span class="se-module-name">'+choices[key]+(official?'<small>官方记录只读，可自主选择展示</small>':"")+'</span>'+(active?orderControls(target+".modules",index,selected.length):"")+'<input type="checkbox" class="se-toggle" data-module="'+target+'" value="'+key+'" aria-label="显示'+choices[key]+'" '+(active?"checked":"")+'></div>';
    }).join("")+'</div>';
  }
  function heading(title, description, eyebrow) {
    return '<header class="se-section-heading"><div><p class="se-eyebrow">'+eyebrow+'</p><h1>'+title+'</h1><p>'+description+'</p></div></header>';
  }
  function layoutCard() {
    const years={"":"不展示届别"}; for(let y=new Date().getFullYear();y>=1995;y--) years[y]=y+" 级";
    const avatar='<div class="se-identity-avatar">'+(imageUrl(get("content.avatar"))?'<img class="se-avatar-image" src="'+imageUrl(get("content.avatar"))+'" alt="展示头像">':'<span class="se-avatar-image se-avatar-fallback">'+esc((get("nickname")||"我")[0])+'</span>')+btn("选择展示头像",'data-pick="content.avatar"')+btn("复制账号头像",'data-copy-avatar',"se-subtle")+help("独立于账号头像<br>卡片与个人页面共用")+'</div>';
    const identity=field("nickname","公开昵称",{max:30,hint:"仅用于成员展示，不修改入会档案姓名。"})+'<div class="se-grid-two">'+field("cohort","公开入学届别",{choices:years})+field("direction","公开擅长方向",{choices:{hardware:"硬件",software:"软件",custom:"自定义"}})+'</div>'+(get("direction")==="custom"?'<div class="se-spaced">'+field("direction_detail","方向补充说明",{max:40,hint:"选择自定义方向时展示。"})+'</div>':"");
    return heading("版式与身份","从一张名片开始，设计别人认识你的第一眼。","MEMBER CARD / LAYOUT")+
      panel("选择卡片版式",templateGrid("card")+help("切换仅改变布局，已填写的内容会保留。"))+
      panel("公开身份",'<div class="se-identity-editor">'+avatar+'<div>'+identity+'</div></div><div class="se-official"><span class="se-label">官方身份 · 来自任命记录</span>'+$("#official-identity").innerHTML+help("现任职位与任期由系统同步，个人设计不会改变官方身份。")+'</div>')+
      panel("外观细节",sharedStyles("card"));
  }
  function background() {
    const bg=get("card.background"), a=asset(bg.image);
    const presets='<div class="se-presets" data-mode="'+bg.mode+'">'+Object.entries(options.presets).map(([id,name])=>'<button type="button" class="se-preset" data-set="card.background.preset" data-value="'+id+'" aria-pressed="'+(bg.preset===id)+'"><span class="se-swatch se-swatch--'+id+'"></span>'+name+'</button>').join("")+'</div>';
    let inner;
    if(bg.mode==="photo") {
      inner = (a?'<div class="se-row-between"><span class="se-label">'+esc(a.name)+'</span><div class="se-row">'+btn("更换背景照片",'data-pick="card.background.image"')+btn("移除引用",'data-clear="card.background.image"',"se-subtle")+'</div></div>':imageControl("card.background.image","选择背景照片"))+
        (a?'<div class="se-spaced"><div class="se-crop" id="crop-control" tabindex="0" role="group" aria-label="照片焦点，点击或使用方向键调整"><img src="'+a.large_url+'" alt="调整照片取景" style="object-position:'+bg.x+'% '+bg.y+'%;transform:scale('+bg.zoom+')"><span class="se-crop-point" style="left:'+bg.x+'%;top:'+bg.y+'%"></span></div></div>':"")+
        help("拖动取景焦点，或用方向键微调。取景不会修改原素材。")+
        '<div class="se-grid-two">'+range("card.background.x","水平焦点",0,100)+range("card.background.y","垂直焦点",0,100)+'</div>'+range("card.background.zoom","裁切缩放",1,1.5,.01)+
        '<div class="se-grid-two">'+field("card.background.blur","背景模糊",{choices:options.blurs})+field("card.background.mask","文字区域遮罩",{choices:options.masks})+'</div>'+help("遮罩保留安全下限，确保昵称和身份信息清晰。")+
        btn("恢复取景",'data-reset-crop',"se-subtle");
    } else inner=presets+help(bg.mode==="gradient"?"精选渐变让纯文字也有完整的设计效果。":"纯色背景保持克制，让文字成为主角。")+sharedStyles("card");
    return heading("背景与照片","把真实的工作瞬间，变成你的独特背景。","MEMBER CARD / BACKGROUND")+
      panel("背景来源",segment("card.background.mode",{photo:"本人照片",gradient:"预设渐变",solid:"纯色"})+help("卡片背景独立设置，不会覆盖个人页封面。"))+
      panel(bg.mode==="photo"?"照片与取景":bg.mode==="gradient"?"渐变与质感":"纯色与细节",inner);
  }
  const workChoices = () => Object.fromEntries([["","不选择精选作品"],...get("content.works").map(w=>[w.id,w.title||projects.find(p=>p.id===w.project)?.name||"未命名作品"])]);
  function cardContent() {
    return heading("内容与排序","有选择地表达自己，让每一条信息都恰到好处。","MEMBER CARD / CONTENT")+
      panel("卡片内容模块",help("已启用 "+get("card.modules").length+" / 3 个模块。拖动或用上下按钮调整顺序，关闭不会删除内容。")+moduleList("card"))+
      panel("短介绍",field("content.intro","一句话，让大家认识你",{area:true,max:60,hint:"最多 60 字，卡片空间有限，较长内容会截断。"}))+
      panel("技能标签",'<div class="se-tags">'+get("content.tags").map((tag,i)=>'<span class="se-tag">'+esc(tag)+'<button type="button" data-remove-tag="'+i+'" aria-label="移除'+esc(tag)+'">×</button></span>').join("")+'</div><div class="se-row"><input class="se-input" id="tag-entry" maxlength="12" placeholder="输入标签，按回车添加" aria-label="新标签">'+btn("添加标签",'data-add-tag')+'</div>'+help("最多 4 个标签，每个最多 12 字。"))+
      panel("精选作品",field("card.featured_work","在名片中展示哪件作品",{choices:workChoices()})+help("此选择独立于个人页作品顺序。作品转为私密后会隐藏，不会自动替换。")+btn("管理我的作品",'data-section-link="page-works"',"se-subtle"));
  }
  function pageLayout() {
    return heading("布局与内容","给你的经历、作品与热爱一个完整的空间。","PERSONAL PAGE / LAYOUT")+
      panel("个人页模板",templateGrid("page")+help("独立于成员卡片。预览与真实个人展示页共用组件。"))+
      panel("页面内容模块",help("已启用 "+get("page.modules").length+" / 7 类模块。官方记录来自网站，展示与否由你决定。")+moduleList("page"))+
      panel("自我介绍与技能",field("content.about","自我介绍",{area:true,rows:5,max:2400,hint:"支持换行，不支持 HTML、嵌入网页或脚本。"})+field("content.skills","技能与兴趣",{area:true,max:600}))+
      panel("个人页封面与细节",imageControl("content.cover","选择个人页封面")+help("封面用于工程铭牌的工作台主图和作品橱窗模板。更换模板会保留选图；文字档案不使用封面。")+field("page.focus","封面焦点",{choices:options.focus})+sharedStyles("page"));
  }
  function works() {
    const list=get("content.works");
    if(!list.some(w=>w.id===workId)) workId=list[0]?.id||"";
    const index=list.findIndex(w=>w.id===workId), w=list[index];
    const path="content.works."+index;
    const tabs='<div class="se-entry-list">'+list.map((item,i)=>'<button type="button" class="se-entry" data-work="'+item.id+'" aria-pressed="'+(item.id===workId)+'">'+(imageUrl(item.image)?'<img src="'+imageUrl(item.image)+'" alt="">':'<span class="se-entry-placeholder">'+(i+1)+'</span>')+'<span>'+esc(item.title||"未命名作品")+'</span></button>').join("")+'</div>';
    let detail = '<div class="se-empty"><strong>从你的第一件作品开始</strong>可以独立填写，也可关联已公开的站内项目。</div>';
    if(w) detail='<div><div class="se-row-between"><span class="se-label">作品 '+(index+1)+' / '+list.length+'</span><div class="se-row">'+orderControls("content.works",index,list.length)+btn("移除",'data-remove-work="'+w.id+'"',"se-subtle")+'</div></div><div class="se-spaced">'+imageControl(path+".image","选择作品封面")+'</div><div class="se-spaced">'+field(path+".title","作品名称",{max:60,placeholder:"例如：桌面信号发生器"})+'</div>'+field(path+".description","作品说明",{area:true,max:240})+field(path+".project","关联已公开的站内项目",{choices:Object.fromEntries([["","独立作品，不关联项目"],...projects.map(p=>[p.id,p.name])]),hint:"仅引用公开展示，不获得项目成员身份或编辑权限。"})+
      (w.project?'<div class="se-notice">使用站内公开地址：'+esc(projects.find(p=>p.id===w.project)?.url||"项目不再公开，发布前请调整关联")+'</div>':"")+field(path+".url","外部作品地址",{type:"url",disabled:!!w.project,hint:w.project?"关联项目时不再使用外链。":"只接受 HTTPS，不会自动抓取远程内容。"})+
      '<label class="se-consent"><input type="checkbox" data-feature-work="'+w.id+'" '+(get("card.featured_work")===w.id?"checked":"")+'>选择为成员卡片的精选作品</label></div>';
    return heading("精选作品","把想法做出来，也让作品被看见。","PERSONAL PAGE / WORKS")+
      panel("我的作品",'<div class="se-list-editor">'+tabs+detail+'</div>',btn("＋ 添加作品",'data-add-work '+(list.length>=6?"disabled":""),"se-subtle"))+
      help("最多 6 件作品。卡片选择保持独立，调整这里的顺序不会改变卡片精选。");
  }
  function galleryLinks() {
    const photos=get("content.gallery"), links=get("content.links");
    return heading("图集与链接","记录创作的过程，连接更多关于你的内容。","PERSONAL PAGE / COLLECTION")+
      panel("图片集",'<div class="se-gallery-editor">'+photos.map((p,i)=>'<div class="se-gallery-entry" draggable="true" data-drag-path="content.gallery" data-drag-index="'+i+'"><div>'+(imageUrl(p.image)?'<img src="'+imageUrl(p.image)+'" alt="图集图片">':'<div class="se-entry-placeholder">＋</div>')+'<button type="button" class="se-link-button" data-pick="content.gallery.'+i+'.image">更换</button></div><div>'+field("content.gallery."+i+".caption","图片说明",{max:100})+'<div class="se-row">'+orderControls("content.gallery",i,photos.length)+btn("移除",'data-remove-item="content.gallery" data-index="'+i+'"',"se-subtle")+'</div></div></div>').join("")+'</div>'+(photos.length?"":'<div class="se-empty">实验、焊接、调试，也值得被记录。</div>')+help("最多 6 张，不会从外部网址加载图片。"),btn("＋ 添加图片",'data-add-gallery '+(photos.length>=6?"disabled":""),"se-subtle"))+
      panel("外部链接",links.map((link,i)=>'<div class="se-spaced"><div class="se-grid-two">'+field("content.links."+i+".label","链接名称",{max:40})+field("content.links."+i+".url","HTTPS 地址",{type:"url"})+'</div><div class="se-row se-spaced">'+orderControls("content.links",i,links.length)+btn("移除",'data-remove-item="content.links" data-index="'+i+'"',"se-subtle")+'</div><hr class="se-divider"></div>').join("")+(links.length?"":'<div class="se-empty">你的网站、代码仓库或其他公开主页。</div>')+help("请确认链接中没有密码、私人文件或个人敏感信息。"),btn("＋ 添加链接",'data-add-link '+(links.length>=6?"disabled":""),"se-subtle"));
  }
  const size = bytes => bytes==null?"体积未知":bytes<1048576?(bytes/1024).toFixed(0)+" KB":(bytes/1048576).toFixed(2)+" MB";
  const uploadBox = () => '<div class="se-upload" data-dropzone>'+btn("＋ 上传图片",'data-upload-file',"se-primary")+' '+btn("复制账号头像",'data-copy-avatar',"se-subtle")+'<p>JPEG / PNG / WebP · 每张不超过 5 MB · 最大 8 MP</p><p>图片重新编码并移除 EXIF，原始文件不会保留。也可拖入文件。</p><input type="file" accept="image/jpeg,image/png,image/webp" data-file-input hidden></div>';
  const assetTile = (a,picking=false) => '<button type="button" class="se-asset" '+(picking?'data-select-asset':'data-inspect-asset')+'="'+a.id+'" aria-pressed="'+(a.id===selectedAsset)+'"><img src="'+a.url+'" alt="'+esc(a.name)+'"><strong>'+esc(a.name)+'</strong><small>'+a.width+' × '+a.height+' · '+a.format+' · '+size(a.bytes)+'</small><small>'+esc(a.public_uses.length?"公开使用中":a.draft_uses.length?"已保存草稿使用中":"尚未保存引用")+'</small></button>';
  function library() {
    return heading("素材库","你的图片，一处管理，多处使用。","MY ASSETS / PRIVATE")+
      '<div class="se-row-between"><span class="se-label">'+model.server.assets.length+' / 20 张素材</span><span class="se-badge">受保护存储</span></div>'+uploadBox()+
      '<div class="se-asset-grid">'+model.server.assets.map(a=>assetTile(a)).join("")+'</div>'+(model.server.assets.length?"":'<div class="se-empty"><strong>素材库还是空的</strong>上传你的工作照片、作品封面或展示头像。</div>');
  }
  function publicState() {
    const s=model.server;
    return s.blocked?"被管理员下架":s.published?"已有公开版本":s.withdrawal_reason?"已撤回":"尚未公开";
  }
  function publish() {
    return heading("预览与发布","认真检查，确认这是你想与大家分享的样子。","REVIEW / PUBLISH")+
      '<div class="se-public-state">公开状态：<strong>'+publicState()+'</strong>'+(model.server.published?' · <a href="'+model.server.public_url+'" target="_blank" rel="noopener">查看当前公开页 ↗</a>':"")+'</div>'+
      '<div class="se-notice">进入本页不会自动公开。卡片与个人页同时确认，发布后才会替换当前公开版本。</div>'+
      '<div class="se-publish-previews"><section><h2>成员卡片</h2><div data-publish-frame="card"></div></section><section><h2>个人展示页</h2><div data-publish-frame="page"></div></section></div>';
  }
  function render() {
    content.innerHTML='<div class="se-section">'+({"card-layout":layoutCard,"card-background":background,"card-content":cardContent,"page-layout":pageLayout,"page-works":works,"page-gallery":galleryLinks,assets:library,publish}[section])()+'</div>';
    root.querySelector(".se-workbench").dataset.section=section;
    $$("[data-section-link]").forEach(a=>a.setAttribute("aria-current",a.dataset.sectionLink===section?"page":"false"));
    $("#preview-title").textContent=section==="assets"?"素材详情":section==="publish"?"发布检查":"实时预览";
    mobilePreviewLabel();
    stage.hidden=section==="assets"||section==="publish";
    renderInspector();
    mountTemplates();
    if(section==="publish") mountPublish();
    status();
  }
  function status(text, error=false) {
    const el=$("#save-state");
    el.textContent=text||(model.busy?"保存中…":saveError?"保存失败 · 输入已保留":model.dirty?"● 未保存修改":"✓ 草稿已保存");
    el.dataset.state=error||saveError?"error":model.dirty?"dirty":"saved";
    const notice=$("#moderation-notice");
    notice.hidden=!model.server.blocked;
    notice.textContent="展示已被下架："+(model.server.moderation_reason||"请联系管理员了解原因")+"。仍可修改草稿，解除限制后须由你重新发布。";
    root.dataset.busy=String(model.busy);
    $$("button,input,select,textarea").forEach(el=>{
      if(model.busy) { if(!el.disabled) { el.disabled=true; el.dataset.busyDisabled="1"; } }
      else if(el.dataset.busyDisabled) { el.disabled=false; delete el.dataset.busyDisabled; }
    });
    $$('[data-operation="save"]').forEach(b=>b.disabled=model.busy);
    const publishButton=$('[data-operation="publish"]');
    if(publishButton) publishButton.disabled=model.busy||model.dirty||!model.ticket||!confirmed||model.server.blocked;
    const consent=$("#publish-consent");
    if(consent) consent.disabled=model.busy||model.dirty||!model.ticket||model.server.blocked;
  }
  function renderInspector() {
    if(section==="assets") {
      const a=asset(selectedAsset)||model.server.assets[0]; selectedAsset=a?.id||"";
      inspector.innerHTML=a?'<img class="se-asset-hero" src="'+a.large_url+'" alt="'+esc(a.name)+'"><div class="se-inspector"><h3>'+esc(a.name)+'</h3><dl><dt>格式与尺寸</dt><dd>'+a.format+' · '+a.width+' × '+a.height+'</dd><dt>实际体积</dt><dd>'+size(a.bytes)+'</dd><dt>当前编辑</dt><dd>'+(references(model.draft).has(a.id)?(model.dirty?"有引用，修改尚未保存":"有引用，与保存草稿一致"):(a.draft_uses.length?"已移除，尚需保存":"未引用"))+'</dd><dt>保存草稿</dt><dd>'+esc(a.draft_uses.join("、")||"未引用")+'</dd><dt>公开版本</dt><dd>'+esc(a.public_uses.join("、")||"未引用")+'</dd></dl>'+btn("删除素材",'data-delete-asset="'+a.id+'" '+((!a.can_delete||references(model.draft).has(a.id)||model.dirty)?"disabled":""),"se-danger")+help("移除引用不会删除文件。请先保存引用变更；草稿或公开版本使用中的图片不能删除。")+'</div>':'<div class="se-empty">选择一张图片查看用途</div>';
      return;
    }
    if(section==="publish") {
      inspector.innerHTML='<h2 style="font-size:18px;margin-top:24px">发布前检查</h2><ul class="se-checklist"><li data-ok="'+!!get("nickname")+'">已填写公开昵称</li><li data-ok="'+!model.dirty+'">'+(model.dirty?"请先保存这次修改":"草稿已保存")+'</li><li data-ok="'+!!model.ticket+'">'+(model.ticket?"卡片与个人页预览已更新":"正在等待最新双预览")+'</li><li data-ok="'+!model.server.blocked+'">'+(model.server.blocked?"等待管理员解除下架限制":"当前具备公开展示资格")+'</li></ul>'+
        (model.dirty?btn("先保存并刷新预览",'data-operation="save"',"se-primary se-publish-button"):"")+
        '<label class="se-consent"><input type="checkbox" id="publish-consent" '+(confirmed?"checked":"")+'>我确认昵称、图片、自填文字和链接将面向互联网公开。未启用的模块不会公开；学号、联系方式等档案不会自动展示。撤回无法收回他人已下载的内容。</label>'+
        btn(model.server.published?"确认更新公开版本":"确认发布我的展示",'data-operation="publish"',"se-primary se-publish-button")+
        help("无需管理员预审。任职经历与勋章的开关，不代表修改或授予官方记录。")+
        (model.server.published?btn("撤回公开展示",'data-operation="withdraw"',"se-subtle se-publish-button"):"");
      status();
    } else inspector.innerHTML='<div class="se-inspector"><h3>展示说明</h3>'+help("昵称、届别和方向是独立公开信息。官方职位由任命记录同步，不随设计更改。")+help("长介绍可能按卡片空间截断，请同时检查桌面与手机预览。")+'</div>';
  }
  function showSection(next, push=true) {
    if(!names[next]||model.busy) return;
    section=next;
    if(push) { const url=new URL(location.href);url.searchParams.set("section",section);history.pushState({}, "",url); }
    root.dataset.menu="closed";$("#section-menu").setAttribute("aria-expanded","false");
    root.dataset.mobilePreview="false";$("#mobile-preview").setAttribute("aria-pressed","false");
    confirmed=false;model.ticket="";render();schedulePreview(0); requestTemplates();
    const lenis=window.ESTA?.motion?.lenis;
    if(lenis)lenis.scrollTo(0,{immediate:true,force:true});
    else window.scrollTo({top:0,behavior:"instant"});
  }
  function mobilePreviewLabel(){
    $("#mobile-preview").textContent=root.dataset.mobilePreview==="true"?"返回编辑":section==="assets"?"素材详情":section==="publish"?"发布确认":"查看预览";
  }
  function toast(message) {
    clearTimeout(messageTimer);$("#editor-message").textContent=message;$("#editor-message").hidden=false;
    messageTimer=setTimeout(()=>$("#editor-message").hidden=true,6500);
  }
  function touch() {
    confirmed=false;model.ticket="";lastPreview=-1;previewAbort?.abort();templateAbort?.abort();
    $("#preview-status").textContent="内容已变化 · 正在更新预览";
    if($("#publish-consent")) $("#publish-consent").checked=false;
    status();schedulePreview();
  }
  function set(path,value,refresh=false) { model.set(path,value);touch();if(refresh)render(); }
  function sectionFor(path) {
    if(path.startsWith("content.works"))return"page-works";
    if(path.startsWith("content.gallery")||path.startsWith("content.links"))return"page-gallery";
    if(path.startsWith("card.background"))return"card-background";
    if(path.startsWith("content.intro")||path.startsWith("content.tags")||path==="card.modules"||path==="card.featured_work")return"card-content";
    if(path.startsWith("page")||["content.about","content.skills","content.cover"].includes(path))return"page-layout";
    if(path==="assets")return"assets";return"card-layout";
  }
  function errors(error) {
    const box=$("#form-errors");box.hidden=false;
    box.innerHTML='<strong>'+esc(error.message||"操作失败，请重试。")+'</strong>'+Object.entries(error.fields||{}).map(([path,messages])=>'<div><button type="button" data-error-field="'+esc(path)+'">'+esc(messages.join(" "))+' →</button></div>').join("");
    if(error.code==="conflict") recoverConflict();
  }
  async function request(url, init={}) {
    const timeout=new AbortController(), timer=setTimeout(()=>timeout.abort(),25000);
    const signal=init.signal?AbortSignal.any([init.signal,timeout.signal]):timeout.signal;
    try {
      const response=await fetch(url,{credentials:"same-origin",cache:"no-store",...init,signal,headers:{"X-CSRFToken":csrf,...init.headers}});
      let data;
      try { data=await response.json(); }
      catch(error) {
        if(signal.aborted)throw error;
        throw new Error(response.redirected?"登录已失效。请在新标签页重新登录，再回到这里重试。":"服务器暂时没有返回有效结果。你的输入已保留。");
      }
      if(!response.ok)throw Object.assign(new Error(data.error||"请求失败，请重试。"),data);
      return data;
    } catch(error) { if(timeout.signal.aborted)throw new Error("请求超时，当前输入已保留。请检查网络后重试。");throw error; }
    finally { clearTimeout(timer); }
  }
  function api(data,signal) { return request(root.dataset.action,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data),signal}); }
  function frame(container, documentText, kind, thumbnail=false) {
    if(!documentText)return;
    container.replaceChildren();
    const wrapper=document.createElement("div"), iframe=document.createElement("iframe");
    wrapper.className=thumbnail?"":"se-frame";wrapper.dataset.kind=kind;
    iframe.title=kind==="card"?"成员卡片预览":"个人页面预览";
    iframe.setAttribute("sandbox","allow-same-origin");iframe.setAttribute("referrerpolicy","no-referrer");
    if(thumbnail){iframe.tabIndex=-1;iframe.setAttribute("aria-hidden","true");}
    wrapper.append(iframe);container.append(wrapper);
    let observer;
    const fit=()=>{
      if(!wrapper.isConnected)return;
      const doc=iframe.contentDocument;if(!doc?.body)return;
      const desktop=device==="desktop"||thumbnail;
      doc.body.classList.toggle("sc-preview-desktop",desktop);
      doc.body.classList.toggle("sc-preview-mobile",!desktop);
      const width=kind==="card"?(desktop?400:360):(desktop?1000:375);
      const available=container.clientWidth;
      const scale=Math.min(1,available/width);
      iframe.style.width=width+"px";
      const height=kind==="card"?width*(desktop?5/3:4/3)+12:Math.max(500,doc.querySelector(".sc-page").getBoundingClientRect().height+12);
      iframe.style.height=height+"px";iframe.style.transform="scale("+scale+")";
      wrapper.style.height=(thumbnail?container.clientHeight:Math.min(kind==="page"?820:1000,height*scale))+"px";
      wrapper.style.width=Math.min(available,width)+"px";
      if(kind==="page"&&!thumbnail&&height*scale>820)wrapper.style.overflowY="auto";
      if(thumbnail) {
        const thumbScale = kind === "card" ? Math.min(available / width, container.clientHeight / height) : available / width;
        iframe.style.transform="scale("+thumbScale+")";
        iframe.style.left=Math.max(0,(available-width*thumbScale)/2)+"px";
      }
      wrapper.classList.add("se-frame-ready");
    };
    iframe.addEventListener("load",()=>{
      fit();iframe.contentDocument.fonts.ready.then(fit);
      iframe.contentDocument.querySelectorAll("img").forEach(img=>img.addEventListener("load",fit,{once:true}));
      observer=new ResizeObserver(fit);observer.observe(container);
      frameObservers.push([wrapper,observer]);
    },{once:true});
    iframe.srcdoc=documentText;
  }
  const frameObservers=[];
  function cleanFrames(){for(let i=frameObservers.length-1;i>=0;i--)if(!frameObservers[i][0].isConnected){frameObservers[i][1].disconnect();frameObservers.splice(i,1);}}
  function mountTemplates(){ $$("[data-template-frame]").forEach(el=>frame(el,templates[el.dataset.templateFrame],el.dataset.templateFrame.split("-")[0],true));cleanFrames(); }
  function mountPublish(){ $$("[data-publish-frame]").forEach(el=>frame(el,documents[el.dataset.publishFrame],el.dataset.publishFrame));cleanFrames(); }
  function mountPreview(){if(section==="publish")mountPublish();else if(section!=="assets")frame(stage,documents[section.startsWith("page")?"page":"card"],section.startsWith("page")?"page":"card");cleanFrames();}
  function schedulePreview(delay=350){clearTimeout(previewTimer);if(!composing&&!model.busy)previewTimer=setTimeout(updatePreview,delay);}
  async function updatePreview(){
    if(model.busy||composing)return;
    previewAbort?.abort();previewAbort=new AbortController();
    const snapshot=model.snapshot();
    $("#preview-status").textContent="正在更新预览…";
    try{
      const data=await api({action:"preview",target:"both",...snapshot},previewAbort.signal);
      if(!model.acceptPreview(snapshot,data.ticket))return;
      documents=data.documents;lastPreview=model.generation;
      $("#preview-status").textContent="预览已更新 · "+(model.dirty?"尚未保存":"与当前保存草稿一致");
      mountPreview();renderInspector();status();
    }catch(error){
      if(error.name==="AbortError"||!model.isCurrent(snapshot))return;
      model.ticket="";$("#preview-status").textContent="预览更新失败，保留上一次画面（已过期）";
      status();errors(error);
    }
  }
  async function requestTemplates(){
    if(!["card-layout","page-layout"].includes(section)||model.busy)return;
    templateAbort?.abort();templateAbort=new AbortController();
    const generation=model.generation, revision=model.revision;
    try{
      const data=await api({action:"preview",target:"templates",design:clone(model.draft),revision},templateAbort.signal);
      if(generation!==model.generation||revision!==model.revision)return;
      templates=data.documents;mountTemplates();
    }catch(error){if(error.name!=="AbortError")$("#preview-status").textContent="模板缩略图暂未更新；编辑内容已保留";}
  }
  async function operation(action){
    if(model.busy)return;
    if(action==="publish"&&(model.dirty||!model.ticket||!confirmed||lastPreview!==model.generation))return toast("请先保存、检查最新双预览并确认公开说明。");
    if(action==="withdraw"&&!await confirm("撤回公开展示？","成员墙、个人页和公开图片将停止新访问。草稿会保留，已被他人下载的内容无法收回。"))return;
    const snapshot=model.snapshot(), ticket=model.ticket;
    model.busy=true;saveError="";previewAbort?.abort();templateAbort?.abort();status();$("#form-errors").hidden=true;
    try{
      const data=await api({action,...snapshot,consent:action==="publish"&&confirmed,ticket});
      model.acceptSave(data,snapshot);confirmed=false;toast(data.message);
      render();
    }catch(error){saveError=error.message;status("保存失败 · 输入已保留",true);errors(error);}
    finally{model.busy=false;status();renderInspector();schedulePreview(0);requestTemplates();}
  }
  function confirm(title,description){
    const dialog=$("#editor-confirm");$("#confirm-title").textContent=title;$("#confirm-description").textContent=description;
    dialog.showModal();return new Promise(resolve=>confirmationResolve=resolve);
  }
  function finishConfirm(value){$("#editor-confirm").close();confirmationResolve?.(value);confirmationResolve=null;}
  async function recoverConflict(){
    try{
      conflictServer=await request(root.dataset.state);model.ticket="";confirmed=false;
      const entries=[["公开昵称","nickname"],["届别","cohort"],["卡片设计","card"],["个人页设计","page"],["展示内容","content"]];
      const value=(design,path)=>JSON.stringify(design[path],null,2);
      $("#conflict-diff").innerHTML='<div class="se-conflict-row"><strong>字段</strong><strong>当前未保存内容</strong><strong>服务器版本</strong></div>'+entries.map(([label,path])=>'<div class="se-conflict-row"><span>'+label+'</span><pre>'+esc(value(model.draft,path))+'</pre><pre>'+esc(value(conflictServer.draft,path))+'</pre></div>').join("");
      if(!$("#version-conflict").open)$("#version-conflict").showModal();
    }catch(error){toast("无法获取最新版本；当前输入仍保留，请稍后重试。");}
  }
  function picker(path){
    if(model.busy)return;pickerPath=path;renderPicker();$("#asset-picker").showModal();
  }
  function renderPicker(){
    $(".se-picker-upload").innerHTML=uploadBox();
    $(".se-picker-grid").innerHTML=model.server.assets.map(a=>assetTile(a,true)).join("")||'<div class="se-empty">暂无素材，先上传一张图片。</div>';
  }
  async function upload(file,copy=false){
    if(model.busy)return;
    if(file&&file.size>5*1024*1024)return toast("单张图片不能超过 5 MB。");
    const data=new FormData();if(copy)data.append("copy_avatar","1");else data.append("image",file);
    model.busy=true;status("正在处理图片…");
    const before=new Set(model.server.assets.map(a=>a.id));
    try{
      const response=await request(root.dataset.upload,{method:"POST",body:data});model.server.assets=response.assets;
      const added=response.assets.find(a=>!before.has(a.id));
      if(copy&&added&&section==="card-layout"&&!$("#asset-picker").open)model.set("content.avatar",added.id);
      selectedAsset=added?.id||selectedAsset;
      toast("图片已安全处理。选择用途后，再保存草稿。");render();if($("#asset-picker").open)renderPicker();
    }catch(error){errors(error);}
    finally{model.busy=false;status();schedulePreview();requestTemplates();}
  }
  async function deleteAsset(id){
    if(model.busy||model.dirty||references(model.draft).has(id))return toast("请先移除引用并保存，再删除素材。");
    const a=asset(id);if(!a?.can_delete)return toast("图片仍被保存草稿或公开版本使用。");
    if(!await confirm("删除这张素材？","只有不再被保存草稿或公开版本引用的图片才能删除。删除文件后无法恢复。"))return;
    model.busy=true;status();
    try{const data=await request(a.delete_url,{method:"POST"});model.server.assets=data.assets;render();toast("素材已删除。");}
    catch(error){errors(error);}finally{model.busy=false;status();}
  }
  function addTag(){
    const input=$("#tag-entry"), value=input?.value.trim();if(!value)return;
    const tags=get("content.tags");if(tags.length>=4)return toast("最多 4 个标签。");if(tags.includes(value))return toast("这个标签已经添加。");
    set("content.tags",[...tags,value],true);
  }
  function applyCrop(x,y){
    set("card.background.x",Math.round(Math.max(0,Math.min(100,x))));
    set("card.background.y",Math.round(Math.max(0,Math.min(100,y))));
    updateCrop();
  }
  function updateCrop(){
    const bg=get("card.background");
    for(const key of ["x","y","zoom"]){
      const path="card.background."+key;const el=$('[data-field="'+path+'"]');if(el)el.value=bg[key];
      const output=$('[data-output="'+path+'"]');if(output)output.textContent=bg[key];
    }
    const crop=$("#crop-control");if(crop){$("img",crop).style.objectPosition=bg.x+"% "+bg.y+"%";$("img",crop).style.transform="scale("+bg.zoom+")";$(".se-crop-point",crop).style.left=bg.x+"%";$(".se-crop-point",crop).style.top=bg.y+"%";}
  }
  root.addEventListener("input",event=>{
    const el=event.target;if(model.busy)return;
    if(el.matches("[data-field]")){
      set(el.dataset.field,el.type==="range"?Number(el.value):el.value);
      if(el.dataset.field.startsWith("card.background"))updateCrop();
    }
  });
  root.addEventListener("change",event=>{
    const el=event.target;if(model.busy)return;
    if(el.matches("select[data-field]")){
      if(el.dataset.field.endsWith(".project")&&el.value)model.set(el.dataset.field.replace(/project$/,"url"),"");
      set(el.dataset.field,el.value,true);requestTemplates();
    }else if(el.dataset.module){
      const path=el.dataset.module+".modules",list=get(path);
      set(path,el.checked?[...list,el.value]:list.filter(v=>v!==el.value),true);
    }else if(el.dataset.featureWork){set("card.featured_work",el.checked?el.dataset.featureWork:"",false);}
    else if(el.id==="publish-consent"){confirmed=el.checked;status();}
    else if(el.matches("[data-file-input]")&&el.files[0])upload(el.files[0]);
  });
  root.addEventListener("compositionstart",()=>{composing=true;clearTimeout(previewTimer);previewAbort?.abort();});
  root.addEventListener("compositionend",()=>{composing=false;schedulePreview();});
  root.addEventListener("keydown",event=>{
    if(event.key==="Escape"&&root.dataset.menu==="open"){root.dataset.menu="closed";$("#section-menu").setAttribute("aria-expanded","false");$("#section-menu").focus();}
    if(event.target.id==="tag-entry"&&event.key==="Enter"&&!event.isComposing){event.preventDefault();addTag();}
    if(event.target.id==="crop-control"&&["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)){event.preventDefault();const bg=get("card.background"),step=event.shiftKey?10:1;applyCrop(bg.x+(event.key==="ArrowRight"?step:event.key==="ArrowLeft"?-step:0),bg.y+(event.key==="ArrowDown"?step:event.key==="ArrowUp"?-step:0));}
  });
  root.addEventListener("pointerdown",event=>{
    const crop=event.target.closest("#crop-control");if(!crop||model.busy)return;
    crop.setPointerCapture(event.pointerId);
    const apply=e=>{const rect=crop.getBoundingClientRect();applyCrop((e.clientX-rect.left)/rect.width*100,(e.clientY-rect.top)/rect.height*100);};
    apply(event);const end=()=>{crop.removeEventListener("pointermove",apply);crop.removeEventListener("pointerup",end);crop.removeEventListener("pointercancel",end);};
    crop.addEventListener("pointermove",apply);crop.addEventListener("pointerup",end);crop.addEventListener("pointercancel",end);
  });
  root.addEventListener("click",async event=>{
    const el=event.target.closest("button,a[data-section-link]");if(!el||el.disabled)return;
    try{
      if(el.dataset.sectionLink){event.preventDefault();showSection(el.dataset.sectionLink);}
      else if(el.dataset.operation)await operation(el.dataset.operation);
      else if(el.dataset.set){set(el.dataset.set,el.dataset.value,true);requestTemplates();}
      else if(el.dataset.pick)picker(el.dataset.pick);
      else if(el.dataset.clear)set(el.dataset.clear,"",true);
      else if(el.hasAttribute("data-copy-avatar"))await upload(null,true);
      else if(el.hasAttribute("data-upload-file"))el.closest(".se-upload").querySelector("[data-file-input]").click();
      else if(el.dataset.selectAsset){const path=pickerPath;$("#asset-picker").close();set(path,el.dataset.selectAsset,true);}
      else if(el.dataset.inspectAsset){selectedAsset=el.dataset.inspectAsset;render();if(innerWidth<768){root.dataset.mobilePreview="true";$("#mobile-preview").setAttribute("aria-pressed","true");mobilePreviewLabel();}}
      else if(el.dataset.deleteAsset)await deleteAsset(el.dataset.deleteAsset);
      else if(el.hasAttribute("data-add-tag"))addTag();
      else if(el.hasAttribute("data-remove-tag"))set("content.tags",get("content.tags").filter((_,i)=>i!==Number(el.dataset.removeTag)),true);
      else if(el.dataset.move){
        const path=el.dataset.move,to=Number(el.dataset.to);
        set(path,move(get(path),Number(el.dataset.index),to),true);
        const button=$$('[data-move]').find(b=>b.dataset.move===path&&Number(b.dataset.index)===to&&!b.disabled);
        button?.focus({preventScroll:true});
      }
      else if(el.hasAttribute("data-add-work")){
        if(get("content.works").length>=6)return;workId=crypto.randomUUID();set("content.works",[...get("content.works"),{id:workId,title:"",description:"",image:"",url:"",project:""}],true);
      }else if(el.dataset.work){workId=el.dataset.work;render();}
      else if(el.dataset.removeWork){
        if(!await confirm("移除这件作品？","作品文字将从草稿移除，但素材不会删除。已公开的版本保持不变，直到你重新发布。"))return;
        const selected=get("card.featured_work")===el.dataset.removeWork;model.draft=removeWork(model.draft,el.dataset.removeWork);model.touch();touch();render();if(selected)toast("已清空卡片精选作品，请按需重新选择。");
      }else if(el.hasAttribute("data-add-gallery")){if(get("content.gallery").length>=6)return;const i=get("content.gallery").length;set("content.gallery",[...get("content.gallery"),{image:"",caption:""}],true);picker("content.gallery."+i+".image");}
      else if(el.hasAttribute("data-add-link")){if(get("content.links").length>=6)return;set("content.links",[...get("content.links"),{label:"",url:""}],true);}
      else if(el.dataset.removeItem)set(el.dataset.removeItem,get(el.dataset.removeItem).filter((_,i)=>i!==Number(el.dataset.index)),true);
      else if(el.hasAttribute("data-reset-crop")){for(const [key,value] of Object.entries({x:50,y:50,zoom:1,blur:"none",mask:"balanced"}))model.set("card.background."+key,value);touch();render();}
      else if(el.dataset.device){device=el.dataset.device;$$("[data-device]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.device===device)));mountPreview();}
      else if(el.hasAttribute("data-close-dialog"))el.closest("dialog").close();
      else if(el.hasAttribute("data-confirm-cancel"))finishConfirm(false);
      else if(el.hasAttribute("data-confirm-accept"))finishConfirm(true);
      else if(el.id==="section-menu"){const open=root.dataset.menu!=="open";root.dataset.menu=open?"open":"closed";el.setAttribute("aria-expanded",String(open));}
      else if(el.id==="mobile-preview"){const open=root.dataset.mobilePreview!=="true";root.dataset.mobilePreview=String(open);el.setAttribute("aria-pressed",String(open));mobilePreviewLabel();if(open)mountPreview();}
      else if(el.dataset.errorField){
        const path=el.dataset.errorField,match=path.match(/^content\.works\.(\d+)\./);
        if(match)workId=get("content.works")[Number(match[1])]?.id||"";
        showSection(sectionFor(path));
        const field=$('[data-field="'+CSS.escape(path)+'"]');if(field){field.setAttribute("aria-invalid","true");field.focus();}
      }
      else if(el.id==="download-draft"){const url=URL.createObjectURL(new Blob([JSON.stringify(model.draft,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="我的展示-未保存副本.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
      else if(el.id==="load-server-version"&&conflictServer){if(!await confirm("载入服务器版本？","当前页面尚未保存的内容会被替换。你可以先取消并下载副本。"))return;model.load(conflictServer);confirmed=false;saveError="";$("#version-conflict").close();$("#form-errors").hidden=true;render();schedulePreview(0);requestTemplates();}
    }catch(error){errors(error);}
  });
  $("#editor-confirm").addEventListener("cancel",()=>finishConfirm(false));
  $("#design-form").addEventListener("submit",event=>event.preventDefault());
  root.addEventListener("dragstart",event=>{const el=event.target.closest("[draggable=true]");if(!el||model.busy)return;drag={path:el.dataset.dragPath,index:Number(el.dataset.dragIndex)};event.dataTransfer.effectAllowed="move";event.dataTransfer.setData("text/plain",drag.path);el.classList.add("dragging");});
  root.addEventListener("dragover",event=>{const drop=event.target.closest("[data-dropzone]"),row=event.target.closest("[data-drag-path]");if(drop||row){event.preventDefault();if(drop)drop.classList.add("drag-over");}});
  root.addEventListener("dragleave",event=>event.target.closest("[data-dropzone]")?.classList.remove("drag-over"));
  root.addEventListener("drop",event=>{const drop=event.target.closest("[data-dropzone]"),row=event.target.closest("[data-drag-path]");if(drop){event.preventDefault();drop.classList.remove("drag-over");if(event.dataTransfer.files[0])upload(event.dataTransfer.files[0]);}else if(row&&drag&&row.dataset.dragPath===drag.path){event.preventDefault();set(drag.path,move(get(drag.path),drag.index,Number(row.dataset.dragIndex)),true);}drag=null;});
  root.addEventListener("dragend",()=>{$$(".dragging").forEach(el=>el.classList.remove("dragging"));drag=null;});
  addEventListener("popstate",()=>showSection(new URL(location.href).searchParams.get("section")||"card-layout",false));
  addEventListener("beforeunload",event=>{if(model.dirty||model.busy){event.preventDefault();event.returnValue="";}});
  document.addEventListener("visibilitychange",async()=>{
    if(document.hidden||model.busy)return;
    try{const server=await request(root.dataset.state);if(server.revision!==model.revision){model.ticket="";confirmed=false;status();$("#preview-status").textContent="服务器版本有更新；请保留当前内容并检查冲突。";}else{model.server.blocked=server.blocked;model.server.moderation_reason=server.moderation_reason;status();}}catch{/* The next explicit action reports authorization or connectivity errors. */}
  });
  $$("[disabled]").forEach(el=>el.disabled=false);
  render();schedulePreview(0);requestTemplates();
})();
