"""Validated quiz/survey definitions and server-side question evaluation.

Private definitions contain answer keys. Only public_question() may be sent to
participants; grading, branching and question allocation stay on the server.
"""
import copy
import math
import re
import secrets
import unicodedata

QUIZ_TYPES={'ox','single','multi','short','blank','match','order','scenario','hotspot'}
SURVEY_TYPES={'single','multi','text','rating','number'}
MODES={'single','pack','staged','random','branch','team'}


def string(value,limit=2000,required=True):
    if not isinstance(value,str) or len(value)>limit or (required and not value.strip()):
        raise ValueError('문항의 필수 내용과 글자 수를 확인하세요.')
    return value.strip()


def number(value,low,high):
    if type(value) not in [int,float] or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('문항의 숫자 범위를 확인하세요.')
    return value


def integer(value,low,high):
    if type(value) is not int: raise ValueError('정수를 입력하세요.')
    return number(value,low,high)


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',value):
        raise ValueError('문항·보기 식별자를 확인하세요.')
    return value


def entries(values,minimum=2,maximum=20):
    if not isinstance(values,list) or not minimum<=len(values)<=maximum:
        raise ValueError(f'보기는 {minimum}~{maximum}개가 필요합니다.')
    result=[];seen=set()
    for v in values:
        if not isinstance(v,dict): raise ValueError('보기 형식을 확인하세요.')
        item={'id':identifier(v.get('id')),'label':string(v.get('label'),300)}
        if item['id'] in seen: raise ValueError('중복된 보기가 있습니다.')
        seen.add(item['id']);result.append(item)
    return result


def answers(values):
    if not isinstance(values,list) or not 1<=len(values)<=20: raise ValueError('정답을 하나 이상 입력하세요.')
    return list(dict.fromkeys(string(v,300) for v in values))


