// Disposable database, mocked weather, real live controls. Never touches Render.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..');
async function freePort(){return new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const port=s.address().port;s.close(()=>resolve(port))})})}
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'festival-help-weather-')),port=await freePort(),base='http://127.0.0.1:'+port;
 const env={...process.env,FESTIVAL_DATA:data,PORT:String(port),HOST:'127.0.0.1'};delete env.FESTIVAL_TRANSLATION_API_KEY;delete env.FESTIVAL_KMA_API_KEY;
 const python=process.env.BROWSER_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 const server=spawn(python,[path.join(root,'server.py')],{cwd:root,env,stdio:['ignore','ignore','inherit']});let browser;
 try{
  let ready=false;for(let i=0;i<100;i++){try{if((await fetch(base+'/api/status')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,100))}assert(ready);
  async function call(route,body,token){const r=await fetch(base+route,{method:body?'POST':'GET',headers:{...(body?{'Content-Type':'application/json'}:{}),...(token?{Authorization:'Bearer '+token}:{})},body:body?JSON.stringify(body):undefined});assert.equal(r.status,200,await r.clone().text());return r.json()}
  const owner=await call('/api/setup',{email:'tour@example.test',name:'Tour operator',password:'tour-owner-password-2026'}),ep='/api/events/youth-expo/';
  await call(ep+'settings',{weather:{enabled:true,locations:[{name:'행사장','nx':60,'ny':127},{name:'야외','nx':61,'ny':127}]},survey_gate:'all',entry_gate:'all',reporting_enabled:true},owner.token);
  await call(ep+'survey-config',{title:'Tour survey',questions:[{id:'opinion',label:'테스트 의견',type:'text',required:false}],published:true,consent:'Fictional browser test only.'},owner.token);
  const draft=await call('/api/events',{name:'Private draft'},owner.token);
  await call('/api/events/'+draft.id+'/settings',{weather:{enabled:true,locations:[{name:'비공개 행사장','nx':60,'ny':127}]}},owner.token);
  const booth=await call(ep+'booth-access',{booth:'booth-1',password:'tour-booth-password'},owner.token);
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined),headless:true,args:['--no-sandbox']});
  const context=await browser.newContext({serviceWorkers:'block',viewport:{width:1440,height:1000}}),errors=[];
  await context.route(/https:\/\/(tile\.openstreetmap\.org|server\.arcgisonline\.com)\//,r=>r.abort());
  const page=await context.newPage();page.setDefaultTimeout(12000);page.on('pageerror',e=>errors.push(e.stack));
  await page.addInitScript(token=>sessionStorage.setItem('festival_management_token',token),owner.token);
  let requests=0,status='ok';
  await page.route('**/api/events/*/admin-weather?*',async r=>{
   requests++;if(status==='error')return r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Test weather unavailable'})});
   const u=new URL(r.request().url()),isDraft=u.pathname.includes(draft.id),index=Number(u.searchParams.get('location'));const stamp=new Date(await page.evaluate(()=>Date.now())).toISOString();
   return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status,source:'기상청 테스트 응답',locations:isDraft?[{name:'비공개 행사장'}]:[{name:'행사장'},{name:'야외'}],location:{name:isDraft?'비공개 행사장':index?'야외':'행사장'},observed_at:stamp,fetched_at:stamp,current:{temperature:isDraft?15:index?31:23.5,humidity:65,wind_speed:2.1,precipitation_1h:0,precipitation_type:0},forecast:[]})});
  });
  await page.clock.install();await page.goto(base+'/manage');await page.getByRole('heading',{name:'현장 운영 현황'}).waitFor();await page.locator('#event-switch').selectOption('youth-expo');await page.getByText('23.5°',{exact:true}).waitFor();
  await page.locator('#weather-location').selectOption('1');await page.getByText('31°',{exact:true}).waitFor();
  const before=requests;const refreshed=page.waitForResponse(r=>r.url().includes('/admin-weather?'));await page.clock.fastForward(61000);await refreshed;await page.waitForFunction(()=>document.querySelector('#weather-panel')?.textContent.includes('31°'));await page.waitForTimeout(100);assert(requests>before,'automatic weather refresh');
  status='stale';await page.getByRole('button',{name:'날씨 새로고침',exact:true}).click();await page.getByText('업데이트 지연 · 마지막 정상 관측값입니다.',{exact:false}).waitFor();
  status='error';await page.clock.fastForward(3601000);await page.getByText('Test weather unavailable',{exact:false}).waitFor();assert.equal(await page.getByText('31°',{exact:true}).count(),0,'old readings expire');
  status='ok';await page.locator('#event-switch').selectOption(draft.id);await page.getByText('15°',{exact:true}).waitFor();assert.equal(await page.getByText('31°',{exact:true}).count(),0,'other event data never reused');await page.locator('#event-switch').selectOption('youth-expo');await page.getByText('23.5°',{exact:true}).waitFor();
  async function tour(p,modal=false){
   const posts=[];const record=r=>{if(r.method()==='POST')posts.push(r.url())};p.on('request',record);
   const start=p.locator(modal?'#modal [data-help-start]':'#help-launcher');await start.waitFor();await start.click();await p.locator('.tour-layer').waitFor();
   assert.equal(await p.evaluate(()=>document.querySelector('#app').inert),true);
   await p.keyboard.press('Tab');assert(await p.evaluate(()=>document.activeElement.closest('.tour-panel')!==null),'keyboard focus stays inside tour');
   let count=0;while(await p.locator('.tour-layer').count()){
    assert(++count<150,'tour finishes');assert(!(await p.locator('.tour-panel').innerText()).includes('never-read-this-secret'),'field values never appear in tutorial');
    const panel=await p.locator('.tour-panel').boundingBox();const viewport=p.viewportSize();assert(panel.x>=0&&panel.y>=0&&panel.x+panel.width<=viewport.width+1&&panel.y+panel.height<=viewport.height+1,'tooltip fits viewport');
    await p.locator('.tour-next').click();
   }
   assert.equal(await p.evaluate(()=>document.querySelector('#app').inert),false);assert.deepEqual(posts,[],'tour never submits or mutates');p.off('request',record);return count;
  }
  for(const name of ['대시보드','공간·부스','콘텐츠·일정','미션·설문','추첨·지급','소통·대응','안전','보고서','행사 설정']){
   await page.getByRole('button',{name,exact:true}).click();assert(await tour(page)>0);console.log('PASS admin tour:',name);
  }
  await page.getByRole('button',{name:'연결 설정',exact:true}).click();await page.locator('#modal [data-help-start]').waitFor();await tour(page,true);await page.getByRole('button',{name:'닫기',exact:true}).click();
  await page.getByRole('button',{name:'공간·부스',exact:true}).click();await page.getByRole('button',{name:'존 추가',exact:true}).click();await page.getByLabel('존 이름',{exact:true}).fill('Do not submit this zone');await tour(page,true);assert.equal(await page.getByLabel('존 이름',{exact:true}).inputValue(),'Do not submit this zone');await page.getByRole('button',{name:'닫기',exact:true}).click();
  const participant=await context.newPage({viewport:{width:390,height:844}});await participant.setViewportSize({width:390,height:844});participant.setDefaultTimeout(12000);participant.on('pageerror',e=>errors.push(e.stack));
  await participant.goto(base+'/e/youth-expo');
  for(const name of ['홈','프로그램','미션','안전','내 참여']){await participant.getByRole('button',{name,exact:true}).click();await tour(participant);console.log('PASS participant tour:',name)}
  await participant.getByRole('button',{name:'홈',exact:true}).click();await participant.getByRole('button',{name:'지도·부스 찾기',exact:false}).click();await tour(participant);
  await participant.getByRole('button',{name:'프로그램',exact:true}).click();await participant.getByRole('button',{name:'상세 안내',exact:true}).first().click();await participant.locator('#modal [data-help-start]').waitFor();await tour(participant,true);await participant.getByRole('button',{name:'닫기',exact:true}).click();
  await participant.request.post(base+ep+'pass',{data:{}});await participant.reload();await participant.getByRole('button',{name:'홈',exact:true}).click();
  await participant.locator('[data-action="nav:survey"]').first().click();await participant.locator('[name=age_group]').waitFor();await tour(participant);
  await participant.getByRole('button',{name:'안전',exact:true}).click();await participant.getByRole('button',{name:'위험·도움 요청',exact:true}).click();await participant.locator('form[data-form=report]').waitFor();await tour(participant);
  for(const url of ['/register?event=youth-expo','/invite','/booth']){await participant.goto(base+url);await participant.locator('form').waitFor();await tour(participant);console.log('PASS standalone tour:',url)}
  await participant.getByLabel('공통 비밀번호',{exact:true}).fill('never-read-this-secret');await participant.locator('#help-launcher').click();assert(!await participant.locator('.tour-panel').innerText().then(t=>t.includes('never-read-this-secret')));await participant.keyboard.press('Escape');assert.equal(await participant.getByLabel('공통 비밀번호',{exact:true}).inputValue(),'never-read-this-secret');await participant.evaluate(()=>{const field=document.createElement('textarea');field.name='private_note';field.textContent='never-read-this-secret';document.querySelector('form').append(field)});await tour(participant);
  const staffSession=await call('/api/booth-login',{manager:booth.manager,password:'tour-booth-password',display:'Tour staff'});
  const staff=await context.newPage({viewport:{width:390,height:844}});await staff.setViewportSize({width:390,height:844});staff.setDefaultTimeout(12000);staff.on('pageerror',e=>errors.push(e.stack));await staff.addInitScript(token=>sessionStorage.setItem('festival_management_token',token),staffSession.token);await staff.goto(base+'/booth');await staff.locator('#staff-status').waitFor();
  for(const name of ['현황','부스 정보','QR','소통','종료 설문']){await staff.getByRole('button',{name,exact:true}).click();await tour(staff);console.log('PASS staff tour:',name)}
  await staff.getByRole('button',{name:'QR',exact:true}).click();await staff.getByRole('button',{name:'QR 보기·인쇄',exact:true}).click();await staff.locator('#modal [data-help-start]').waitFor();await tour(staff,true);await staff.getByRole('button',{name:'닫기',exact:true}).click();
  assert.equal(await staff.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await participant.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const dest=process.env.BROWSER_SCREENSHOT_DIR;if(dest){fs.mkdirSync(dest,{recursive:true});await page.getByRole('button',{name:'대시보드',exact:true}).click();await page.getByText('23.5°',{exact:true}).waitFor();await page.screenshot({path:path.join(dest,'dashboard-weather.png'),fullPage:true});await page.locator('#help-launcher').click();for(let step=0;step<80&&(await page.locator('#tour-title').innerText())!=='날씨 새로고침';step++)await page.locator('.tour-next').click();assert.equal(await page.locator('#tour-title').innerText(),'날씨 새로고침');await page.screenshot({path:path.join(dest,'dashboard-tutorial.png'),fullPage:true});await page.keyboard.press('Escape')}
  const offlineContext=await browser.newContext({viewport:{width:390,height:844}}),offline=await offlineContext.newPage();offline.on('pageerror',e=>errors.push(e.stack));
  await offline.goto(base+'/e/youth-expo');await offline.locator('nav[aria-label="참가자 메뉴"]').waitFor();await offline.waitForFunction(()=>!!navigator.serviceWorker.controller);await offline.reload();await offline.locator('nav[aria-label="참가자 메뉴"]').waitFor();
  assert(await offline.evaluate(async()=>!!await caches.match('/help-ui.js')),'tutorial module cached');await offlineContext.setOffline(true);await offline.reload();await offline.locator('nav[aria-label="참가자 메뉴"]').waitFor();await tour(offline);await offlineContext.close();
  assert.deepEqual(errors,[]);console.log('PASS: all menu tours, standalone forms, modal tours, keyboard, no writes, private field values, mobile fit, weather region/event/cache/refresh/failure.');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(resolve=>{if(server.exitCode!==null)return resolve();server.once('exit',resolve);setTimeout(resolve,3000)});fs.rmSync(data,{recursive:true,force:true})}
})().catch(error=>{console.error(error);process.exitCode=1});
