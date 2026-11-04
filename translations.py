"""English drafts and source-version review. Only curated public content is eligible."""
import hashlib
import json


def seed_demo_english(db, updated):
    """Curated demo copy only; never overwrite an organizer's translation or edit."""
    event = db.execute('SELECT settings FROM events WHERE id="youth-expo"').fetchone()
    if not event or not json.loads(event['settings']).get('sample'):
        return
    copy = {
        '제22회 대한민국 청소년박람회': '22nd Korea Youth Expo',
        '청소년의 힘으로, 더 푸른 미래를!': 'Youth power for a greener future!',
        '여수엑스포컨벤션센터': 'Yeosu Expo Convention Center',
        '미래기술존': 'Future Technology Zone', '환경·지속가능존': 'Environment & Sustainability Zone',
        '문화예술존': 'Arts & Culture Zone', '미래기술 체험': 'Explore Future Technology',
        '로봇과 만나는 내일': 'Tomorrow with Robots', '지구를 위한 작은 실천': 'Small Steps for Our Planet',
        '나만의 굿즈 만들기': 'Create Your Own Souvenirs', '참여 기관': 'Participating organization',
        '직접 보고 경험하며 새로운 가능성을 발견해 보세요.': 'Discover new possibilities through hands-on experiences.',
        '컨벤션센터': 'Convention Center', '부스 탐험가': 'Booth Explorer',
        '서로 다른 부스 3곳을 인증하세요.': 'Check in at three different booths.',
        '다양한 존 둘러보기': 'Explore Different Zones',
        '서로 다른 존의 부스를 방문해 보세요.': 'Visit booths in different zones.',
        '청소년, AI와 만드는 더 나은 내일': 'Youth and AI: Building a Better Tomorrow',
        '청소년 꿈 콘서트': 'Youth Dream Concert', '자유 참여 프로그램입니다.': 'Everyone is welcome to join.',
        '컨벤션홀 A': 'Convention Hall A', '특설무대': 'Main Stage', '세미나': 'Seminar', '공연': 'Performance',
        '행사 이용 안내': 'Visitor Information',
        '프로그램과 부스 위치를 확인하고 다양한 체험에 참여해 보세요.': 'Explore the program and booth map, and enjoy a variety of activities.',
        '샘플 행사입니다. 관리자 설정 후 실제 행사 정보로 변경하세요.': 'This is a sample event. The organizer can replace it with their event information.',
        '행사 전체 설문': 'Event Feedback Survey', '행사에 얼마나 만족하셨나요?': 'How satisfied are you with the event?',
        '매우 만족': 'Very satisfied', '만족': 'Satisfied', '보통': 'Neutral', '불만족': 'Dissatisfied', '매우 불만족': 'Very dissatisfied',
        '개선할 점이나 의견을 알려주세요.': 'Please share your feedback or suggestions.',
        '주로 이용한 교통수단': 'Main mode of transport', '대중교통': 'Public transport', '승용차': 'Car',
        '도보·자전거': 'Walking or cycling', '기타': 'Other', '모름': 'Not sure',
        '왕복 이동 거리 (km, 모르면 비워두세요)': 'Round-trip distance (km; leave blank if unknown)',
        '승용차 탑승 인원 (본인 포함)': 'Number of people in your car (including you)',
        '방문 구분': 'Visitor type', '지역 주민': 'Local resident', '외지 방문객': 'Visitor from outside the area',
        '응답하지 않음': 'Prefer not to answer', '지역 내 본인 식음료 지출 (원)': 'Your local spending on food and drinks (KRW)',
        '지역 내 본인 숙박 지출 (원)': 'Your local accommodation spending (KRW)',
        '지역 내 본인 쇼핑 지출 (원)': 'Your local shopping spending (KRW)',
        '지역 내 본인 교통 지출 (원)': 'Your local transport spending (KRW)', '지역 내 숙박 일수': 'Number of nights stayed locally',
    }
    for item in sources(db, 'youth-expo'):
        translated = copy.get(item['source'])
        if translated:
            db.execute('INSERT OR IGNORE INTO translations VALUES(?,?,?,?,?,?,?,?,?)',
                       ('youth-expo', item['kind'], item['id'], item['field'], 'en', item['source_hash'], translated, 1, updated))


def signature(text): return hashlib.sha256(text.encode()).hexdigest()