def validate(raw,survey=False):
    if not isinstance(raw,dict): raise ValueError('문항 설정을 확인하세요.')
    mode=raw.get('mode','pack')
    if mode not in MODES: raise ValueError('진행 방식을 확인하세요.')
    if survey and mode not in ['single','pack','staged','random','branch']:
        raise ValueError('설문형 미션은 개인별로 응답합니다.')
    qs=raw.get('questions')
    if not isinstance(qs,list) or not 1<=len(qs)<=40: raise ValueError('문항은 1~40개로 구성하세요.')
    if mode=='single' and len(qs)!=1: raise ValueError('한 문제형은 문항을 하나만 등록하세요.')
    out={'version':2,'mode':mode,'questions':[],'completion':raw.get('completion','score') if not survey else 'submit',
         'pass_count':integer(raw.get('pass_count',len(qs)),1,len(qs)),
         'random_count':integer(raw.get('random_count',len(qs)),1,len(qs)),
         'max_attempts':integer(raw.get('max_attempts',0),0,30),
         'hints':bool(raw.get('hints',True)),'feedback':raw.get('feedback','after_submit')}
    out['team_assignment']=raw.get('team_assignment','both');out['team_size']=integer(raw.get('team_size',4),2,20)
    if out['team_assignment'] not in ['both','code','random']: raise ValueError('팀 구성 방식을 확인하세요.')
    if out['completion'] not in ['score','submit'] or out['feedback'] not in ['after_submit','after_complete','none']:
        raise ValueError('완료 기준과 해설 공개 시점을 확인하세요.')
    seen=set()
    for source in qs:
        if not isinstance(source,dict): raise ValueError('문항 형식을 확인하세요.')
        kind=source.get('type');qid=identifier(source.get('id'))
        if kind not in (SURVEY_TYPES if survey else QUIZ_TYPES): raise ValueError('지원하는 문항 유형을 선택하세요.')
        if qid in seen: raise ValueError('중복된 문항이 있습니다.')
        seen.add(qid)
        q={'id':qid,'type':kind,'prompt':string(source.get('prompt'),3000),'required':bool(source.get('required',True)),
           'hint':string(source.get('hint',''),1000,False),'explanation':string(source.get('explanation',''),3000,False)}
        media=source.get('media') or {}
        if not isinstance(media,dict): raise ValueError('문제 자료 설정을 확인하세요.')
        media_type=media.get('kind','none')
        if media_type not in ['none','image','audio','video','observation']: raise ValueError('문제 자료 유형을 확인하세요.')
        q['media']={'kind':media_type,'caption':string(media.get('caption',''),3000,False),'url':''}
        if media_type in ['image','audio','video']:
            url=media.get('url','')
            if not isinstance(url,str) or not re.fullmatch(r'/assets/[\w.-]+',url): raise ValueError('등록한 문제 자료 파일을 선택하세요.')
            q['media']['url']=url
            if not q['media']['caption']: raise ValueError('이미지 설명 또는 음성·영상의 대체 설명을 입력하세요.')
        if kind in ['ox','single','multi','scenario','hotspot']:
            q['choices']=[{'id':'o','label':'O'},{'id':'x','label':'X'}] if kind=='ox' else entries(source.get('choices'))
            ids={c['id'] for c in q['choices']}
            if not survey:
                q['answers']=answers(source.get('answers'))
                if not set(q['answers'])<=ids or (kind!='multi' and len(q['answers'])!=1): raise ValueError('보기 안에서 정답을 선택하세요.')
            if kind=='hotspot':
                if media_type!='image': raise ValueError('사진 위치 퀴즈에는 이미지 자료가 필요합니다.')
                regions=source.get('regions',{})
                if not isinstance(regions,dict) or set(regions)!=ids: raise ValueError('모든 보기의 이미지 구역을 지정하세요.')
                q['regions']={}
                for rid,rect in regions.items():
                    if not isinstance(rect,dict): raise ValueError('이미지 구역을 확인하세요.')
                    r={key:number(rect.get(key),0,100) for key in ['x','y','width','height']}
                    if r['width']<=0 or r['height']<=0 or r['x']+r['width']>100 or r['y']+r['height']>100:
                        raise ValueError('이미지 구역은 그림 안에 있어야 합니다.')
                    q['regions'][rid]=r
        if kind=='short': q['answers']=answers(source.get('answers'))
        if kind=='blank':
            blanks=source.get('blanks',[])
            if not isinstance(blanks,list) or not 1<=len(blanks)<=8 or any(not isinstance(b,dict) for b in blanks): raise ValueError('빈칸은 1~8개로 구성하세요.')
            q['blanks']=[{'id':identifier(b.get('id')),'label':string(b.get('label'),200),'answers':answers(b.get('answers'))} for b in blanks]
            if len({b['id'] for b in q['blanks']})!=len(blanks): raise ValueError('빈칸을 구분하세요.')
        if kind=='match':
            pairs=source.get('pairs',[])
            if not isinstance(pairs,list) or not 2<=len(pairs)<=10 or any(not isinstance(p,dict) for p in pairs): raise ValueError('짝은 2~10개로 구성하세요.')
            q['pairs']=[{'id':identifier(p.get('id')),'left':string(p.get('left'),300),'right':string(p.get('right'),300)} for p in pairs]
            if len({p['id'] for p in q['pairs']})!=len(pairs) or len({p['right'] for p in q['pairs']})!=len(pairs): raise ValueError('짝과 답을 중복 없이 입력하세요.')
        if kind=='order':
            q['items']=entries(source.get('items'),2,10);q['order']=source.get('order')
            if not isinstance(q['order'],list) or len(q['order'])!=len(q['items']) or set(q['order'])!={i['id'] for i in q['items']}: raise ValueError('모든 항목의 정답 순서를 지정하세요.')
        if kind in ['rating','number']:
            q['min']=number(source.get('min',1 if kind=='rating' else 0),0,1e9)
            q['max']=number(source.get('max',5 if kind=='rating' else 1e6),q['min'],1e9)
            if kind=='rating' and (type(q['min']) is not int or type(q['max']) is not int or q['max']-q['min']>10): raise ValueError('평가 척도는 정수로 최대 11단계입니다.')
        branches=source.get('branches',{})
        if not isinstance(branches,dict): raise ValueError('분기 설정을 확인하세요.')
        q['branches']=branches if mode=='branch' else {}
        out['questions'].append(q)
    for index,q in enumerate(out['questions']):
        if q['branches']:
            if q['type'] not in ['single','scenario','ox']: raise ValueError('분기는 OX·단일 선택·상황 선택 문항에 설정하세요.')
            if not set(q['branches'])<={c['id'] for c in q['choices']}: raise ValueError('분기 대상 보기를 확인하세요.')
            later={v['id'] for v in out['questions'][index+1:]}
            if any(v!='end' and v not in later for v in q['branches'].values()): raise ValueError('분기는 뒤의 문항 또는 종료로 연결하세요.')
    if mode=='random' and out['pass_count']>out['random_count'] and out['completion']=='score': raise ValueError('필요 정답 수는 출제 문항 수 이하여야 합니다.')
    if mode=='branch' and out['completion']=='score':
        # Every possible path must permit the configured score; no cyclic paths.
        counts={};n=len(out['questions'])
        for i in range(n-1,-1,-1):
            q=out['questions'][i];default=out['questions'][i+1]['id'] if i+1<n else 'end'
            destinations=[q['branches'].get(c['id'],default) for c in q.get('choices',[])] if q['branches'] else [default]
            counts[q['id']]=1+min(0 if dest=='end' else counts[dest] for dest in destinations)
        if out['pass_count']>counts[out['questions'][0]['id']]: raise ValueError('짧은 분기 경로에서도 달성할 수 있도록 필요 정답 수를 줄이세요.')
    if survey: out.update(hints=False,feedback='none',max_attempts=1)
    return out


