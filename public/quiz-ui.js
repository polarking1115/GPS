/* Rich mission authoring and participant delivery. Answer keys never enter the participant editor. */
window.QuizUI=(()=>{
 const types={ox:'OX',single:'객관식 · 하나 선택',multi:'객관식 · 여러 개 선택',short:'단답형',blank:'빈칸 완성',match:'짝 맞추기',order:'순서 배열',scenario:'상황 선택',hotspot:'사진 속 위치',text:'주관식',rating:'만족도·평가',number:'숫자 응답'};
 const modes={single:'한 문제',pack:'문제 묶음',staged:'단계별 공개',random:'무작위 출제',branch:'답변에 따른 분기',team:'팀 협력'};
 const id=()=>crypto.randomUUID().replaceAll('-','');
 let draft=null,current=null,drag=null;
 const item=(label='')=>({id:id(),label});
 const question=(type='ox')=>({id:id(),type,prompt:'',required:true,hint:'',explanation:'',media:{kind:'none',url:'',caption:''},choices:type==='ox'?[{id:'o',label:'O'},{id:'x',label:'X'}]:[item('보기 1'),item('보기 2')],answers:type==='ox'?['o']:[],blanks:[{id:id(),label:'빈칸 1',answers:[]}],pairs:[{id:id(),left:'',right:''},{id:id(),left:'',right:''}],items:[item('첫 번째'),item('두 번째')],branches:{},regions:{},min:type==='rating'?1:0,max:type==='rating'?5:100});
 const input=(qid,key,label,value='',type='text',extra='')=>`<label for="qe-${qid}-${key}">${esc(label)}</label><input id="qe-${qid}-${key}" type="${type}" data-qq="${qid}" data-qkey="${key}" value="${esc(value)}" ${extra}>`;
 const textarea=(qid,key,label,value='')=>`<label for="qe-${qid}-${key}">${esc(label)}</label><textarea id="qe-${qid}-${key}" data-qq="${qid}" data-qkey="${key}">${esc(value)}</textarea>`;
 const sel=(qid,key,label,values,value)=>`<label for="qe-${qid}-${key}">${esc(label)}</label><select id="qe-${qid}-${key}" data-qq="${qid}" data-qkey="${key}">${options(values,value)}</select>`;
 const allowed=()=>draft.survey?['single','multi','text','rating','number']:Object.keys(types).filter(k=>!['text','rating','number'].includes(k));
 function editor(m){
  if(m.locked&&m.config?.version!==2){draft=null;return field('question','퀴즈 질문',m.config?.question||'')+field('answer','퀴즈 정답 · 참가자에게 비공개',m.config?.answer||'')}
  const c=m.config?.version===2?structuredClone(m.config):{version:2,mode:'pack',completion:m.kind==='survey'?'submit':'score',pass_count:1,random_count:1,max_attempts:0,hints:true,feedback:'after_submit',team_assignment:'both',team_size:4,questions:[question(m.kind==='survey'?'single':'ox')]};
  if(m.config?.question){c.questions=[{...question('short'),prompt:m.config.question,answers:[m.config.answer]}]}
  for(const q of c.questions)if(q.type==='order'&&q.order)q.items=q.order.map(id=>q.items.find(item=>item.id===id));
  draft={config:c,survey:m.kind==='survey',locked:!!m.locked};return `<div id="quiz-builder">${builder()}</div>`;
 }
 function builder(){const c=draft.config;return `<div class="notice info">${draft.survey?'정답 없이 필수 응답을 마치면 완료되는 미션입니다. 행사 전체 설문과 별도로 집계합니다.':'문항 유형과 진행 방식을 조합하세요. 공개 후 문항·정답·완료 기준은 잠깁니다.'}</div>${sel('','mode','진행 방식',Object.entries(modes).filter(([k])=>!draft.survey||k!=='team'),c.mode)}${c.mode==='random'?input('','random_count','출제 문항 수',c.random_count,'number','min="1"'):''}${!draft.survey?`${sel('','completion','완료 기준',[['score','필수 응답 + 정답 개수 달성'],['submit','필수 응답 완료 · 점수는 참고']],c.completion)}${c.completion==='score'?input('','pass_count','필요 정답 개수',c.pass_count,'number','min="1"'):''}${input('','max_attempts','문항별 제출 횟수 · 0이면 무제한',c.max_attempts,'number','min="0" max="30"')}<label class="check"><input type="checkbox" data-qkey="hints" ${c.hints?'checked':''}>힌트 선택 제공</label>${sel('','feedback','해설 공개 시점',[['after_submit','해당 문항 제출 후'],['after_complete','미션 완료 후'],['none','해설 숨김']],c.feedback)}`:''}${c.mode==='team'?`${sel('','team_assignment','팀 구성',[['both','팀 코드 참여 + 랜덤 배정'],['code','팀 코드 참여'],['random','랜덤 배정']],c.team_assignment)}${input('','team_size','팀 정원',c.team_size,'number','min="2" max="20"')}${note('팀원 2명부터 답안을 제출할 수 있습니다. 첫 제출 후에는 팀 합류·변경이 잠깁니다. 팀이 완료하면 참여 중인 모든 팀원이 완료됩니다.')}`:''}${c.questions.map((q,i)=>questionEditor(q,i)).join('')}${button('문항 추가','quiz-add-question','primary')}${button('참가자 문항 미리보기','quiz-preview')}`}
 function questionEditor(q,index){const c=draft.config,qs=c.questions;return `<section class="quiz-editor-question card" data-question-id="${q.id}"><div class="row"><h3>문항 ${index+1}</h3><div class="actions">${button('위로','quiz-move:'+q.id+':-1','text-btn',index===0?'disabled':'')}${button('아래로','quiz-move:'+q.id+':1','text-btn',index===qs.length-1?'disabled':'')}${button('삭제','quiz-remove:'+q.id,'text-btn')}</div></div>${sel(q.id,'type','문항 유형',allowed().map(k=>[k,types[k]]),q.type)}${textarea(q.id,'prompt','문제·질문',q.prompt)}<label class="check"><input type="checkbox" data-qq="${q.id}" data-qkey="required" ${q.required?'checked':''}>필수 응답</label>${sel(q.id,'media.kind','문제 자료',[['none','텍스트'],['image','사진·그림'],['audio','음성'],['video','영상'],['observation','현장 관찰']],q.media?.kind||'none')}${['image','audio','video'].includes(q.media?.kind)?`<label>자료 파일 · 최대 4MB<input type="file" data-quiz-upload="${q.id}" accept="${q.media.kind==='image'?'image/png,image/jpeg,image/webp':q.media.kind==='audio'?'audio/mpeg,audio/wav,audio/ogg':'video/mp4,video/webm'}"></label>${q.media.url?`<p>등록한 자료</p>${media(q.media)}`:note('문제에 사용할 파일을 등록하세요.')}`:''}${q.media?.kind!=='none'?textarea(q.id,'media.caption',q.media.kind==='observation'?'현장 관찰 안내':'자료 설명 · 음성·영상은 대체 설명',q.media.caption||''):''}${answerEditor(q,index)}${!draft.survey?textarea(q.id,'hint','힌트 · 선택',q.hint||'')+textarea(q.id,'explanation','정답 해설 · 선택',q.explanation||''):''}</section>`}
 function answerEditor(q,index){let html='';
  if(['ox','single','multi','scenario','hotspot'].includes(q.type)){
   html=`<h4>${draft.survey?'응답 보기':'보기와 정답'}</h4>${(q.choices||[]).map(choice=>`<div class="quiz-choice-editor">${q.type==='ox'?`<strong>${choice.label}</strong>`:input(q.id,'choice.'+choice.id,'보기 내용',choice.label)}${!draft.survey?`<label class="check"><input type="${q.type==='multi'?'checkbox':'radio'}" name="correct-${q.id}" data-qq="${q.id}" data-correct="${choice.id}" ${(q.answers||[]).includes(choice.id)?'checked':''}>정답</label>`:''}${q.type!=='ox'?button('보기 삭제','quiz-remove-choice:'+q.id+':'+choice.id,'text-btn'):''}${draft.config.mode==='branch'&&['ox','single','scenario'].includes(q.type)?sel(q.id,'branch.'+choice.id,'이 답을 고르면',[['','다음 문항'],['end','이 경로 종료'],...draft.config.questions.slice(index+1).map((next,j)=>[next.id,`문항 ${index+j+2} · ${next.prompt.slice(0,30)||types[next.type]}`])],q.branches?.[choice.id]||''):''}</div>`).join('')}${q.type!=='ox'?button('보기 추가','quiz-add-choice:'+q.id):''}`;
   if(q.type==='hotspot'){
    const chosen=q._region||q.choices?.[0]?.id,rect=q.regions?.[chosen]||{x:0,y:0,width:20,height:20};
    html+=`${sel(q.id,'_region','위치를 지정할 보기',(q.choices||[]).map(c=>[c.id,c.label]),chosen)}${q.media?.url?`<div class="quiz-image-picker" data-quiz-region="${q.id}"><img src="${esc(q.media.url)}" alt="${esc(q.media.caption)}" draggable="false"><span class="quiz-region" style="left:${rect.x}%;top:${rect.y}%;width:${rect.width}%;height:${rect.height}%"></span></div>${note('이미지 위를 끌어 구역을 지정하거나 아래 비율을 입력하세요.')}`:''}<div class="grid2">${[['x','왼쪽 (%)'],['y','위쪽 (%)'],['width','너비 (%)'],['height','높이 (%)']].map(([k,l])=>input(q.id,'rect.'+chosen+'.'+k,l,rect[k],'number','min="0" max="100" step="any"')).join('')}</div>`;
   }
  }
  if(q.type==='short')html=textarea(q.id,'answers','허용 정답 · 한 줄에 하나',(q.answers||[]).join('\n'));
  if(q.type==='blank')html=`${(q.blanks||[]).map(b=>`<div class="bubble">${input(q.id,'blank.'+b.id+'.label','빈칸 이름',b.label)}${textarea(q.id,'blank.'+b.id+'.answers','허용 정답 · 한 줄에 하나',b.answers.join('\n'))}${button('빈칸 삭제','quiz-remove-blank:'+q.id+':'+b.id,'text-btn')}</div>`).join('')}${button('빈칸 추가','quiz-add-blank:'+q.id)}`;
  if(q.type==='match')html=`${(q.pairs||[]).map(p=>`<div class="bubble grid2">${input(q.id,'pair.'+p.id+'.left','왼쪽 항목',p.left)}${input(q.id,'pair.'+p.id+'.right','연결할 정답',p.right)}${button('짝 삭제','quiz-remove-pair:'+q.id+':'+p.id,'text-btn')}</div>`).join('')}${button('짝 추가','quiz-add-pair:'+q.id)}`;
  if(q.type==='order')html=`${note('정답 순서대로 항목을 입력하세요. 참가자에게는 순서를 섞어 보여줍니다.')}${(q.items||[]).map((v,i)=>`<div class="bubble">${input(q.id,'item.'+v.id,`${i+1}번째 항목`,v.label)}${button('위로','quiz-order-item:'+q.id+':'+i+':-1','text-btn')}${button('아래로','quiz-order-item:'+q.id+':'+i+':1','text-btn')}${button('항목 삭제','quiz-remove-item:'+q.id+':'+v.id,'text-btn')}</div>`).join('')}${button('항목 추가','quiz-add-item:'+q.id)}`;
  if(['rating','number'].includes(q.type))html=`<div class="grid2">${input(q.id,'min','최솟값',q.min??0,'number')}${input(q.id,'max','최댓값',q.max??5,'number')}</div>`;
  return html;
 }
 function repaint(){const root=$('#quiz-builder');if(root&&draft)root.innerHTML=builder()}
 function definition(){const c=structuredClone(draft.config);for(const q of c.questions){delete q._region;if(q.type==='order')q.order=q.items.map(i=>i.id)}return c}
 function update(el){if(!draft||!el.dataset.qkey)return;const key=el.dataset.qkey,q=el.dataset.qq?draft.config.questions.find(q=>q.id===el.dataset.qq):draft.config;if(!q)return;let value=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value;
  if(key==='type'){const old=q,type=value;Object.assign(q,question(type),{id:old.id,prompt:old.prompt,required:old.required,media:old.media,hint:old.hint,explanation:old.explanation});if(type==='hotspot'){q.media={...q.media,kind:'image'};q.regions=Object.fromEntries(q.choices.map((c,i)=>[c.id,{x:i*50,y:0,width:50,height:100}]))}repaint();return}
  const parts=key.split('.');if(parts[0]==='media')q.media[parts[1]]=value;
  else if(parts[0]==='choice')q.choices.find(c=>c.id===parts[1]).label=value;
  else if(parts[0]==='branch'){q.branches=q.branches||{};if(value)q.branches[parts[1]]=value;else delete q.branches[parts[1]]}
  else if(parts[0]==='rect'){q.regions=q.regions||{};q.regions[parts[1]]={x:0,y:0,width:20,height:20,...q.regions[parts[1]],[parts[2]]:Number(value)}}
  else if(parts[0]==='pair')q.pairs.find(p=>p.id===parts[1])[parts[2]]=value;
  else if(parts[0]==='blank')q.blanks.find(b=>b.id===parts[1])[parts[2]]=parts[2]==='answers'?value.split('\n').filter(Boolean):value;
  else if(parts[0]==='item')q.items.find(i=>i.id===parts[1]).label=value;
  else q[key]=key==='answers'?value.split('\n').filter(Boolean):value;
  if(['mode','completion','_region','media.kind'].includes(key))repaint();
 }
 function media(m){if(!m||m.kind==='none')return '';if(m.kind==='observation')return `<div class="notice">${esc(m.caption)}</div>`;if(!m.url)return '';const source=esc(m.url);return `${m.kind==='image'?`<img class="quiz-media" src="${source}" alt="${esc(m.caption)}">`:m.kind==='audio'?`<audio class="quiz-media" src="${source}" controls preload="metadata"></audio>`:`<video class="quiz-media" src="${source}" controls preload="metadata" playsinline></video>`}${m.caption?`<p class="muted">${esc(m.caption)}</p>`:''}`}
 function responseFields(q){const value=q.response,base=`quiz-${q.id}`,choices=q.choices||[],selected=v=>Array.isArray(value)?value.includes(v):value===v;
  if(['ox','single','scenario','multi'].includes(q.type))return choices.map(c=>`<label class="check"><input type="${q.type==='multi'?'checkbox':'radio'}" name="${base}" value="${esc(c.id)}" ${selected(c.id)?'checked':''}>${esc(c.label)}</label>`).join('');
  if(['short','text'].includes(q.type))return area(base,q.type==='short'?'정답':'응답',value||'');
  if(q.type==='blank')return q.blanks.map(b=>field(base+'-'+b.id,b.label,value?.[b.id]||'')).join('');
  if(q.type==='match')return q.left.map(left=>select(base+'-'+left.id,left.label,[['','선택하세요'],...q.right.map(r=>[r.id,r.label])],value?.[left.id]||'')).join('');
  if(q.type==='order'){const order=value||q.items.map(i=>i.id);return `<div class="quiz-sort" data-quiz-sort="${q.id}">${order.map((v,i)=>`<div class="quiz-sort-row" data-sort-id="${esc(v)}"><span>${i+1}. ${esc(q.items.find(x=>x.id===v)?.label)}</span>${button('↑','quiz-sort:'+q.id+':'+i+':-1','',`aria-label="${esc(t('위로'))}"`)}${button('↓','quiz-sort:'+q.id+':'+i+':1','',`aria-label="${esc(t('아래로'))}"`)}</div>`).join('')}</div>`}
  if(q.type==='hotspot')return `<div class="quiz-image-picker" data-quiz-point="${q.id}"><img src="${esc(q.media.url)}" alt="${esc(q.media.caption)}" draggable="false"><span class="quiz-point" ${typeof value==='object'&&value!==null?`style="left:${value.x}%;top:${value.y}%"`:'hidden'}></span></div><input type="hidden" name="${base}-point" value="${typeof value==='object'&&value!==null?esc(JSON.stringify(value)):''}">${select(base,'이미지의 구역을 선택하거나 위 사진을 누르세요',[['','위치 선택'],...choices.map(c=>[c.id,c.label])],typeof value==='string'?value:'')}`;
  if(q.type==='rating')return select(base,'평가 점수',[['','선택하세요'],...Array.from({length:q.max-q.min+1},(_,i)=>[q.min+i,String(q.min+i)])],value??'');
  return field(base,'숫자 응답',value??'','number');
 }
 function questionCard(q,preview=false){const locked=!preview&&(current?.data.completed||current?.data.survey&&q.answered||q.correct&&!current.data.survey||['staged','branch'].includes(current?.data.mode)&&current?.data.current!==q.id);return `<section class="quiz-question card" data-quiz-q="${q.id}"><h3>${esc(q.prompt)}</h3>${q.required?`<small>${esc(t('필수 응답'))}</small>`:''}${q.type!=='hotspot'?media(q.media):''}${q.hint?`<details><summary>${esc(t('힌트 보기'))}</summary><p>${esc(q.hint)}</p></details>`:''}<fieldset ${locked?'disabled':''}>${responseFields(q)}</fieldset>${q.answered?`<p class="tag ${q.correct?'':'blue'}">${esc(t(current?.data.survey?'응답 저장':q.correct?'정답':'다시 도전하세요'))}</p>`:''}${q.explanation?`<p class="notice">${esc(q.explanation)}</p>`:''}${!preview&&current?.data.max_attempts?note(t('제출 {current} / {limit}회',{current:q.attempts,limit:current.data.max_attempts})):''}</section>`}
 const path=route=>'/api/events/'+encodeURIComponent(current.event)+'/'+route+'?lang='+S.lang;
 async function open(m){current={id:m.id,event:S.event,data:null};await reload()}
 async function reload(){const saved=current;if(!saved)return;const data=await api(path('quiz-session')+'&mission='+encodeURIComponent(saved.id));if(current===saved){current.data=data;render()}}
 function render(){const d=current.data;let body=`<p>${esc(d.description)}</p>`;
  if(d.mode==='team'){
   if(d.team)body+=`<div class="card"><h3>${esc(d.team.assignment==='random'?t('랜덤 팀')+' '+d.team.name.slice(-4):d.team.name)}</h3>${d.team.code?`<p>${esc(t('팀 참여 코드'))}: <strong>${esc(d.team.code)}</strong></p>`:''}<p>${d.team.members.length} / ${d.team_size} ${esc(t('명'))}</p><p>${d.team.members.map((m,i)=>esc(t('참가자 {number}',{number:i+1}))+(m.self?' ('+esc(t('나'))+')':'')).join(' · ')}</p>${note(d.team.started?'풀이가 시작되어 팀 구성이 확정되었습니다.':'팀원 2명부터 제출할 수 있습니다. 첫 답안 제출 전까지 합류·팀 변경이 가능합니다.')}${!d.team.started&&d.can_write?button('팀에서 나가기','quiz-team-leave'):''}${button('팀 현황 갱신','quiz-refresh')}</div>`;
   else if(d.can_write)body+=`${['both','code'].includes(d.team_assignment)?`<div class="card">${form('quiz-team-create',`${field('name','팀 이름','','text',true)}${submitButton('팀 만들기')}`)}${form('quiz-team-join',`${field('code','팀 참여 코드','','text',true)}${submitButton('코드로 합류')}`)}</div>`:''}${['both','random'].includes(d.team_assignment)?button('랜덤 팀 참여','quiz-team-random','primary full'):''}`;
  }
  if(d.purged)body+=note('응답 원자료가 삭제되었습니다. 완료 기록은 유지됩니다.');else if(!d.can_write)body+=note('현재 미션 참여 기간이 아닙니다. 저장된 결과만 확인할 수 있습니다.');
  if(!d.ready){if(d.can_write&&(d.mode!=='team'||d.team))body+=button('미션 시작','quiz-start','primary full')}
  else{
   body+=`<div class="notice info">${esc(t(d.completed?'미션 완료!':d.survey?'필수 문항에 응답하면 완료됩니다.':d.completion==='submit'?'필수 문항을 풀면 완료됩니다.':'필수 응답과 정답 개수 기준을 달성하세요.'))}${!d.survey?`<p>${esc(t('정답'))} ${d.score} / ${d.pass_count}</p>`:''}</div>`;
   if(d.mode==='team'&&!d.completed)body+=note('각자 풀고 싶은 문항에 답해 제출하세요. 팀원의 정답을 합쳐 완료 조건을 달성합니다.');
   const bodyQuestions=d.questions.map(q=>questionCard(q)).join('');
   body+=form('quiz-submit',bodyQuestions+(!d.completed&&d.can_write&&(!['branch','staged'].includes(d.mode)||d.current)?submitButton(d.survey?'응답 제출':'답안 제출'):''));
   if(d.mode==='branch'&&d.finished&&!d.completed&&d.can_write)body+=button('처음부터 다시 풀기','quiz-retry','primary');
  }
  modal(d.title,body);
 }
 async function request(route,body){const saved=current;if(!saved)return;const data=await api(path(route),'POST',{mission:saved.id,...body});if(current!==saved)return;current.data=data;const pass=await api('/api/events/'+encodeURIComponent(saved.event)+'/pass');if(current!==saved)return;S.pass=pass;await publicRender();render()}
 function collect(f){const fd=new FormData(f),out={};for(const q of current.data.questions){if(current.data.survey&&q.answered||q.correct&&!current.data.survey||['staged','branch'].includes(current.data.mode)&&q.id!==current.data.current)continue;const base='quiz-'+q.id;let value;
  if(q.type==='multi')value=fd.getAll(base);
  else if(q.type==='blank')value=Object.fromEntries(q.blanks.map(b=>[b.id,fd.get(base+'-'+b.id)||'']));
  else if(q.type==='match')value=Object.fromEntries(q.left.map(b=>[b.id,fd.get(base+'-'+b.id)||'']));
  else if(q.type==='order')value=[...f.querySelectorAll(`[data-quiz-sort="${q.id}"] [data-sort-id]`)].map(el=>el.dataset.sortId);
  else if(q.type==='hotspot')value=fd.get(base)|| (fd.get(base+'-point')?JSON.parse(fd.get(base+'-point')):null);
  else{value=fd.get(base);if(['number','rating'].includes(q.type)&&value!=='')value=Number(value)}
  const missing=value===null||value===''||Array.isArray(value)&&!value.length||value&&typeof value==='object'&&!Array.isArray(value)&&Object.values(value).some(v=>v==='');
  if(missing&&current.data.mode==='team')continue;
  if(missing&&q.required)throw Error(t('필수 문항에 답해 주세요.'));
  out[q.id]=missing?null:value;
 }return out}
 async function submit(f){const type=f.dataset.form;if(type==='quiz-team-create'||type==='quiz-team-join'){const d=Object.fromEntries(new FormData(f));await request('quiz-team',{...d,action:type.endsWith('create')?'create':'join'});return true}if(type!=='quiz-submit')return false;const answers=collect(f);if(!Object.keys(answers).length)return true;await request('quiz-submit',{answers,revision:current.data.revision,request_id:id()});return true}
 async function action(a){
  if(a==='quiz-refresh'){await reload();return true}if(a==='quiz-start'){await request('quiz-session',{});return true}if(a==='quiz-retry'){await request('quiz-retry',{revision:current.data.revision,request_id:id()});return true}
  if(a==='quiz-team-random'||a==='quiz-team-leave'){await request('quiz-team',{action:a.endsWith('random')?'random':'leave'});return true}
  if(a.startsWith('quiz-sort:')){const [,qid,index,delta]=a.split(':'),root=$(`[data-quiz-sort="${qid}"]`),rows=[...root.children],i=Number(index),j=i+Number(delta);if(j<0||j>=rows.length)return true;const q=(current?.data.questions||draft?.config.questions||[]).find(q=>q.id===qid),order=rows.map(r=>r.dataset.sortId);[order[i],order[j]]=[order[j],order[i]];q.response=order;root.outerHTML=responseFields(q);return true}
  if(a==='quiz-preview'){const preview=$('#quiz-preview');if(preview){preview.remove();return true}const root=document.createElement('div');root.id='quiz-preview';root.innerHTML='<h3>참가자 문항 미리보기</h3>'+draft.config.questions.map(q=>questionCard({...q,...(q.type==='match'?{left:q.pairs.map(p=>({id:p.id,label:p.left})),right:[...q.pairs].reverse().map(p=>({id:p.id,label:p.right}))}:{}),hint:draft.config.hints?q.hint:''},true)).join('');$('#quiz-builder').append(root);root.scrollIntoView({block:'start',behavior:'smooth'});return true}
  if(!a.startsWith('quiz-')||!draft)return false;
  const [,qid,arg,last]=a.split(':'),q=draft.config.questions.find(q=>q.id===qid),c=draft.config;
  if(a==='quiz-add-question'){if(c.questions.length>=40)throw Error('문항은 최대 40개입니다.');c.questions.push(question(draft.survey?'single':'ox'));c.pass_count=c.questions.length;c.random_count=c.questions.length}
  else if(a.startsWith('quiz-remove:')){if(c.questions.length===1)throw Error('문항이 하나 이상 필요합니다.');c.questions=c.questions.filter(q=>q.id!==qid);c.pass_count=Math.min(c.pass_count,c.questions.length);c.random_count=Math.min(c.random_count,c.questions.length)}
  else if(a.startsWith('quiz-move:')){const i=c.questions.indexOf(q),j=i+Number(arg);if(j>=0&&j<c.questions.length)[c.questions[i],c.questions[j]]=[c.questions[j],c.questions[i]]}
  else if(a.startsWith('quiz-add-choice:')){const choice=item('새 보기');q.choices.push(choice);if(q.type==='hotspot')q.regions[choice.id]={x:0,y:0,width:20,height:20}}
  else if(a.startsWith('quiz-remove-choice:')){if(q.choices.length<=2)throw Error('보기는 두 개 이상 필요합니다.');q.choices=q.choices.filter(v=>v.id!==arg);q.answers=q.answers?.filter(v=>v!==arg);delete q.regions?.[arg];delete q.branches?.[arg];if(q._region===arg)delete q._region}
  else if(a.startsWith('quiz-add-blank:'))q.blanks.push({id:id(),label:'새 빈칸',answers:[]});
  else if(a.startsWith('quiz-remove-blank:'))q.blanks=q.blanks.filter(v=>v.id!==arg);
  else if(a.startsWith('quiz-add-pair:'))q.pairs.push({id:id(),left:'',right:''});
  else if(a.startsWith('quiz-remove-pair:'))q.pairs=q.pairs.filter(v=>v.id!==arg);
  else if(a.startsWith('quiz-add-item:'))q.items.push(item('새 항목'));
  else if(a.startsWith('quiz-remove-item:'))q.items=q.items.filter(v=>v.id!==arg);
  else if(a.startsWith('quiz-order-item:')){const i=Number(arg),j=i+Number(last);if(j>=0&&j<q.items.length)[q.items[i],q.items[j]]=[q.items[j],q.items[i]]}
  else return false;
  repaint();return true;
 }
 async function change(el){
  if(el.dataset.correct&&draft){const q=draft.config.questions.find(q=>q.id===el.dataset.qq);q.answers=q.type==='multi'?[...new Set(el.checked?[...(q.answers||[]),el.dataset.correct]:(q.answers||[]).filter(v=>v!==el.dataset.correct))]:[el.dataset.correct]}
  if(el.dataset.qkey&&['SELECT','INPUT'].includes(el.tagName))update(el);
  if(el.dataset.quizUpload&&draft){const q=draft.config.questions.find(q=>q.id===el.dataset.quizUpload),file=el.files?.[0],saved=draft;if(!file)return;if(file.size>4*1024*1024)throw Error('자료 파일은 4MB 이하여야 합니다.');const payload=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)});const r=await api(ep(q.media.kind==='image'?'upload':'quiz-media'),'POST',{mime:file.type,data:payload});if(draft===saved){q.media.url=r.url;repaint()}}
 }
 function point(el,event){const r=el.getBoundingClientRect();return {x:Math.max(0,Math.min(100,(event.clientX-r.left)/r.width*100)),y:Math.max(0,Math.min(100,(event.clientY-r.top)/r.height*100))}}
 document.addEventListener('input',e=>{if(e.target.dataset.qkey&&e.target.tagName!=='SELECT')update(e.target)});
 document.addEventListener('pointerdown',e=>{const box=e.target.closest('[data-quiz-region]');if(box&&draft&&!box.closest('fieldset:disabled')){e.preventDefault();drag={box,start:point(box,e)};box.setPointerCapture?.(e.pointerId)}});
 document.addEventListener('pointerup',e=>{if(drag){const {box,start}=drag,end=point(box,e),q=draft?.config.questions.find(q=>q.id===box.dataset.quizRegion);if(q){const selected=q._region||q.choices[0].id;const x=Math.min(99,Math.floor(Math.min(start.x,end.x))),y=Math.min(99,Math.floor(Math.min(start.y,end.y)));q.regions[selected]={x,y,width:Math.min(100-x,Math.max(1,Math.floor(Math.abs(start.x-end.x)))),height:Math.min(100-y,Math.max(1,Math.floor(Math.abs(start.y-end.y))))};repaint()}drag=null}});
 document.addEventListener('click',e=>{const box=e.target.closest('[data-quiz-point]');if(!box||box.closest('fieldset:disabled'))return;const p=point(box,e),base='quiz-'+box.dataset.quizPoint;box.parentElement.querySelector(`[name="${base}-point"]`).value=JSON.stringify(p);const select=box.parentElement.querySelector(`[name="${base}"]`);if(select)select.value='';const marker=box.querySelector('.quiz-point');marker.hidden=false;marker.style.left=p.x+'%';marker.style.top=p.y+'%'});
 function close(){draft=null;current=null;drag=null}
 return {editor,definition,change,submit,action,open,close};
})();