def sources(db,event):
    result=[]
    def append(kind,rid,field,value,critical=False):
        if isinstance(value,str) and value.strip():result.append({'kind':kind,'id':rid,'field':field,'source':value,'source_hash':signature(value),'critical':critical})
    for table,kind,fields,where in [
        ('events','event',['name','description','venue'],'id=?'),
        ('zones','zone',['name','description'],'event=?'),
        ('booths','booth',['name','organization','description','building'],'event=? AND approved=1'),
        ('programs','program',['title','description','place','category'],'event=?'),
        ('missions','mission',['title','description'],'event=? AND published=1'),
        ('notices','notice',['title','body'],'event=? AND target="public"')]:
        for r in db.execute(f'SELECT * FROM {table} WHERE {where}',(event,)):
            for field in fields:append(kind,r['id'],field,r[field],kind=='notice')
    for r in db.execute('SELECT entity,change_note FROM content_meta WHERE event=? AND kind="program"',(event,)):
        append('program',r['entity'],'change_note',r['change_note'])
    settings=json.loads(db.execute('SELECT settings FROM events WHERE id=?',(event,)).fetchone()[0])
    append('setting',event,'header_name',settings.get('header_name',''))
    for building in settings.get('building_maps',[]):append('building',building['name'],'name',building['name'])
    for node in settings.get('outdoor_nodes',[]):append('node',node['id'],'name',node.get('name',''))
    for i,location in enumerate(settings.get('weather',{}).get('locations',[])):append('weather',str(i),'name',location.get('name',''))
    for m in db.execute('SELECT id,config FROM missions WHERE event=? AND published=1',(event,)):
        config=json.loads(m['config']);append('mission',m['id'],'question',config.get('question',''))
        for q in config.get('questions',[]):
            prefix='q.'+q['id']+'.'
            for field in ['prompt','hint']: append('mission',m['id'],prefix+field,q.get(field,''))
            # Explanations can contain the answer. They stay out of automatic
            # external translation; only delivered after the configured release.
            append('mission',m['id'],prefix+'caption',q.get('media',{}).get('caption',''))
            for key in ['choices','items','blanks']:
                for item in q.get(key,[]): append('mission',m['id'],prefix+key+'.'+item['id'],item['label'])
            for pair in q.get('pairs',[]):
                for side in ['left','right']: append('mission',m['id'],prefix+side+'.'+pair['id'],pair[side])
    row=db.execute('SELECT * FROM surveys WHERE event=?',(event,)).fetchone()
    if row:
        append('survey',event,'title',row['title']);append('survey',event,'consent',row['consent'],True)
        for q in json.loads(row['questions']):
            append('survey',event,'question.'+q['id'],q['label'])
            for i,option in enumerate(q.get('options',[])):append('survey',event,f'option.{q["id"]}.{i}',option)
    return result


def reviewed(db,event):
    return {(r['kind'],r['entity'],r['field']):dict(r) for r in db.execute('SELECT * FROM translations WHERE event=? AND lang="en" AND reviewed=1',(event,))}


def translator(db,event):
    rows=reviewed(db,event)
    def get(kind,rid,field,original):
        r=rows.get((kind,rid,field))
        return r['translation'] if r and r['source_hash']==signature(original or '') else original
    return get


def public_payload(db,event,payload):
    get=translator(db,event)
    for field in ['name','description','venue']:payload['event'][field]=get('event',event,field,payload['event'][field])
    theme=payload['theme']
    theme['header_name']=get('setting',event,'header_name',theme.get('header_name') or '')
    # Names also act as map relationship keys. Translate display labels only.
    for b in theme.get('building_maps') or []:b['label']=get('building',b['name'],'name',b['name'])
    for n in theme.get('outdoor_nodes') or []:n['label']=get('node',n['id'],'name',n['name'])
    counts={'translated':0,'missing':0};rows=reviewed(db,event)
    # Count only the content visible in this public payload, not private/draft sources.
    for src in sources(db,event):
        if src['kind'] not in ['survey','mission']:
            row=rows.get((src['kind'],src['id'],src['field']))
            if row and row['source_hash']==src['source_hash']:counts['translated']+=1
            else:counts['missing']+=1
    for key,kind,fields in [('zones','zone',['name','description']),('booths','booth',['name','organization','description']),('programs','program',['title','description','place','category','change_note']),('notices','notice',['title','body'])]:
        for row in payload[key]:
            for field in fields:row[field]=get(kind,row['id'],field,row[field])
    zone_names={z['id']:z['name'] for z in payload['zones']}
    for b in payload['booths']:
        b['zone_name']=zone_names.get(b['zone'],b['zone_name'])
        b['building_label']=get('booth',b['id'],'building',b['building'])
    payload['translation']={'lang':'en',**counts}
    return payload


def pass_payload(db,event,payload):
    get=translator(db,event)
    for m in payload.get('missions',[]):
        for field in ['title','description','question']:
            if field in m:m[field]=get('mission',m['id'],field,m[field])
    for v in payload.get('visits',[]):v['name']=get('booth',v['booth'],'name',v['name'])
    return payload


def survey_payload(db,event,payload):
    get=translator(db,event);s=payload.get('survey')
    if not s:return payload
    for field in ['title','consent']:s[field]=get('survey',event,field,s[field])
    for q in s['questions']:
        q['label']=get('survey',event,'question.'+q['id'],q['label'])
        # Original option values are submitted; translated labels are presentation only.
        if q.get('options'):q['option_labels']=[get('survey',event,f'option.{q["id"]}.{i}',v) for i,v in enumerate(q['options'])]
    return payload


def weather_payload(db,event,payload,index):
    get=translator(db,event)
    for i,location in enumerate(payload.get('locations',[])):
        location['name']=get('weather',str(i),'name',location['name'])
    if payload.get('location'):
        payload['location']=dict(payload['location'],name=get('weather',str(index),'name',payload['location']['name']))
    return payload


def quiz_payload(db,event,mission,config,run,payload):
    get=translator(db,event)
    payload['title']=get('mission',mission,'title',payload['title'])
    payload['description']=get('mission',mission,'description',payload['description'])
    for q in payload.get('questions',[]):
        prefix='q.'+q['id']+'.'
        for field in ['prompt','hint']:
            if field in q:q[field]=get('mission',mission,prefix+field,q[field])
        q['media']['caption']=get('mission',mission,prefix+'caption',q['media']['caption'])
        for key in ['choices','items','blanks','left']:
            for item in q.get(key,[]):item['label']=get('mission',mission,prefix+key+'.'+item['id'],item['label'])
        reverse={v:k for k,v in run['match_tokens'].get(q['id'],{}).items()}
        for item in q.get('right',[]):item['label']=get('mission',mission,prefix+'right.'+reverse[item['id']],item['label'])
    return payload