def canonical(value): return unicodedata.normalize('NFKC',value).strip().casefold()


def evaluate(q,value,survey=False):
    """Return a normalized answer and its correctness, never trust client scores."""
    kind=q['type']
    if kind in ['ox','single','scenario']:
        if value not in [c['id'] for c in q['choices']]: raise ValueError('보기에서 답을 선택하세요.')
        return value,survey or value in q['answers']
    if kind=='multi':
        if not isinstance(value,list) or not value or any(not isinstance(v,str) for v in value) or len(set(value))!=len(value) or not set(value)<={c['id'] for c in q['choices']}:
            raise ValueError('하나 이상의 보기를 중복 없이 선택하세요.')
        return sorted(value),survey or set(value)==set(q['answers'])
    if kind in ['short','text']:
        value=string(value,3000)
        return value,survey or canonical(value) in {canonical(a) for a in q['answers']}
    if kind=='blank':
        if not isinstance(value,dict) or set(value)!={b['id'] for b in q['blanks']}: raise ValueError('모든 빈칸에 답하세요.')
        value={k:string(v,300) for k,v in value.items()}
        return value,all(canonical(value[b['id']]) in {canonical(a) for a in b['answers']} for b in q['blanks'])
    if kind=='match':
        ids={p['id'] for p in q['pairs']}
        if not isinstance(value,dict) or set(value)!=ids or any(v not in ids for v in value.values()) or len(set(value.values()))!=len(ids): raise ValueError('각 항목의 짝을 중복 없이 선택하세요.')
        return value,all(k==v for k,v in value.items())
    if kind=='order':
        if not isinstance(value,list) or len(value)!=len(q['items']) or any(not isinstance(v,str) for v in value) or set(value)!={i['id'] for i in q['items']}: raise ValueError('모든 항목을 한 번씩 배치하세요.')
        return value,value==q['order']
    if kind=='hotspot':
        if isinstance(value,str):
            if value not in q['regions']: raise ValueError('이미지 구역을 선택하세요.')
            return value,value in q['answers']
        if not isinstance(value,dict) or set(value)!={'x','y'}: raise ValueError('이미지에서 위치를 선택하세요.')
        point={k:number(v,0,100) for k,v in value.items()}
        r=q['regions'][q['answers'][0]]
        return point,r['x']<=point['x']<=r['x']+r['width'] and r['y']<=point['y']<=r['y']+r['height']
    if kind in ['rating','number']:
        n=number(value,q['min'],q['max'])
        if kind=='rating' and type(n) is not int: raise ValueError('평가 점수는 정수로 선택하세요.')
        return n,True
    raise ValueError('문항 유형을 확인하세요.')


def public_question(q,config,feedback=False):
    result={k:copy.deepcopy(q[k]) for k in ['id','type','prompt','required','media']}
    if config['hints']: result['hint']=q['hint']
    if feedback: result['explanation']=q['explanation']
    for key in ['choices','items','min','max']:
        if key in q: result[key]=copy.deepcopy(q[key])
    if 'blanks' in q: result['blanks']=[{'id':b['id'],'label':b['label']} for b in q['blanks']]
    # The relationship IDs in a match are also the answer key: use separate,
    # per-run opaque IDs for the right-hand choices in the delivery layer.
    if 'pairs' in q:
        result['left']=[{'id':p['id'],'label':p['left']} for p in q['pairs']]
        result['right']=[{'id':p['id'],'label':p['right']} for p in q['pairs']]
    return result


def new_run(config):
    qs=config['questions'];ids=[q['id'] for q in qs]
    if config['mode']=='random': ids=secrets.SystemRandom().sample(ids,config['random_count'])
    return {'ids':ids,'answers':{},'correct':{},'attempts':{},'current':ids[0] if config['mode'] in ['staged','branch'] else None,
            'path':[],'finished':False,'completed':False,'revision':1,
            'match_tokens':{q['id']:{p['id']:secrets.token_urlsafe(12) for p in q['pairs']} for q in qs if q['type']=='match'}}


