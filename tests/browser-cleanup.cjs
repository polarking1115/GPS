// Regression scenarios from the full workflow audit. Uses only a disposable database.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const port=()=>new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))})});
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'festival-cleanup-')),base='http://127.0.0.1:'+await port();
 const env={...process.env,FESTIVAL_DATA:data,HOST:'127.0.0.1',PORT:new URL(base).port};delete env.FESTIVAL_TRANSLATION_API_KEY;delete env.FESTIVAL_KMA_API_KEY;
 const server=spawn(process.env.BROWSER_PYTHON||path.join(root,'.venv/bin/python'),['server.py'],{cwd:root,env,stdio:['ignore','ignore','inherit']});let browser;
 try{
  for(let i=0;i<100;i++){try{if((await fetch(base+'/api/status')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
  const setup=await fetch(base+'/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'cleanup@example.test',name:'Cleanup owner',password:'cleanup-owner-test-password'})});assert.equal(setup.status,200);const {token}=await setup.json();
  const call=async(url,body)=>{const r=await fetch(base+url,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert.equal(r.status,200,await r.clone().text());return r.json()};
  const ep='/api/events/youth-expo/';
  const quiz=await call(ep+'mission',{title:'첫 참여 퀴즈',kind:'quiz',question:'정답은 A',answer:'A',published:true});
  const second=await call('/api/events',{name:'지역 전시회',venue:'테스트 전시장',start:'2026-11-04',end:'2026-11-05'});
  const sep='/api/events/'+second.id+'/';await call(sep+'settings',{status:'active'});
  const copied=await call('/api/events',{name:'복제 행사',copy:'youth-expo'});
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const errors=[];
  const makePage=async(viewport={width:1440,height:1000})=>{const context=await browser.newContext({viewport,serviceWorkers:'block'}),page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.stack));page.on('dialog',d=>d.accept());return page};
  const visitor=await makePage({width:390,height:844});
  await visitor.goto(base+'/e/youth-expo');await visitor.getByRole('button',{name:'미션',exact:true}).click();
  await visitor.locator('.card').filter({hasText:'첫 참여 퀴즈'}).getByRole('button',{name:'수행 조건 보기'}).click();
  await visitor.getByRole('button',{name:'확인하고 계속'}).click();await visitor.getByLabel('정답',{exact:true}).fill('A');await visitor.getByRole('button',{name:'정답 확인',exact:true}).click();await visitor.getByText('미션 완료!',{exact:true}).waitFor();
  const before=await (await visitor.request.get(base+ep+'pass')).json();assert(before.missions.find(m=>m.id===quiz.id).completed);
  const other=await visitor.request.post(base+sep+'pass',{data:{}});assert.equal(other.status(),200);assert.notEqual((await other.json()).participant.id,before.participant.id);
  assert.equal((await (await visitor.request.get(base+ep+'pass')).json()).participant.id,before.participant.id);
  await visitor.getByRole('button',{name:'안전',exact:true}).click();assert.equal(await visitor.locator('[data-action^="report:"]').count(),0);
  // Unpublished surveys do not create an unnecessary pass/consent dialog.
  const fresh=await makePage({width:390,height:844});await fresh.goto(base+'/e/youth-expo');await fresh.locator('[data-action="nav:survey"]').click();await fresh.getByText('아직 공개된 설문이 없습니다.',{exact:true}).waitFor();assert.equal(await fresh.locator('[data-action=ack-pass]').count(),0);
  const admin=await makePage();await admin.addInitScript(token=>sessionStorage.setItem('festival_management_token',token),token);await admin.goto(base+'/manage');await admin.locator('#event-switch').selectOption(second.id);await admin.getByRole('button',{name:'행사 설정',exact:true}).click();
  for(const name of ['프로그램 안내 사용','미션 사용','설문 접수 사용'])await admin.getByLabel(name,{exact:true}).uncheck();
  await admin.locator('form[data-form=settings]').getByRole('button',{name:'저장',exact:true}).click();await admin.getByText('저장했습니다.',{exact:true}).waitFor();
  await visitor.goto(base+'/e/'+second.id);await visitor.getByRole('heading',{name:'지역 전시회',exact:true}).waitFor();
  assert.deepEqual(await visitor.locator('nav button').allTextContents(),['홈','안전','내 참여']);assert.equal(await visitor.locator('.kv-art').count(),0);assert.equal(await visitor.locator('[data-action="nav:survey"]').count(),0);assert(!(await visitor.locator('main').innerText()).includes('박람회'));
  await visitor.getByRole('button',{name:'내 참여',exact:true}).click();assert.equal(await visitor.getByText('완료 미션',{exact:true}).count(),0);
  await admin.locator('#event-switch').selectOption(copied.id);await admin.getByRole('button',{name:'미션·설문',exact:true}).click();await admin.getByRole('button',{name:'미션 공개',exact:true}).first().click();await admin.getByRole('button',{name:'공개 중지',exact:true}).waitFor();
  await admin.locator('#event-switch').selectOption('youth-expo');await admin.getByRole('button',{name:'보고서',exact:true}).click();await admin.getByRole('button',{name:'분석 새로 불러오기'}).click();await admin.getByRole('heading',{name:'전체 설문 집계'}).waitFor();
  await admin.locator('#event-switch').selectOption(second.id);await admin.getByRole('button',{name:'보고서',exact:true}).click();assert.equal(await admin.getByRole('heading',{name:'전체 설문 집계'}).count(),0);
  const access=await call(ep+'booth-access',{booth:'booth-1',password:'cleanup-booth-password'});
  const staff=await makePage({width:390,height:844});await staff.goto(base+'/bm/'+access.manager);await staff.getByLabel('공통 비밀번호',{exact:true}).fill('cleanup-booth-password');await staff.getByLabel('이번 접속 담당자 표시명').fill('검토 담당');await staff.getByRole('button',{name:'부스 관리 시작'}).click();await staff.getByRole('button',{name:'종료 설문',exact:true}).click();
  await staff.getByLabel('운송·이동 교통수단').fill('도보');await staff.getByLabel('왕복 이동 거리(km)').fill('0');await staff.getByLabel('지역 식비(원)').fill('15000');await staff.getByRole('button',{name:'실적 제출'}).click();await staff.getByText('저장했습니다.',{exact:true}).waitFor();await staff.reload();await staff.getByRole('button',{name:'종료 설문',exact:true}).click();assert.equal(await staff.getByLabel('지역 식비(원)').inputValue(),'15000');assert.equal(await staff.getByLabel('왕복 이동 거리(km)').inputValue(),'0');
  const invite=await call(sep+'invite',{email:'analysis-ui@example.test',role:'analyst'});await call('/api/accept-invite',{invite:invite.invite,name:'분석 담당',password:'analysis-ui-test-password'});
  const session=await call('/api/login',{email:'analysis-ui@example.test',password:'analysis-ui-test-password'});
  const analyst=await makePage();await analyst.addInitScript(token=>sessionStorage.setItem('festival_management_token',token),session.token);await analyst.goto(base+'/manage');await analyst.getByRole('heading',{name:'현장 운영 현황'}).waitFor();assert.equal(await analyst.getByRole('button',{name:'행사 설정',exact:true}).count(),0);assert.equal(await analyst.getByRole('button',{name:'새 행사 개설',exact:true}).count(),0);assert.equal(await analyst.locator('[data-action^="edit-booth:"]').count(),0);
  await admin.getByRole('button',{name:'행사 설정',exact:true}).click();await admin.getByRole('button',{name:'행사 담당자·권한 관리'}).click();await admin.getByRole('button',{name:'이 행사 권한 회수'}).click();await admin.getByText('초대 수락한 행사 담당자가 없습니다.',{exact:true}).waitFor();await analyst.reload();await analyst.getByRole('button',{name:'로그인',exact:true}).waitFor();
  for(const page of [visitor,staff])assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);console.log('PASS: first quiz pass, multi-event records, disabled modules/reports, unpublished survey, neutral theme, copied mission publication, report reset, staff answer reload, role controls and revocation.');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>{if(server.exitCode!==null)return r();server.once('exit',r);setTimeout(r,3000)});fs.rmSync(data,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
