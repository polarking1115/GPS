"""English drafts and source-version review. Only curated public content is eligible."""
import hashlib
import json


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
    settings=json.loads(db.execute('SELECT settings FROM events WHERE id=?',(event,)).fetchone()[0])
    append('setting',event,'header_name',settings.get('header_name',''))
    for building in settings.get('building_maps',[]):append('building',building['name'],'name',building['name'])
    for node in settings.get('outdoor_nodes',[]):append('node',node['id'],'name',node.get('name',''))
    for i,location in enumerate(settings.get('weather',{}).get('locations',[])):append('weather',str(i),'name',location.get('name',''))
    for m in db.execute('SELECT id,config FROM missions WHERE event=? AND published=1',(event,)):
        append('mission',m['id'],'question',json.loads(m['config']).get('question',''))
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
    for key,kind,fields in [('zones','zone',['name','description']),('booths','booth',['name','organization','description']),('programs','program',['title','description','place','category']),('notices','notice',['title','body'])]:
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
