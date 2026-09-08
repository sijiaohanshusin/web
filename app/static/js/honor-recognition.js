(() => {
  'use strict';
  const panel = document.querySelector('#honor-recognition');
  const form = document.querySelector('#honor-form');
  if (!panel || !form) return;
  const $ = (s) => panel.querySelector(s);
  const file = $('#hr-file'), choice = $('#hr-image'), status = $('#hr-status');
  const start = $('#hr-start'), review = $('#hr-review'), output = $('#hr-result');
  const undo = $('#hr-undo'), photo = $('#hr-photo-img');
  const labels = {title:'奖项全称', contest:'赛事 / 赛道', year:'获奖年份', level:'奖项级别', awardee:'公开团队署名', note:'公开说明'};
  let busy = false, image = null, serial = 0, changed = false, applied = [], mutations = new Map();
  panel.querySelector('.hr-controls').hidden = false;
  $('#hr-photo').addEventListener('toggle', e=>review.classList.toggle('has-photo',e.target.open));
  const noteChange = (field) => { mutations.set(field, (mutations.get(field) || 0) + 1); changed = true; };
  form.addEventListener('input', (e) => noteChange(e.target));
  form.addEventListener('change', (e) => noteChange(e.target));
  window.addEventListener('beforeunload', (e) => { if(changed || busy){e.preventDefault();e.returnValue='';} });
  form.addEventListener('submit', (e) => { if(busy){e.preventDefault();status.textContent='请等待本次识别完成后再保存；输入仍可编辑。';} else changed=false; });
  const request = async (url, body, timeoutMs=25000) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {method:body?'POST':'GET', body, credentials:'same-origin', signal:controller.signal,
        headers: body ? {'X-CSRFToken':form.elements.csrfmiddlewaretoken.value} : {}});
      if(response.redirected) throw new Error('登录已失效，请在新标签页重新登录，当前输入请勿关闭。');
      let data;
      try { data=await response.json(); } catch { throw new Error('服务未返回有效结果，请稍后重试。输入仍保留。'); }
      if(!response.ok) throw new Error(data.error || '请求未完成，请稍后重试。');
      return data;
    } finally { clearTimeout(timeout); }
  };
  const body = (values) => { const data=new FormData();Object.entries(values).forEach(([k,v])=>data.append(k,v));return data; };
  const setBusy = (value) => {busy=value;panel.classList.toggle('is-busy',value);start.disabled=value||panel.dataset.enabled!=='true';file.disabled=value;choice.disabled=value;};
  file.addEventListener('change',()=>{image=null;choice.value='';$('#hr-consent').checked=false;++serial;});
  choice.addEventListener('change',()=>{file.value='';image=choice.value ? {id:choice.value,url:choice.selectedOptions[0].dataset.url}:null;$('#hr-consent').checked=false;++serial;});
  const put = (field,value) => {
    applied.push({field, before:field.value, after:String(value), revision:mutations.get(field)||0});
    field.value=String(value);changed=true;undo.hidden=false;
    const details=field.closest('details');if(details)details.open=true;
  };
  const paragraph = (value, parent=output) => {const p=document.createElement('p');p.textContent=value;parent.append(p);return p;};
  const suggestion = (label,value,accept) => {
    const box=document.createElement('div');box.className='hr-suggestion';output.append(box);
    paragraph(`${label}：${value}`,box);
    const button=document.createElement('button');button.type='button';button.className='btn btn-outline';button.textContent='采用此建议';
    button.addEventListener('click',()=>{if(accept()){button.disabled=true;button.textContent='已填入，请核对';}});box.append(button);
  };
  const fillPeople = (people, baseline, requiresReview=false) => {
    const group=form.querySelector('[data-people-set]');
    const hasNames=Array.from(group.querySelectorAll('[name$="-name"]')).some(f=>f.value.trim());
    const altered=Array.from(group.querySelectorAll('input,select')).some(f=>(mutations.get(f)||0)!==(baseline.get(f)?.revision||0));
    const applyPeople=()=>{
      const names=new Set(Array.from(group.querySelectorAll('[name$="-name"]')).map(f=>f.value.trim()).filter(Boolean));
      for(const person of people){
        if(names.has(person.name)){paragraph(`已有署名 ${person.name}，未重复添加；如为同名不同人请手动核对。`);continue;}
        let row=Array.from(group.querySelectorAll('.ac-person')).find(r=>Array.from(r.querySelectorAll('input,select')).every(f=>f.type==='checkbox'?!f.checked:!f.value));
        if(!row){
          const before=Number(group.querySelector('[name="people-TOTAL_FORMS"]').value);
          group.querySelector('[data-add-person]').click();
          if(Number(group.querySelector('[name="people-TOTAL_FORMS"]').value)===before){paragraph('参与者已满20人，剩余姓名请手动核对。');break;}
          row=group.querySelector('[data-people-rows]').lastElementChild.querySelector('fieldset');
        }
        put(row.querySelector('[name$="-name"]'),person.name);
        if(person.role)put(row.querySelector('[name$="-role"]'),person.role);
        names.add(person.name);
      }
      return true;
    };
    if(!people.length)return;
    if(hasNames||altered||requiresReview)suggestion('参与者建议（不关联账号）',people.map(x=>x.name).join('、'),applyPeople);
    else {applyPeople();paragraph(`已填入${people.length}位参与者建议；姓名、身份和公开同意仍需本人核对。`);}
  };
  const show = (data, baseline) => {
    output.replaceChildren();applied=[];undo.hidden=true;review.hidden=false;
    photo.src=image.url;
    const result=data.result;
    const reviewFields=new Set(result.review_fields||[]);
    paragraph(result.notice);
    for(const [name,value] of Object.entries(result.fields||{})){
      if(!Object.hasOwn(labels,name))continue;
      const field=form.elements[name], before=baseline.get(field);
      if(!field||!before)continue;
      const formatted=name==='level'?({'30':'国家级','20':'省级','10':'校级','5':'其他'}[value]||value):value;
      if(!reviewFields.has(name)&&!before.value&&!field.value&&(mutations.get(field)||0)===before.revision){put(field,value);paragraph(`${labels[name]}：${formatted} · 已填入，待核对`);}
      else if(field.value!==String(value))suggestion(labels[name],formatted,()=>{if(field.value&&!window.confirm(`采用建议会替换“${labels[name]}”当前内容，确定吗？`))return false;put(field,value);return true;});
    }
    fillPeople(result.contributors||[],baseline,reviewFields.has('contributors'));
    (result.warnings||[]).forEach(w=>paragraph(w.replace(/^(title|contest|year|level|awardee)：/,(_,key)=>labels[key]+'：')));
    for(const match of data.matches||[]){
      const link=document.createElement('a');link.href=match.url;link.target='_blank';link.rel='noopener';link.textContent=`可能已有记录：${match.year} ${match.title}，查看或认领`;paragraph('').append(link);
    }
    status.textContent='识别完成。已填项仍需核对，尚未保存或公开。';
  };
  undo.addEventListener('click',()=>{
    let count=0;
    for(const item of [...applied].reverse()){
      if(item.field.value===item.after&&(mutations.get(item.field)||0)===item.revision){item.field.value=item.before;count++;}
    }
    applied=[];undo.hidden=true;changed=true;status.textContent=`已撤销${count}处自动填入。后续人工修改已保留。`;
  });
  start.addEventListener('click',async()=>{
    if(busy)return;
    if(!$('#hr-consent').checked){status.textContent='请先确认将这张图片发送给阿里云识别。';$('#hr-consent').focus();return;}
    if(!image&&!file.files[0]){status.textContent='请先选择证书图片。';file.focus();return;}
    const ticket=++serial;
    const baseline=new Map(Array.from(form.elements).map(f=>[f,{value:f.value,revision:mutations.get(f)||0}]));
    setBusy(true);
    try {
      if(!image){
        status.textContent='正在上传并自动缩放、压缩、摆正证书，不会公开图片…';
        const data=await request(panel.dataset.upload,body({upload:file.files[0],version:form.elements.version.value}),120000);
        image=data.image;
        const previousVersion=form.elements.version.value;
        document.querySelectorAll('input[name="version"]').forEach(input=>{if(input.value===previousVersion)input.value=data.version;});
        const option=new Option(image.label,image.id);option.dataset.url=image.url;choice.add(option);choice.value=image.id;
        form.elements.certificate.add(new Option(image.label,image.id));
        // Do not select the public certificate or modify the saved draft's content.
        file.value='';
      }
      status.textContent='已上传，等待 AI 整理。你可以继续编辑下方字段。';
      let data=await request(panel.dataset.start,body({image:image.id,consent:'on'}));
      const deadline=Date.now()+100000;
      while(['queued','running'].includes(data.status)){
        if(Date.now()>deadline)throw new Error('任务仍在等待或识别中，请稍后点击重试以查询同一任务。不会重复提交。');
        await new Promise(r=>setTimeout(r,1800));
        data=await request(data.status_url);
      }
      if(ticket!==serial)return;
      if(data.status!=='succeeded')throw new Error(data.error||'识别未完成，可重试或继续手动填写。');
      show(data,baseline);
    } catch(e){status.textContent=e.name==='AbortError'?'网络请求超时，请重试；图片和输入仍保留。':e.message;}
    finally {setBusy(false);}
  });
})();