def visible_ids(config,run):
    if config['mode'] in ['staged','branch']: return list(dict.fromkeys(run['path']+([run['current']] if run['current'] else [])))
    return run['ids']


def view(config,run):
    ids=visible_ids(config,run);lookup={q['id']:q for q in config['questions']};questions=[]
    for qid in ids:
        q=lookup[qid];feedback=config['feedback']=='after_submit' and qid in run['answers'] or config['feedback']=='after_complete' and run['completed']
        item=public_question(q,config,feedback)
        if q['type']=='match':
            item['right']=[{'id':run['match_tokens'][qid][p['id']],'label':p['right']} for p in q['pairs']]
            item['right'].sort(key=lambda x:x['id'])
        if q['type']=='order': item['items'].sort(key=lambda x:x['label'])
        item.update(attempts=run['attempts'].get(qid,0),answered=qid in run['answers'],correct=run['correct'].get(qid,False) if not config.get('survey') else None)
        if qid in run['answers']: item['response']=copy.deepcopy(run['answers'][qid])
        questions.append(item)
    return {'questions':questions,'mode':config['mode'],'completion':config['completion'],'pass_count':config['pass_count'],
            'max_attempts':config['max_attempts'],'current':run['current'],'total':len(run['ids']),'score':sum(run['correct'].values()),
            'completed':run['completed'],'finished':run['finished'],'revision':run['revision']}


def submit(config,run,submitted,survey=False):
    if run['completed']: return run
    if not isinstance(submitted,dict) or not submitted: raise ValueError('답변을 입력하세요.')
    allowed=set(visible_ids(config,run))
    if config['mode'] in ['staged','branch']: allowed={run['current']} if run['current'] else set()
    if not set(submitted)<=allowed: raise ValueError('현재 공개된 문항만 제출할 수 있습니다.')
    result=copy.deepcopy(run);lookup={q['id']:q for q in config['questions']}
    for qid,value in submitted.items():
        q=lookup[qid]
        if value is None and not q['required']:
            result['answers'][qid]=None;result['correct'][qid]=False
            continue
        if result['correct'].get(qid) and not survey: continue  # Earned credit cannot regress.
        if config['max_attempts'] and result['attempts'].get(qid,0)>=config['max_attempts']: raise ValueError('이 문항의 제출 횟수를 모두 사용했습니다.')
        normalized=value
        if q['type']=='match':
            reverse={v:k for k,v in result['match_tokens'][qid].items()}
            if not isinstance(value,dict) or any(v not in reverse for v in value.values()): raise ValueError('표시된 보기에서 짝을 선택하세요.')
            normalized={k:reverse[v] for k,v in value.items()}
        normalized,correct=evaluate(q,normalized,survey)
        result['answers'][qid]=copy.deepcopy(value) if q['type']=='match' else normalized
        result['correct'][qid]=correct;result['attempts'][qid]=result['attempts'].get(qid,0)+1
    if config['mode'] in ['staged','branch']:
        qid=result['current'];q=lookup[qid]
        advance=qid in result['answers'] and (config['mode']=='branch' or survey or result['correct'][qid] or config['completion']=='submit' or not q['required'] and result['answers'][qid] is None)
        if advance:
            index=result['ids'].index(qid);next_id=result['ids'][index+1] if index+1<len(result['ids']) else 'end'
            if config['mode']=='branch': next_id=q['branches'].get(result['answers'][qid],next_id) if isinstance(result['answers'][qid],str) else next_id
            result['path'].append(qid);result['current']=None if next_id=='end' else next_id
        result['finished']=result['current'] is None
    else:
        result['finished']=all(qid in result['answers'] for qid in result['ids'] if lookup[qid]['required'])
    considered=result['path'] if config['mode']=='branch' else result['ids']
    score=sum(result['correct'].get(qid,False) for qid in considered)
    result['completed']=result['finished'] and (survey or config['completion']=='submit' or score>=config['pass_count'])
    result['revision']+=1
    return result


def retry(config,run):
    if config['mode']!='branch' or not run['finished'] or run['completed']: raise ValueError('완료 기준에 미달한 분기형 퀴즈만 처음부터 다시 풀 수 있습니다.')
    result=copy.deepcopy(run)
    result.update(answers={},correct={},path=[],current=run['ids'][0],finished=False,revision=run['revision']+1)
    return result
