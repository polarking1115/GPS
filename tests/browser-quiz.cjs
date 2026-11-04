// Nine question formats, media authoring, all delivery modes and both team routes.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const port=()=>new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))})});
const choice=(id='q1',extra={})=>({id,type:'single',prompt:'정답을 고르세요',choices:[{id:'a',label:'정답 보기'},{id:'b',label:'다른 보기'}],answers:['a'],...extra});
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'festival-quiz-browser-')),base='http://127.0.0.1:'+await port(),uploads=new Set();
 const env={...process.env,FESTIVAL_DATA:path.join(temp,'data'),HOST:'127.0.0.1',PORT:new URL(base).port};delete env.FESTIVAL_TRANSLATION_API_KEY;delete env.FESTIVAL_KMA_API_KEY;
 const server=spawn(process.env.BROWSER_PYTHON||path.join(root,'.venv/bin/python'),['server.py'],{cwd:root,env,stdio:['ignore','ignore','inherit']});let browser;
 try{
  for(let i=0;i<100;i++){try{if((await fetch(base+'/api/status')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
  const setup=await fetch(base+'/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'quiz-ui@example.test',name:'Quiz UI owner',password:'quiz-ui-owner-test-password'})});assert.equal(setup.status,200);const {token}=await setup.json(),ep='/api/events/youth-expo/';
  const call=async(route,body)=>{const r=await fetch(base+ep+route,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert.equal(r.status,200,await r.clone().text());return r.json()};
  const questions=[
   {id:'ox',type:'ox',prompt:'OX 문제',answers:['o'],hint:'O를 선택하세요',explanation:'OX 해설'},
   choice('single',{prompt:'하나 선택 문제'}),choice('multi',{type:'multi',prompt:'여러 선택 문제',answers:['a','b']}),
   {id:'short',type:'short',prompt:'단답 문제',answers:['CODE']},
   {id:'blank',type:'blank',prompt:'빈칸 문제',blanks:[{id:'blank1',label:'바다를 뜻하는 말',answers:['해양']}]},
   {id:'match',type:'match',prompt:'짝 문제',pairs:[{id:'apple',left:'사과',right:'과일'},{id:'rose',left:'장미',right:'꽃'}]},
   {id:'order',type:'order',prompt:'순서 문제',items:[{id:'finish',label:'마무리'},{id:'prepare',label:'준비'}],order:['prepare','finish']},
   choice('scenario',{type:'scenario',prompt:'상황 선택 문제'}),
   choice('hotspot',{type:'hotspot',prompt:'사진 위치 문제',choices:[{id:'a',label:'왼쪽 구역'},{id:'b',label:'오른쪽 구역'}],media:{kind:'image',url:'/assets/youth-hero.png',caption:'왼쪽과 오른쪽으로 나뉜 그림'},regions:{a:{x:0,y:0,width:50,height:100},b:{x:50,y:0,width:50,height:100}}})];
  const all=await call('mission',{title:'9가지 문항 체험',kind:'quiz',published:false,config:{version:2,mode:'pack',pass_count:9,questions}});
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});const errors=[];
  const page=async(viewport={width:1440,height:1000})=>{const p=await browser.newPage({viewport,serviceWorkers:'block'});p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.stack));p.on('dialog',d=>d.accept());return p};
  const admin=await page();await admin.addInitScript(token=>sessionStorage.setItem('festival_management_token',token),token);
  admin.on('response',async response=>{if(/\/(upload|quiz-media)$/.test(new URL(response.url()).pathname)&&response.status()===200){const data=await response.json();uploads.add(data.url)}});
  await admin.goto(base+'/manage');await admin.getByRole('button',{name:'미션·설문',exact:true}).click();await admin.locator('[data-action="edit-mission:'+all.id+'"]').click();
  await admin.locator('.quiz-editor-question').nth(8).waitFor({state:'attached'});assert.equal(await admin.locator('.quiz-editor-question').count(),9);
  assert.deepEqual(await admin.locator('[data-qkey=type]').evaluateAll(nodes=>nodes.map(n=>n.value)),['ox','single','multi','short','blank','match','order','scenario','hotspot']);
  await admin.getByLabel('필요 정답 개수',{exact:true}).fill('9');
  const short=admin.locator('[data-question-id=short]');await short.getByLabel('문제·질문',{exact:true}).fill('단답 문제 · 수정됨');
  const order=admin.locator('[data-question-id=order]');assert.equal(await order.getByLabel('1번째 항목').inputValue(),'준비');
  await admin.getByRole('button',{name:'참가자 문항 미리보기'}).click();await admin.locator('#quiz-preview .quiz-question').nth(8).waitFor({state:'attached'});assert.equal(await admin.locator('#quiz-preview .quiz-question').count(),9);await admin.getByRole('button',{name:'참가자 문항 미리보기'}).click();
  await admin.getByRole('button',{name:'변경 저장',exact:true}).click();await admin.locator('#modal').waitFor({state:'hidden'});
  await admin.locator('[data-action="mission-publication:'+all.id+'"]').click();await admin.locator('[data-action="mission-publication:'+all.id+'"]').filter({hasText:'공개 중지'}).waitFor();
  const visitor=await page({width:390,height:844});
  const open=async(p,id)=>{await p.goto(base+'/e/youth-expo');await p.getByRole('button',{name:'미션',exact:true}).click();await p.locator('[data-action="mission:'+id+'"]').click();const notice=p.locator('[data-action=ack-pass]');await p.locator('#modal').waitFor({state:'visible'});if(await notice.count())await notice.click();await p.locator('[data-action=quiz-start], form[data-form=quiz-submit], form[data-form=quiz-team-create], [data-action=quiz-team-random]').first().waitFor()};
  await open(visitor,all.id);await visitor.getByRole('button',{name:'미션 시작',exact:true}).click();await visitor.locator('[data-quiz-q=ox]').getByText('힌트 보기',{exact:true}).click();
  await visitor.locator('[data-quiz-q=ox]').getByLabel('O',{exact:true}).check();await visitor.locator('[data-quiz-q=single]').getByLabel('정답 보기',{exact:true}).check();
  await visitor.locator('[data-quiz-q=multi]').getByLabel('정답 보기',{exact:true}).check();await visitor.locator('[data-quiz-q=multi]').getByLabel('다른 보기',{exact:true}).check();
  await visitor.locator('[data-quiz-q=short]').getByLabel('정답',{exact:true}).fill('code');await visitor.getByLabel('바다를 뜻하는 말',{exact:true}).fill('해양');
  await visitor.locator('[data-quiz-q=match]').getByLabel('사과',{exact:true}).selectOption({label:'과일'});await visitor.locator('[data-quiz-q=match]').getByLabel('장미',{exact:true}).selectOption({label:'꽃'});
  await visitor.locator('[data-quiz-sort=order] .quiz-sort-row').filter({hasText:'준비'}).getByRole('button',{name:'위로',exact:true}).click();
  await visitor.locator('[data-quiz-q=scenario]').getByLabel('정답 보기',{exact:true}).check();const photo=visitor.locator('[data-quiz-point=hotspot]');await photo.scrollIntoViewIfNeeded();const box=await photo.boundingBox();await photo.click({position:{x:box.width*.25,y:box.height*.5}});
  await visitor.getByRole('button',{name:'답안 제출',exact:true}).click();await visitor.getByText('미션 완료!',{exact:false}).waitFor();await visitor.getByText('OX 해설',{exact:true}).waitFor();assert.equal(await visitor.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  // Author a new quiz and exercise all supported media uploads with actual files.
  const wav=Buffer.alloc(44+4800);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(4800,40);fs.writeFileSync(path.join(temp,'tone.wav'),wav);
  // A tiny generated blue video fixture keeps this suite independent of FFmpeg.
  fs.writeFileSync(path.join(temp,'clip.webm'),Buffer.from('GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQJChYECGFOAZwEAAAAAAALAEU2bdLpNu4tTq4QVSalmU6yBoU27i1OrhBZUrmtTrIHWTbuMU6uEElTDZ1OsggEjTbuMU6uEHFO7a1OsggKq7AEAAAAAAABZAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVSalmsCrXsYMPQkBNgIxMYXZmNjEuNy4xMDNXQYxMYXZmNjEuNy4xMDNEiYhAdAAAAAAAABZUrmvIrgEAAAAAAAA/14EBc8WIY9idCGZMQvecgQAitZyDdW5kiIEAhoVWX1ZQOIOBASPjg4QCYloA4JCwgXi6gVCagQJVsIRVuYEBElTDZ/tzc59jwIBnyJlFo4dFTkNPREVSRIeMTGF2ZjYxLjcuMTAzc3PWY8CLY8WIY9idCGZMQvdnyKFFo4dFTkNPREVSRIeUTGF2YzYxLjE5LjEwMSBsaWJ2cHhnyKFFo4hEVVJBVElPTkSHkzAwOjAwOjAwLjMyMDAwMDAwMAAfQ7Z1QQHngQCjzYEAAIDQBACdASp4AFAAAEcIhYWIhYSIAgICdaoD+AIGpxka6m9xF5YBrqb3EXlgGupvbQD+/00S//xYV/FhX8WFf/FhX/z8zu3F/OYAo5eBACgA8QEABRCsABgAGFgv9AAIgaaAAKOXgQBQAPEBAAUQrAAYABhYL/QACIGmgACjl4EAeADxAQAFEKwAGAAYWC/0AAiBpoAAo5eBAKAA8QEABRCsABgAGFgv9AAIgaaAAKOXgQDIAPEBAAUQrAAYABhYL/QACIGmgACjl4EA8ADxAQAFEKwAGAAYWC/0AAiBpoAAo5eBARgA8QEABRAQFGAAYWC/0AAiBpoAABxTu2uRu4+zgQC3iveBAfGCAaPwgQM=','base64'));
  await admin.getByRole('button',{name:'미션 추가',exact:true}).click();await admin.getByLabel('미션명',{exact:true}).fill('자료 포함 퀴즈');await admin.getByLabel('완료 조건',{exact:true}).selectOption('quiz');
  for(const [index,kind,file] of [[0,'image',path.join(root,'public/assets/youth-hero.png')],[1,'audio',path.join(temp,'tone.wav')],[2,'video',path.join(temp,'clip.webm')],[3,'observation',null]]){
   if(index)await admin.getByRole('button',{name:'문항 추가',exact:true}).click();const q=admin.locator('.quiz-editor-question').last();await q.getByLabel('문제·질문',{exact:true}).fill('자료 문제 '+index);await q.getByLabel('문제 자료',{exact:true}).selectOption(kind);await q.getByLabel(kind==='observation'?'현장 관찰 안내':'자료 설명 · 음성·영상은 대체 설명',{exact:true}).fill('자료 설명 '+index);
   if(file){const response=admin.waitForResponse(r=>/\/(upload|quiz-media)$/.test(new URL(r.url()).pathname)&&r.status()===200);await q.locator('input[type=file]').setInputFiles(file);await response;await q.getByText('등록한 자료',{exact:true}).waitFor()}
  }
  await admin.getByLabel('지금 공개 · 달성 조건 잠금',{exact:true}).check();await admin.getByRole('button',{name:'등록',exact:true}).click();await admin.locator('#modal').waitFor({state:'hidden'});
  const mediaMission=(await call('admin')).missions.find(m=>m.title==='자료 포함 퀴즈');await open(visitor,mediaMission.id);await visitor.getByRole('button',{name:'미션 시작',exact:true}).click();
  await visitor.locator('audio').evaluate(el=>el.load());await visitor.waitForFunction(()=>document.querySelector('audio')?.readyState>=1);await visitor.waitForFunction(()=>document.querySelector('video')?.readyState>=1);assert.equal(await visitor.locator('audio').count(),1);assert.equal(await visitor.locator('video').count(),1);await visitor.getByText('자료 설명 3',{exact:true}).waitFor();
  for(const radio of await visitor.locator('[data-quiz-q] input[type=radio][value=o]').all())await radio.check();await visitor.getByRole('button',{name:'답안 제출',exact:true}).click();await visitor.getByText('미션 완료!',{exact:false}).waitFor();
  // Staged, random, branching, single and survey flows use the same saved editor schema.
  for(const mode of ['single','staged','random','branch']){
   const questions=mode==='single'?[choice()]:[choice('q1',mode==='branch'?{branches:{b:'end'}}:{}),choice('q2')];
   const m=await call('mission',{title:'진행 '+mode,kind:'quiz',config:{version:2,mode,questions,pass_count:1,random_count:1}});await open(visitor,m.id);await visitor.getByRole('button',{name:'미션 시작',exact:true}).click();
   if(mode==='branch'){await visitor.getByLabel('다른 보기',{exact:true}).check();await visitor.getByRole('button',{name:'답안 제출',exact:true}).click();await visitor.getByRole('button',{name:'처음부터 다시 풀기',exact:true}).click()}
   await visitor.locator('.quiz-question').last().getByLabel('정답 보기',{exact:true}).check();await visitor.getByRole('button',{name:'답안 제출',exact:true}).click();
   if(['staged','branch'].includes(mode)){await visitor.locator('[data-quiz-q=q2]').getByLabel('정답 보기',{exact:true}).check();await visitor.getByRole('button',{name:'답안 제출',exact:true}).click()}
   await visitor.getByText('미션 완료!',{exact:false}).waitFor();
  }
  await admin.getByRole('button',{name:'미션 추가',exact:true}).click();await admin.getByLabel('미션명',{exact:true}).fill('체험 후 설문');await admin.getByLabel('완료 조건',{exact:true}).selectOption('survey');await admin.getByLabel('문제·질문',{exact:true}).fill('체험은 어땠나요?');await admin.getByLabel('문항 유형',{exact:true}).selectOption('rating');await admin.getByLabel('지금 공개 · 달성 조건 잠금',{exact:true}).check();await admin.getByRole('button',{name:'등록',exact:true}).click();await admin.locator('#modal').waitFor({state:'hidden'});
  const survey=(await call('admin')).missions.find(m=>m.title==='체험 후 설문');await open(visitor,survey.id);await visitor.getByRole('button',{name:'미션 시작',exact:true}).click();await visitor.getByLabel('평가 점수',{exact:true}).selectOption('4');await visitor.getByRole('button',{name:'응답 제출',exact:true}).click();await visitor.getByText('미션 완료!',{exact:false}).waitFor();
  await admin.locator('[data-action="mission-results:'+survey.id+'"]').click();await admin.getByText('평균 4 · 합계 4',{exact:true}).waitFor();await admin.getByRole('button',{name:'닫기',exact:true}).click();
  const team=await call('mission',{title:'함께 푸는 퀴즈',kind:'quiz',config:{version:2,mode:'team',team_assignment:'both',team_size:2,pass_count:2,questions:[choice('q1'),choice('q2')]}});
  const teammate=await page({width:390,height:844});await open(visitor,team.id);await visitor.getByLabel('팀 이름',{exact:true}).fill('함께 팀');await visitor.getByRole('button',{name:'팀 만들기',exact:true}).click();await visitor.getByRole('button',{name:'미션 시작',exact:true}).waitFor();const code=await visitor.locator('#modal .card strong').first().innerText();
  await open(teammate,team.id);await teammate.getByLabel('팀 참여 코드',{exact:true}).fill(code);await teammate.getByRole('button',{name:'코드로 합류',exact:true}).click();await teammate.getByRole('button',{name:'미션 시작',exact:true}).click();await visitor.getByRole('button',{name:'팀 현황 갱신',exact:true}).click();
  // Separate team members submit different answers into one shared run.
  await visitor.locator('[data-quiz-q=q1]').getByLabel('정답 보기',{exact:true}).check();await visitor.getByRole('button',{name:'답안 제출',exact:true}).click();await visitor.locator('[data-quiz-q=q1] .tag').filter({hasText:'정답'}).waitFor();await teammate.getByRole('button',{name:'팀 현황 갱신',exact:true}).click();await teammate.locator('[data-quiz-q=q2]').getByLabel('정답 보기',{exact:true}).check();await teammate.getByRole('button',{name:'답안 제출',exact:true}).click();await teammate.getByText('미션 완료!',{exact:false}).waitFor();await visitor.getByRole('button',{name:'팀 현황 갱신',exact:true}).click();await visitor.getByText('미션 완료!',{exact:false}).waitFor();
  const randomA=await page({width:390,height:844}),randomB=await page({width:390,height:844});await open(randomA,team.id);await randomA.getByRole('button',{name:'랜덤 팀 참여',exact:true}).click();await randomA.getByRole('button',{name:'미션 시작',exact:true}).waitFor();await open(randomB,team.id);await randomB.getByRole('button',{name:'랜덤 팀 참여',exact:true}).click();await randomB.getByRole('button',{name:'미션 시작',exact:true}).waitFor();assert.equal(await randomA.locator('#modal .card h3').innerText(),await randomB.locator('#modal .card h3').innerText());
  if(process.env.BROWSER_SCREENSHOT_DIR){fs.mkdirSync(process.env.BROWSER_SCREENSHOT_DIR,{recursive:true});await randomB.screenshot({path:path.join(process.env.BROWSER_SCREENSHOT_DIR,'random-team.png'),fullPage:true});await admin.locator('[data-action="edit-mission:'+all.id+'"]').click();await admin.locator('.quiz-editor-question').first().scrollIntoViewIfNeeded();await admin.screenshot({path:path.join(process.env.BROWSER_SCREENSHOT_DIR,'quiz-authoring.png'),fullPage:true})}
  assert.deepEqual(errors,[]);console.log('PASS: nine quiz formats/editor/preview, image/audio/video/observation uploads, single/pack/staged/random/branch/team, survey editor/report, code teams and random teams, mobile fit.');
 }catch(error){if(browser&&process.env.BROWSER_SCREENSHOT_DIR){fs.mkdirSync(process.env.BROWSER_SCREENSHOT_DIR,{recursive:true});let i=0;for(const context of browser.contexts())for(const p of context.pages())await p.screenshot({path:path.join(process.env.BROWSER_SCREENSHOT_DIR,'failure-'+i+++'.png'),fullPage:true}).catch(()=>{})}throw error}
 finally{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>{if(server.exitCode!==null)return r();server.once('exit',r);setTimeout(r,3000)});fs.rmSync(temp,{recursive:true,force:true});for(const file of uploads)fs.rmSync(path.join(root,'public',file.replace(/^\//,'')),{force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
