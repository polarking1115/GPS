// Real session expiry and editor retries against a disposable database.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..');
async function freePort(){return new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))})})}
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'gps-settings-session-')),port=await freePort(),base='http://127.0.0.1:'+port;
 const env={...process.env,FESTIVAL_DATA:data,PORT:String(port),HOST:'127.0.0.1'};delete env.FESTIVAL_TRANSLATION_API_KEY;delete env.FESTIVAL_KMA_API_KEY;
 const server=spawn(path.join(root,'.venv/bin/python'),['server.py'],{cwd:root,env,stdio:['ignore','ignore','inherit']});let browser;const uploads=new Set();
 try{
  for(let i=0;i<100;i++){try{if((await fetch(base+'/api/status')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
  const email='settings-session@example.test',password='settings-session-password-2026';
  const setup=await fetch(base+'/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password,name:'Editor'})});assert.equal(setup.status,200);const {token}=await setup.json();
  const publicData=async()=>{const r=await fetch(base+'/api/events/youth-expo');assert.equal(r.status,200);return r.json()};
  const initial=await publicData();browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const context=await browser.newContext({serviceWorkers:'block',viewport:{width:1440,height:1000}}),admin=await context.newPage(),visitor=await context.newPage(),errors=[];
  for(const p of [admin,visitor]){p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.stack))}
  await admin.addInitScript(token=>sessionStorage.setItem('festival_management_token',token),token);
  admin.on('response',async r=>{if(r.url().endsWith('/upload')&&r.ok())uploads.add((await r.json()).url)});
  await visitor.goto(base+'/e/youth-expo');await visitor.getByRole('heading',{name:initial.event.name,exact:true}).waitFor();
  await admin.goto(base+'/manage');await admin.getByRole('button',{name:'행사 설정',exact:true}).click();
  const settings=()=>admin.locator('form[data-form=settings]'),editor=()=>admin.locator('form[data-form=key-visual]');
  const open=async()=>{await admin.getByRole('button',{name:'키비주얼 설정·미리보기',exact:true}).click();await editor().waitFor()};
  const apply=()=>editor().getByRole('button',{name:'미리보기 확인 후 적용',exact:true}).click();
  const expire=async()=>{const token=await admin.evaluate(()=>sessionStorage.getItem('festival_management_token'));const r=await fetch(base+'/api/logout',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:'{}'});assert.equal(r.status,200)};
  const login=async()=>{const dialog=admin.getByRole('dialog',{name:'관리자 다시 로그인',exact:true});await dialog.waitFor();assert.equal(await dialog.getByLabel('로그인 이메일').inputValue(),email);await dialog.getByLabel('로그인 비밀번호').fill(password);await dialog.getByRole('button',{name:'로그인하고 계속'}).click();await dialog.waitFor({state:'hidden'})};
  await settings().getByLabel('행사명',{exact:true}).fill('제25회 시민 행사');await open();assert.equal(await editor().getByLabel('행사명 · 회차 포함').inputValue(),'제25회 시민 행사');
  await editor().getByLabel('슬로건·행사 소개').fill('누구나 함께 만드는 하루');await editor().getByLabel('행사 장소',{exact:true}).fill('시민 광장');
  assert.equal(await admin.locator('#kv-preview-stage .kv-copy h1').textContent(),'제25회 시민 행사');assert.equal((await publicData()).event.name,initial.event.name);
  await admin.getByRole('button',{name:'닫기',exact:true}).click();assert.equal(await settings().getByLabel('행사명',{exact:true}).inputValue(),'제25회 시민 행사');assert.equal((await publicData()).event.name,initial.event.name);
  await open();await editor().getByLabel('슬로건·행사 소개').fill('누구나 함께 만드는 하루');await editor().getByLabel('행사 장소',{exact:true}).fill('시민 광장');await editor().getByLabel('행사 시작일').fill('2026-11-05');await editor().getByLabel('행사 종료일').fill('2026-11-07');
  await admin.locator('#kv-background').setInputFiles(path.join(root,'public/assets/youth-hero.png'));await admin.getByText('새 이미지 선택됨 · 적용할 때 업로드됩니다.',{exact:true}).waitFor();
  await expire();await apply();let dialog=admin.getByRole('dialog',{name:'관리자 다시 로그인',exact:true});await dialog.waitFor();
  await dialog.getByLabel('로그인 비밀번호').fill('incorrect-password');await dialog.getByRole('button',{name:'로그인하고 계속'}).click();await dialog.locator('[role=alert]').filter({hasText:'비밀번호'}).waitFor();
  assert.equal(await editor().getByLabel('행사명 · 회차 포함').inputValue(),'제25회 시민 행사');assert.equal(await admin.locator('#kv-background').evaluate(el=>el.files.length),1);
  await admin.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});assert.equal(await editor().count(),1,'Canceling reauthentication must not close the editor');await admin.locator('#kv-save-state').getByText('저장하지 못했습니다.',{exact:false}).waitFor();assert.equal((await publicData()).event.name,initial.event.name);
  const out=process.env.BROWSER_TEST_OUTPUT;if(out){fs.mkdirSync(out,{recursive:true});await editor().getByLabel('행사명 · 회차 포함').scrollIntoViewIfNeeded();await admin.screenshot({path:path.join(out,'event-fields.png'),fullPage:true})}
  await apply();await login();await admin.locator('#modal').waitFor({state:'hidden'});assert.equal(uploads.size,1);
  const saved=(await publicData()).event;assert.equal(saved.name,'제25회 시민 행사');assert.equal(saved.description,'누구나 함께 만드는 하루');assert.equal(saved.venue,'시민 광장');assert.equal(saved.start,'2026-11-05');assert.equal(saved.end,'2026-11-07');
  assert.equal(await admin.locator('#event-switch option:checked').textContent(),saved.name);await visitor.bringToFront();await visitor.getByRole('heading',{name:saved.name,exact:true}).waitFor({timeout:2500});
  // Ordinary settings also resume after reauthentication and refresh the selector/tab.
  await admin.bringToFront();await settings().getByLabel('행사명',{exact:true}).fill('제26회 열린 행사');await expire();await settings().getByRole('button',{name:'저장',exact:true}).click();await login();await admin.getByText('저장한 설정을 적용했습니다.',{exact:true}).waitFor();assert.equal(await admin.locator('#event-switch option:checked').textContent(),'제26회 열린 행사');await visitor.bringToFront();await visitor.getByRole('heading',{name:'제26회 열린 행사',exact:true}).waitFor({timeout:2500});
  // Validation errors remain in the editor, and retry reuses a successful upload.
  await admin.bringToFront();await open();await editor().getByLabel('행사 시작일').fill('2026-11-08');await apply();await admin.locator('#kv-save-state').getByText('행사 종료일은 시작일 이후여야 합니다.',{exact:true}).waitFor();assert.equal((await publicData()).event.start,'2026-11-05');await editor().getByLabel('행사 시작일').fill('2026-11-05');
  await admin.locator('#kv-background').setInputFiles(path.join(root,'public/assets/youth-hero.png'));await admin.getByText('새 이미지 선택됨 · 적용할 때 업로드됩니다.',{exact:true}).waitFor();let failures=1;
  await admin.route('**/api/events/youth-expo/settings',route=>failures-- >0?route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'공개 필수 항목을 확인하세요: 행사 장소'})}):route.continue());
  await apply();await admin.locator('#kv-save-state').getByText('공개 필수 항목을 확인하세요: 행사 장소',{exact:false}).waitFor();assert.equal(uploads.size,2);await apply();await admin.locator('#modal').waitFor({state:'hidden'});assert.equal(uploads.size,2,'retry must not upload the same selected image twice');
  await admin.unroute('**/api/events/youth-expo/settings');await admin.setViewportSize({width:390,height:844});await open();assert.equal(await admin.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await editor().getByLabel('행사명 · 회차 포함').fill('모바일 편집 중');await expire();await apply();dialog=admin.getByRole('dialog',{name:'관리자 다시 로그인',exact:true});await dialog.waitFor();assert.equal(await admin.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);if(out)await admin.screenshot({path:path.join(out,'reauth-preserves-editor.png'),fullPage:true});await dialog.getByRole('button',{name:'편집으로 돌아가기'}).click();await dialog.waitFor({state:'hidden'});assert.equal(await editor().getByLabel('행사명 · 회차 포함').inputValue(),'모바일 편집 중');
  assert.deepEqual(errors,[]);console.log('PASS: inline event fields, live preview, cancel, expired-session login/retry/cancel, selected-file retention, saved selector/tab refresh, durable errors, upload reuse and mobile layout.');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>{if(server.exitCode!==null)return r();server.once('exit',r);setTimeout(r,3000)});fs.rmSync(data,{recursive:true,force:true});for(const file of uploads)fs.rmSync(path.join(root,'public',file.slice(1)),{force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
