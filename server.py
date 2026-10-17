"""Festival platform. Local development server; deploy behind a reviewed HTTPS gateway."""
from __future__ import annotations
import base64
import csv
import hashlib
import hmac
import io
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
import qrcode
import qrcode.image.svg
import map_config

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('FESTIVAL_DATA', ROOT / '.data')).resolve()
KST = ZoneInfo('Asia/Seoul')
MAX_BODY = 6 * 1024 * 1024
LOCK = threading.Lock()
RATE_LOCK = threading.Lock()
RATE = {}


def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def day(): return datetime.now(KST).date().isoformat()
def uid(): return secrets.token_urlsafe(18)
def pack(v): return json.dumps(v, ensure_ascii=False, separators=(',', ':'))
def unpack(v, default=None): return json.loads(v) if v else default

def connect():
    db = sqlite3.connect(DATA / 'festival.sqlite3', timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def password(value):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
def verify(value, encoded):
    try:
        salt, expected = encoded.split(':')
        actual = hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError): return False

def secret_box(): return Fernet((DATA / 'encryption.key').read_bytes())
def encrypt(v): return secret_box().encrypt(v.encode()).decode() if v else ''
def decrypt(v): return secret_box().decrypt(v.encode()).decode() if v else ''
def phone_hash(v): return hmac.new((DATA/'encryption.key').read_bytes(),v.encode(),hashlib.sha256).hexdigest()
def normalize_phone(v):
    v = re.sub(r'[\s().-]', '', str(v))
    if v.startswith('+82'): v = '0' + v[3:]
    if not re.fullmatch(r'01[016789]\d{7,8}', v): raise ApiError(400, '연락처 형식을 확인하세요. 국내 휴대전화 번호를 입력해 주세요.')
    return v

def text(v, length=200, required=True):
    if not isinstance(v, str) or (required and not v.strip()) or len(v) > length: raise ApiError(400, '입력값의 길이와 필수 항목을 확인하세요.')
    return v.strip()
def integer(v, low=0, high=1000000):
    if type(v) is not int or not low <= v <= high: raise ApiError(400, '숫자 범위를 확인하세요.')
    return v

def date_value(v, optional=True):
    if not v and optional: return ''
    try: return datetime.fromisoformat(v).date().isoformat()
    except (ValueError, TypeError): raise ApiError(400, '날짜 형식을 확인하세요.')
def is_open(start, end): return (not start or day() >= start) and (not end or day() <= end)

class ApiError(Exception):
    def __init__(self, status, message): self.status, self.message = status, message


def initialize(seed=True):
    DATA.mkdir(parents=True, exist_ok=True); DATA.chmod(0o700)
    key = DATA / 'encryption.key'
    if not key.exists():
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f: f.write(Fernet.generate_key())
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS access(user TEXT REFERENCES users(id),event TEXT,role TEXT NOT NULL,PRIMARY KEY(user,event,role));
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user TEXT REFERENCES users(id),booth TEXT,display TEXT,expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS invites(token TEXT PRIMARY KEY,event TEXT NOT NULL,role TEXT NOT NULL,email TEXT NOT NULL,expires INTEGER NOT NULL,used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',venue TEXT NOT NULL DEFAULT '',start TEXT NOT NULL DEFAULT '',end TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'draft',settings TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS zones(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),name TEXT NOT NULL,color TEXT NOT NULL DEFAULT '#00a3c4',description TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS booths(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),zone TEXT NOT NULL REFERENCES zones(id),name TEXT NOT NULL,organization TEXT NOT NULL DEFAULT '',description TEXT NOT NULL DEFAULT '',code TEXT NOT NULL DEFAULT '',building TEXT NOT NULL DEFAULT '',x REAL DEFAULT 50,y REAL DEFAULT 50,lat REAL,lng REAL,approved INTEGER DEFAULT 0,status TEXT NOT NULL DEFAULT 'closed',password TEXT NOT NULL,qr TEXT UNIQUE NOT NULL,manager TEXT UNIQUE NOT NULL,contact TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS participants(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),token TEXT UNIQUE NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS visits(participant TEXT REFERENCES participants(id),booth TEXT REFERENCES booths(id),zone TEXT NOT NULL,day TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(participant,booth,day));
        CREATE INDEX IF NOT EXISTS visit_booth ON visits(booth,day);
        CREATE INDEX IF NOT EXISTS visit_participant ON visits(participant);
        CREATE TABLE IF NOT EXISTS ratings(participant TEXT REFERENCES participants(id),booth TEXT REFERENCES booths(id),score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),updated TEXT NOT NULL,PRIMARY KEY(participant,booth));
        CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',kind TEXT NOT NULL,target INTEGER NOT NULL,refs TEXT NOT NULL,start TEXT NOT NULL DEFAULT '',end TEXT NOT NULL DEFAULT '',published INTEGER DEFAULT 0,config TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS mission_answers(participant TEXT REFERENCES participants(id),mission TEXT REFERENCES missions(id),answer TEXT NOT NULL,approved INTEGER DEFAULT 0,created TEXT NOT NULL,PRIMARY KEY(participant,mission));
        CREATE TABLE IF NOT EXISTS programs(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',date TEXT NOT NULL,time TEXT NOT NULL,place TEXT NOT NULL,building TEXT NOT NULL DEFAULT '',category TEXT NOT NULL DEFAULT '세미나',url TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS notices(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),title TEXT NOT NULL,body TEXT NOT NULL,severity TEXT NOT NULL,target TEXT NOT NULL,refs TEXT NOT NULL,ack INTEGER NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS acknowledgments(notice TEXT REFERENCES notices(id),booth TEXT REFERENCES booths(id),display TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(notice,booth));
        CREATE TABLE IF NOT EXISTS inquiries(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),booth TEXT REFERENCES booths(id),category TEXT NOT NULL,urgent INTEGER NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'received',assignee TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,inquiry TEXT NOT NULL REFERENCES inquiries(id),sender TEXT NOT NULL,display TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS surveys(event TEXT PRIMARY KEY REFERENCES events(id),title TEXT NOT NULL,questions TEXT NOT NULL,published INTEGER DEFAULT 0,end TEXT NOT NULL DEFAULT '',consent TEXT NOT NULL DEFAULT '',under14 INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS responses(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),participant TEXT NOT NULL REFERENCES participants(id),answers TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',phone_hash TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,UNIQUE(event,participant));
        CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),response TEXT UNIQUE NOT NULL REFERENCES responses(id),phone_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'eligible',created TEXT NOT NULL,UNIQUE(event,phone_hash));
        CREATE TABLE IF NOT EXISTS prizes(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),name TEXT NOT NULL,count INTEGER NOT NULL,drawn INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS winners(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),prize TEXT NOT NULL REFERENCES prizes(id),entry TEXT UNIQUE NOT NULL REFERENCES entries(id),status TEXT NOT NULL DEFAULT 'ready',note TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS draws(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),prize TEXT NOT NULL,actor TEXT NOT NULL,candidates TEXT NOT NULL,winners TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),participant TEXT NOT NULL REFERENCES participants(id),kind TEXT NOT NULL,location TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'received',reply TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS staff_surveys(booth TEXT PRIMARY KEY REFERENCES booths(id),answers TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS booth_event ON booths(event);
        CREATE INDEX IF NOT EXISTS response_event ON responses(event);
        ''')
        if seed and not db.execute('SELECT 1 FROM events').fetchone(): seed_demo(db)
    (DATA/'festival.sqlite3').chmod(0o600)


def default_settings():
    return {'survey_gate':'all','entry_gate':'missions','required_missions':1,'survey_end':'','entry_end':'','primary':'#123b9b','accent':'#00a3c4','hero':'/assets/youth-hero.png','building_maps':[], 'outdoor_map':map_config.outdoor_map({}), 'outdoor_nodes':[], 'outdoor_edges':[], 'carbon_factors':{},'local_area':'','safety_phone':'','reporting_enabled':False,'features':{'missions':True,'survey':True,'programs':True},'sample':False}


def seed_demo(db):
    settings=default_settings(); settings['sample']=True
    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)',('youth-expo','제22회 대한민국 청소년박람회','청소년의 힘으로, 더 푸른 미래를!','여수엑스포컨벤션센터',day(),day(),'active',pack(settings),now()))
    for zid,name,color in [('future','미래기술존','#00a3c4'),('eco','환경·지속가능존','#3bb57e'),('culture','문화예술존','#f3488a')]:
        db.execute('INSERT INTO zones VALUES(?,?,?,?,?)',(zid,'youth-expo',name,color,''))
    for i,(name,zid) in enumerate([('미래기술 체험','future'),('로봇과 만나는 내일','future'),('지구를 위한 작은 실천','eco'),('나만의 굿즈 만들기','culture')]):
        bid='booth-'+str(i+1)
        db.execute('INSERT INTO booths VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(bid,'youth-expo',zid,name,'참여 기관','직접 보고 경험하며 새로운 가능성을 발견해 보세요.',f'E-{12+i}','컨벤션센터',22+i*18,28+i*10,None,None,1,'open',password(secrets.token_urlsafe(30)),uid(),uid(),'',now()))
    db.execute('INSERT INTO missions VALUES(?,?,?,?,?,?,?,?,?,?,?)',('explorer','youth-expo','부스 탐험가','서로 다른 부스 3곳을 인증하세요.','booths',3,'[]','','',1,'{}'))
    db.execute('INSERT INTO missions VALUES(?,?,?,?,?,?,?,?,?,?,?)',('zones','youth-expo','다양한 존 둘러보기','서로 다른 존의 부스를 방문해 보세요.','zones',2,'[]','','',1,'{}'))
    for i,(title,place,cat) in enumerate([('청소년, AI와 만드는 더 나은 내일','컨벤션홀 A','세미나'),('청소년 꿈 콘서트','특설무대','공연')]):
        db.execute('INSERT INTO programs VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),'youth-expo',title,'자유 참여 프로그램입니다.',day(),'11:00' if i==0 else '14:00',place,'컨벤션센터',cat,''))
    db.execute('INSERT INTO notices VALUES(?,?,?,?,?,?,?,?,?)',(uid(),'youth-expo','행사 이용 안내','샘플 행사입니다. 관리자 설정 후 실제 행사 정보로 변경하세요.','normal','public','[]',0,now()))
    db.execute('INSERT INTO surveys VALUES(?,?,?,?,?,?,?)',('youth-expo','행사 전체 설문',pack(templates(['satisfaction','carbon','economy'])),0,'','',0))


def templates(names):
    bank={
      'satisfaction':[{'id':'satisfaction','label':'행사에 얼마나 만족하셨나요?','type':'choice','options':['매우 만족','만족','보통','불만족','매우 불만족'],'required':True},{'id':'opinion','label':'개선할 점이나 의견을 알려주세요.','type':'text','required':False}],
      'carbon':[{'id':'transport','label':'주로 이용한 교통수단','type':'choice','options':['대중교통','승용차','도보·자전거','기타','모름'],'required':False},{'id':'distance_km','label':'왕복 이동 거리 (km, 모르면 비워두세요)','type':'number','required':False},{'id':'occupants','label':'승용차 탑승 인원 (본인 포함)','type':'number','required':False}],
      'economy':[{'id':'resident','label':'방문 구분','type':'choice','options':['지역 주민','외지 방문객','응답하지 않음'],'required':False},{'id':'food','label':'지역 내 본인 식음료 지출 (원)','type':'number','required':False},{'id':'lodging','label':'지역 내 본인 숙박 지출 (원)','type':'number','required':False},{'id':'shopping','label':'지역 내 본인 쇼핑 지출 (원)','type':'number','required':False},{'id':'local_transport','label':'지역 내 본인 교통 지출 (원)','type':'number','required':False},{'id':'nights','label':'지역 내 숙박 일수','type':'number','required':False}]
    }
    return [q for name in dict.fromkeys(names) for q in bank.get(name,[])]


def audit(db,e,actor,action,detail=''):
    db.execute('INSERT INTO audit(event,actor,action,detail,created) VALUES(?,?,?,?,?)',(e,actor,action,pack(detail) if not isinstance(detail,str) else detail,now()))


def get_event(db,e,public=False):
    r=db.execute('SELECT * FROM events WHERE id=?',(e,)).fetchone()
    if not r or (public and r['status']=='draft'): raise ApiError(404,'공개된 행사를 찾을 수 없습니다.')
    return dict(r,settings=unpack(r['settings']))


def mission_state(db,e,pid,public=True):
    missions=db.execute('SELECT * FROM missions WHERE event=?'+(' AND published=1' if public else ''),(e,)).fetchall()
    result=[]
    for r in missions:
        m=dict(r); refs=unpack(m['refs'],[]); config=unpack(m.pop('config'),{})
        visits=db.execute('SELECT booth,zone,day FROM visits WHERE participant=? AND (?="" OR day>=?) AND (?="" OR day<=?)',(pid,m['start'],m['start'],m['end'],m['end'])).fetchall() if pid else []
        if m['kind']=='zones': progress=len({v['zone'] for v in visits if not refs or v['zone'] in refs})
        elif m['kind']=='zone': progress=len({v['booth'] for v in visits if v['zone'] in refs})
        elif m['kind'] in ['quiz','text']:
            answer=db.execute('SELECT approved FROM mission_answers WHERE participant=? AND mission=?',(pid,m['id'])).fetchone() if pid else None
            progress=1 if answer and answer[0] else 0
            m['pending']=bool(answer and not answer[0]);m['question']=config.get('question','');m['options']=config.get('options',[])
        else: progress=len({v['booth'] for v in visits if not refs or v['booth'] in refs})
        m.update(refs=refs,progress=min(progress,m['target']),completed=progress>=m['target'],available=is_open(m['start'],m['end']))
        result.append(m)
    return result


def gate_ok(db,event,pid,key):
    s=event['settings']; gate=s.get(key,'all')
    if gate=='all': return True
    return sum(m['completed'] for m in mission_state(db,event['id'],pid))>=int(s.get('required_missions',1))


def booth_stats(db,e):
    result=[]
    for r in db.execute('SELECT b.*,z.name zone_name,z.color zone_color FROM booths b JOIN zones z ON z.id=b.zone WHERE b.event=? ORDER BY b.code,b.created',(e,)):
        b={k:r[k] for k in r.keys() if k not in ['password','contact','qr','manager']}
        b.update(dict(db.execute('SELECT COUNT(DISTINCT participant) total,COUNT(DISTINCT CASE WHEN day=? THEN participant END) today FROM visits WHERE booth=?',(day(),b['id'])).fetchone()))
        b['ratings']=dict(db.execute('SELECT COUNT(*) count,ROUND(AVG(score),2) average FROM ratings WHERE booth=?',(b['id'],)).fetchone())
        b['ratings']['distribution']={str(x['score']):x['n'] for x in db.execute('SELECT score,COUNT(*) n FROM ratings WHERE booth=? GROUP BY score',(b['id'],))}
        result.append(b)
    return result


def validate_questions(qs):
    if not isinstance(qs,list) or len(qs)>60: raise ApiError(400,'설문은 최대 60문항입니다.')
    seen=set()
    for q in qs:
        if not isinstance(q,dict): raise ApiError(400,'문항 형식을 확인하세요.')
        q['id']=text(q.get('id',''),60);q['label']=text(q.get('label',''),500)
        if q['id'] in seen or q.get('type') not in ['text','choice','multi','number','rating']: raise ApiError(400,'중복 문항 ID 또는 지원하지 않는 유형입니다.')
        seen.add(q['id'])
        q['required']=bool(q.get('required',False))
        if q['type'] in ['choice','multi']:
            if not isinstance(q.get('options'),list) or not 1<=len(q['options'])<=30: raise ApiError(400,'선택지를 확인하세요.')
            q['options']=[text(x,200) for x in q['options']]
    return qs


def validate_answers(qs,answers):
    if not isinstance(answers,dict): raise ApiError(400,'답변 형식이 올바르지 않습니다.')
    out={}
    for q in qs:
        value=answers.get(q['id'])
        if value is None or value=='' or value==[]:
            if q.get('required'): raise ApiError(400,q['label']+' 항목을 입력해 주세요.')
            continue
        if q['type']=='number':
            if isinstance(value,bool): raise ApiError(400,'숫자를 확인하세요.')
            try: value=float(value)
            except (ValueError,TypeError): raise ApiError(400,'숫자를 확인하세요.')
            if not 0<=value<=1e9: raise ApiError(400,'숫자 범위를 확인하세요.')
        elif q['type']=='rating': value=integer(value,1,5)
        elif q['type']=='choice':
            if value not in q['options']: raise ApiError(400,'선택지를 확인하세요.')
        elif q['type']=='multi':
            if not isinstance(value,list) or any(v not in q['options'] for v in value): raise ApiError(400,'선택지를 확인하세요.')
            value=list(dict.fromkeys(value))
        else: value=text(value,3000,False)
        out[q['id']]=value
    return out


class Handler(BaseHTTPRequestHandler):
    server_version='Festival/1.0'
    def log_message(self, fmt, *args): pass  # Tokens, reports and URL query strings must not enter request logs.
    def headers_common(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Permissions-Policy','camera=(self), geolocation=(self), microphone=()')
        embeds=[]
        for candidate in os.environ.get('FESTIVAL_EMBED_ORIGINS','').split(','):
            candidate=candidate.strip(); parsed=urlparse(candidate)
            if parsed.scheme in ['https','http'] and parsed.netloc and parsed.path in ['', '/'] and not parsed.query and not parsed.fragment and not parsed.username:
                embeds.append(parsed.scheme+'://'+parsed.netloc)
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tile.openstreetmap.org https://server.arcgisonline.com; connect-src 'self'; frame-ancestors 'self' "+' '.join(embeds)+"; base-uri 'self'; form-action 'self'")
        origin=self.headers.get('Origin')
        if origin in embeds and self.command=='GET' and re.fullmatch(r'/api/events(?:/[\w-]+)?',urlparse(self.path).path):
            self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')
    def send(self,status,value,mime='application/json; charset=utf-8',headers=None):
        body=pack(value).encode() if mime.startswith('application/json') else value
        self.send_response(status);self.headers_common()
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PATCH(self): self.handle_request('PATCH')
    def handle_request(self,method):
        try:
            path=urlparse(self.path).path
            if path.startswith('/api/'):
                if method!='GET':
                    origin=self.headers.get('Origin')
                    if origin and urlparse(origin).netloc!=self.headers.get('Host'): raise ApiError(403,'다른 사이트에서 보낸 요청입니다.')
                    if self.headers.get('Sec-Fetch-Site')=='cross-site': raise ApiError(403,'다른 사이트에서 보낸 요청입니다.')
                body={}
                if method!='GET':
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ApiError(415,'JSON 요청이 필요합니다.')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=MAX_BODY: raise ApiError(413,'요청 크기를 확인하세요.')
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict): raise ApiError(400,'요청 형식이 잘못되었습니다.')
                with connect() as db:
                    if method!='GET': db.execute('BEGIN IMMEDIATE')
                    result=self.api(db,method,path,parse_qs(urlparse(self.path).query),body)
                if result is not None: self.send(200,result)
                return
            if method!='GET': raise ApiError(405,'지원하지 않는 요청입니다.')
            if path in ['/','/manage','/booth','/register','/invite'] or path.startswith('/e/') or path.startswith('/b/') or path.startswith('/bm/'):
                file=ROOT/'public/index.html'
            else:
                file=(ROOT/'public'/path.lstrip('/')).resolve()
                if not file.is_relative_to(ROOT/'public') or not file.is_file(): raise ApiError(404,'파일을 찾을 수 없습니다.')
            self.send(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        except ApiError as e: self.send(e.status,{'error':e.message})
        except (json.JSONDecodeError,ValueError,TypeError,KeyError,OverflowError): self.send(400,{'error':'입력 형식 또는 필수 항목을 확인하세요.'})
        except sqlite3.IntegrityError: self.send(409,{'error':'중복되거나 연결된 정보가 올바르지 않습니다.'})
        except Exception as e:
            print('Server error:',type(e).__name__,flush=True)
            self.send(500,{'error':'처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.'})

    def limited(self,key,limit=12):
        with RATE_LOCK:
            t=time.monotonic(); k=(self.client_address[0],key)
            if len(RATE)>10000:
                for old in [x for x,v in RATE.items() if t-v[0]>120]: RATE.pop(old,None)
            start,n=RATE.get(k,(t,0))
            if t-start>60: start,n=t,0
            RATE[k]=(start,n+1)
            if n>=limit: raise ApiError(429,'요청이 많습니다. 잠시 후 다시 시도하세요.')
    def auth(self,db):
        token=self.headers.get('Authorization','').removeprefix('Bearer ')
        s=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(digest(token),int(time.time()))).fetchone()
        if not s: raise ApiError(401,'관리자 로그인이 필요합니다.')
        return dict(s)
    def admin(self,db,e,roles=None):
        s=self.auth(db)
        if not s['user']: raise ApiError(403,'운영본부 권한이 필요합니다.')
        permissions={r['role'] for r in db.execute('SELECT role FROM access WHERE user=? AND event IN (?,?)',(s['user'],e,'*'))}
        if not permissions or (roles and not (permissions & set(roles))): raise ApiError(403,'이 기능에 대한 권한이 없습니다.')
        s['roles']=permissions;return s
    def booth_auth(self,db,e,bid):
        s=self.auth(db)
        if s['user']: return self.admin(db,e,['owner','content','operations'])
        if s['booth']!=bid: raise ApiError(403,'담당 부스가 아닙니다.')
        b=db.execute('SELECT event FROM booths WHERE id=?',(bid,)).fetchone()
        if not b or b['event']!=e: raise ApiError(403,'해당 행사 부스가 아닙니다.')
        return s
    def participant(self,db,e,create=False):
        cookies=SimpleCookie()
        try: cookies.load(self.headers.get('Cookie',''))
        except Exception: pass
        cookie=cookies.get('festival_pass')
        token=cookie.value if cookie else ''
        if not token and create: token=uid()+uid()
        if not token: return None,None
        p=db.execute('SELECT * FROM participants WHERE event=? AND token=?',(e,digest(token))).fetchone()
        if not p and create:
            pid=uid();db.execute('INSERT INTO participants VALUES(?,?,?,?)',(pid,e,digest(token),now()))
            p=db.execute('SELECT * FROM participants WHERE id=?',(pid,)).fetchone()
        return dict(p) if p else None,token
    def actor(self,s): return s.get('user') or s.get('display') or s.get('booth')
    def session(self,db,user=None,booth=None,display=''):
        token=uid()+uid();db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token),user,booth,display,int(time.time())+12*3600))
        return token

    def api(self,db,method,path,q,d):
        if path=='/api/status' and method=='GET':
            return {'setup_required':not bool(db.execute('SELECT 1 FROM users').fetchone()),'integrations':{'map':'osm_esri_registered_paths','translation':'not_configured','weather':'not_configured','giftcards':'manual_export'},'timezone':'Asia/Seoul'}
        if path=='/api/setup' and method=='POST':
            self.limited('setup',5)
            if db.execute('SELECT 1 FROM users').fetchone(): raise ApiError(409,'초기 관리자 설정이 완료되어 있습니다.')
            if not ipaddress.ip_address(self.client_address[0]).is_loopback or not os.environ.get('FESTIVAL_ALLOW_SETUP','1')=='1': raise ApiError(403,'초기 설정은 서버의 로컬 접속에서만 가능합니다.')
            email=text(d.get('email',''),200).lower(); pw=text(d.get('password',''),200)
            if len(pw)<12 or '@' not in email: raise ApiError(400,'이메일과 12자 이상의 비밀번호를 입력하세요.')
            user=uid();db.execute('INSERT INTO users VALUES(?,?,?,?)',(user,email,text(d.get('name',''),80),password(pw)))
            db.execute('INSERT INTO access VALUES(?,?,?)',(user,'*','owner'))
            return {'token':self.session(db,user=user),'name':d['name']}
        if path=='/api/login' and method=='POST':
            self.limited('login')
            email=text(d.get('email',''),200).lower();pw=text(d.get('password',''),200)
            u=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not u or not verify(pw,u['password']): raise ApiError(401,'이메일 또는 비밀번호를 확인하세요.')
            return {'token':self.session(db,user=u['id']),'name':u['name']}
        if path=='/api/logout' and method=='POST':
            s=self.auth(db);db.execute('DELETE FROM sessions WHERE token=?',(s['token'],));return {'ok':True}
        if path=='/api/accept-invite' and method=='POST':
            self.limited('invite')
            i=db.execute('SELECT * FROM invites WHERE token=? AND used=0 AND expires>?',(digest(text(d.get('invite',''),200)),int(time.time()))).fetchone()
            if not i: raise ApiError(400,'초대가 만료되었거나 유효하지 않습니다.')
            pw=text(d.get('password',''),200)
            if len(pw)<12: raise ApiError(400,'비밀번호는 12자 이상이어야 합니다.')
            u=db.execute('SELECT * FROM users WHERE email=?',(i['email'],)).fetchone()
            if u:
                if not verify(pw,u['password']): raise ApiError(401,'기존 계정 비밀번호를 입력하세요.')
                user=u['id']
            else:
                user=uid();db.execute('INSERT INTO users VALUES(?,?,?,?)',(user,i['email'],text(d.get('name',''),80),password(pw)))
            db.execute('INSERT OR IGNORE INTO access VALUES(?,?,?)',(user,i['event'],i['role']))
            db.execute('UPDATE invites SET used=1 WHERE token=?',(i['token'],));return {'ok':True}
        if path=='/api/booth-login' and method=='POST':
            self.limited('booth-login')
            b=db.execute('SELECT * FROM booths WHERE manager=?',(text(d.get('manager',''),100),)).fetchone()
            if not b or not verify(text(d.get('password',''),200),b['password']): raise ApiError(401,'관리 코드 또는 비밀번호를 확인하세요.')
            return {'token':self.session(db,booth=b['id'],display=text(d.get('display','담당자'),60)),'event':b['event'],'booth':b['id']}
        if path=='/api/events' and method=='GET':
            return [dict(r) for r in db.execute('SELECT id,name,description,venue,start,end,status FROM events WHERE status!="draft" ORDER BY created DESC')]
        if path=='/api/events' and method=='POST':
            s=self.admin(db,'*',['owner']);eid=uid();settings=default_settings()
            source=d.get('copy')
            if source:
                old=get_event(db,source);settings=old['settings'].copy();settings.update(sample=False,entry_end='',reporting_enabled=False)
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)',(eid,text(d.get('name',''),200),text(d.get('description',''),2000,False),text(d.get('venue',''),300,False),date_value(d.get('start')),date_value(d.get('end')),'draft',pack(settings),now()))
            if source:
                zone_map={};booth_map={}
                for z in db.execute('SELECT * FROM zones WHERE event=?',(source,)).fetchall():
                    new_id=uid();zone_map[z['id']]=new_id
                    db.execute('INSERT INTO zones VALUES(?,?,?,?,?)',(new_id,eid,z['name'],z['color'],z['description']))
                for booth in db.execute('SELECT * FROM booths WHERE event=?',(source,)).fetchall():
                    new_id=uid();booth_map[booth['id']]=new_id
                    db.execute('INSERT INTO booths VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(new_id,eid,zone_map[booth['zone']],booth['name'],booth['organization'],booth['description'],booth['code'],booth['building'],booth['x'],booth['y'],booth['lat'],booth['lng'],0,'closed',password(secrets.token_urlsafe(32)),uid(),uid(),'',now()))
                for mission in db.execute('SELECT * FROM missions WHERE event=?',(source,)).fetchall():
                    mapping=zone_map if mission['kind'] in ['zone','zones'] else booth_map
                    refs=[mapping[x] for x in unpack(mission['refs'],[]) if x in mapping]
                    db.execute('INSERT INTO missions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid(),eid,mission['title'],mission['description'],mission['kind'],mission['target'],pack(refs),'','',0,mission['config']))
                for program in db.execute('SELECT * FROM programs WHERE event=?',(source,)).fetchall():
                    new_date=date_value(d.get('start')) or program['date']
                    db.execute('INSERT INTO programs VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),eid,program['title'],program['description'],new_date,program['time'],program['place'],program['building'],program['category'],program['url']))
                survey=db.execute('SELECT * FROM surveys WHERE event=?',(source,)).fetchone()
                if survey: db.execute('INSERT INTO surveys VALUES(?,?,?,?,?,?,?)',(eid,survey['title'],survey['questions'],0,'','',0))
            audit(db,eid,self.actor(s),'event.create',{'copied':source or ''});return {'id':eid}
        if path=='/api/booth-register' and method=='POST':
            self.limited('register',10);e=text(d.get('event',''),100);ev=get_event(db,e,True)
            if ev['status'] not in ['public','active']: raise ApiError(400,'현재 부스 등록을 받지 않습니다.')
            zone=db.execute('SELECT id FROM zones WHERE event=? AND id=?',(e,d.get('zone'))).fetchone()
            if not zone: raise ApiError(400,'존을 선택하세요.')
            pw=text(d.get('password',''),200)
            if len(pw)<10: raise ApiError(400,'공통 비밀번호는 10자 이상으로 설정하세요.')
            bid=uid();manager=uid();qr=uid()
            db.execute('INSERT INTO booths(id,event,zone,name,organization,description,password,qr,manager,contact,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(bid,e,zone['id'],text(d.get('name',''),200),text(d.get('organization',''),200,False),text(d.get('description',''),3000),password(pw),qr,manager,encrypt(text(d.get('contact',''),200,False)),now()))
            return {'id':bid,'manager':manager,'message':'검토 대기 상태로 등록되었습니다. 관리 주소를 보관하세요.'}
        m=re.fullmatch(r'/api/qr-info/([\w-]+)',path)
        if m and method=='GET':
            b=db.execute('SELECT id,event,name,status,approved FROM booths WHERE qr=?',(m[1],)).fetchone()
            if not b or not b['approved']: raise ApiError(404,'사용할 수 없는 부스 QR입니다.')
            get_event(db,b['event'],True);return dict(b)
        if path=='/api/me' and method=='GET':
            s=self.auth(db)
            if s['booth']:
                b=db.execute('SELECT id,event,name,manager FROM booths WHERE id=?',(s['booth'],)).fetchone()
                return {'kind':'booth','booth':dict(b),'display':s['display']}
            u=db.execute('SELECT id,email,name FROM users WHERE id=?',(s['user'],)).fetchone()
            events=db.execute('SELECT id,name,status FROM events ORDER BY created DESC').fetchall()
            accesses=[dict(r) for r in db.execute('SELECT event,role FROM access WHERE user=?',(s['user'],))]
            permitted=[dict(e) for e in events if any(a['event'] in ['*',e['id']] for a in accesses)]
            return {'kind':'admin','user':dict(u),'events':permitted,'access':accesses}
        m=re.fullmatch(r'/api/events/([\w-]+)(?:/(.*))?',path)
        if not m: raise ApiError(404,'API를 찾을 수 없습니다.')
        e,route=m[1],m[2] or '';ev=get_event(db,e)
        if route=='' and method=='GET':
            if ev['status']=='draft': self.admin(db,e)
            zones=[dict(r) for r in db.execute('SELECT * FROM zones WHERE event=?',(e,))]
            booths=[b for b in booth_stats(db,e) if b['approved']]
            # Strip all administrative/contact/certification secrets from public payloads.
            return {'event':{k:ev[k] for k in ['id','name','description','venue','start','end','status']},'theme':{k:ev['settings'].get(k) for k in ['primary','accent','hero','sample','building_maps','outdoor_map','outdoor_nodes','outdoor_edges','safety_phone','reporting_enabled','features']},'zones':zones,'booths':[{k:b[k] for k in ['id','zone','name','organization','description','code','building','x','y','lat','lng','status','zone_name','zone_color']} for b in booths],'programs':[dict(r) for r in db.execute('SELECT * FROM programs WHERE event=? ORDER BY date,time',(e,))],'notices':[dict(r) for r in db.execute('SELECT id,title,body,severity,created FROM notices WHERE event=? AND target="public" ORDER BY created DESC',(e,))]}
        if route=='pass' and method in ['GET','POST']:
            get_event(db,e,True);p,token=self.participant(db,e,method=='POST')
            result={'participant':None,'visits':[],'missions':mission_state(db,e,None),'survey':None,'reports':[]}
            if p:
                r=db.execute('SELECT id FROM responses WHERE participant=? AND event=?',(p['id'],e)).fetchone()
                entry=db.execute('SELECT en.status,w.status delivery,p.name prize FROM entries en JOIN responses r ON r.id=en.response LEFT JOIN winners w ON w.entry=en.id LEFT JOIN prizes p ON p.id=w.prize WHERE r.participant=? AND en.event=?',(p['id'],e)).fetchone()
                result.update(participant={'id':p['id'],'created':p['created']},visits=[dict(r) for r in db.execute('SELECT v.booth,b.name,b.code,MIN(v.created) created,MAX(r.score) rating FROM visits v JOIN booths b ON b.id=v.booth LEFT JOIN ratings r ON r.booth=v.booth AND r.participant=v.participant WHERE v.participant=? GROUP BY v.booth',(p['id'],))],missions=mission_state(db,e,p['id']),survey={'submitted':bool(r),'entry':dict(entry) if entry else None},reports=[dict(r,reply=decrypt(r['reply'])) for r in db.execute('SELECT id,kind,status,reply,created FROM reports WHERE participant=? AND event=?',(p['id'],e))])
            if method=='POST':
                secure='; Secure' if os.environ.get('FESTIVAL_SECURE_COOKIE')=='1' else ''
                self.send(200,result,headers={'Set-Cookie':f'festival_pass={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000{secure}'})
                return None
            return result
        if route=='certify' and method=='POST':
            self.limited('certify',90);get_event(db,e,True)
            if ev['status']!='active' or not is_open(ev['start'],ev['end']): raise ApiError(409,'행사 참여 인증 기간이 아닙니다.')
            b=db.execute('SELECT * FROM booths WHERE event=? AND qr=? AND approved=1',(e,d.get('qr'))).fetchone()
            if not b: raise ApiError(404,'유효한 부스 QR이 아닙니다.')
            if b['status']!='open': raise ApiError(409,'부스가 일시 중단 또는 운영 종료 상태입니다.')
            p,_=self.participant(db,e)
            if not p: raise ApiError(401,'참가 패스를 먼저 생성하세요.')
            score=d.get('score')
            if score is not None: score=integer(score,1,5)
            existing=db.execute('SELECT 1 FROM visits WHERE participant=? AND booth=?',(p['id'],b['id'])).fetchone()
            db.execute('INSERT OR IGNORE INTO visits VALUES(?,?,?,?,?)',(p['id'],b['id'],b['zone'],day(),now()))
            if score is not None: db.execute('INSERT INTO ratings VALUES(?,?,?,?) ON CONFLICT(participant,booth) DO UPDATE SET score=excluded.score,updated=excluded.updated',(p['id'],b['id'],score,now()))
            return {'ok':True,'already':bool(existing),'missions':mission_state(db,e,p['id'])}
        if route=='mission-answer' and method=='POST':
            p,_=self.participant(db,e)
            if not p: raise ApiError(401,'참가 패스를 생성하세요.')
            m=db.execute('SELECT * FROM missions WHERE id=? AND event=? AND published=1',(d.get('mission'),e)).fetchone()
            if ev['status']!='active' or not m or not is_open(m['start'],m['end']): raise ApiError(409,'현재 수행할 수 없는 미션입니다.')
            config=unpack(m['config'],{});answer=text(d.get('answer',''),3000)
            if m['kind'] not in ['quiz','text']: raise ApiError(400,'제출형 미션이 아닙니다.')
            approved=int(m['kind']=='quiz' and hmac.compare_digest(answer.strip().casefold(),str(config.get('answer','')).strip().casefold()))
            db.execute('INSERT INTO mission_answers VALUES(?,?,?,?,?) ON CONFLICT(participant,mission) DO UPDATE SET answer=excluded.answer,approved=excluded.approved,created=excluded.created',(p['id'],m['id'],encrypt(answer),approved,now()))
            return {'approved':bool(approved),'pending':m['kind']=='text'}
        if route=='survey' and method=='GET':
            get_event(db,e,True);s=db.execute('SELECT * FROM surveys WHERE event=? AND published=1',(e,)).fetchone()
            if not s: return {'survey':None}
            p,_=self.participant(db,e);pid=p['id'] if p else None
            return {'survey':dict(s,questions=unpack(s['questions'])),'can_respond':gate_ok(db,ev,pid,'survey_gate'),'can_enter':gate_ok(db,ev,pid,'entry_gate'),'open':is_open('',s['end']) and ev['status']!='archived'}
        if route=='survey' and method=='POST':
            get_event(db,e,True);p,_=self.participant(db,e)
            if not p: raise ApiError(401,'참가 패스를 생성하세요.')
            s=db.execute('SELECT * FROM surveys WHERE event=? AND published=1',(e,)).fetchone()
            if not s or not is_open('',s['end']) or ev['status']=='archived': raise ApiError(409,'설문이 마감되었거나 공개되지 않았습니다.')
            if not gate_ok(db,ev,p['id'],'survey_gate'): raise ApiError(403,'설문 참여 조건을 먼저 완료하세요.')
            # No child personal-data collection until a verified guardian workflow is implemented.
            age=d.get('age_group')
            if age not in ['14plus','under14']: raise ApiError(400,'연령 구분을 확인하세요.')
            if age=='under14': raise ApiError(403,'만 14세 미만 개인정보 설문은 보호자 동의 절차 준비 후 제공합니다. 일반 행사 기능은 계속 이용할 수 있습니다.')
            answers=validate_answers(unpack(s['questions']),d.get('answers',{}))
            if d.get('survey_consent') is not True or not s['consent']: raise ApiError(400,'설문 개인정보 안내를 확인하고 동의해 주세요.')
            existing=db.execute('SELECT id FROM responses WHERE event=? AND participant=?',(e,p['id'])).fetchone()
            if existing:
                entry=db.execute('SELECT id FROM entries WHERE response=?',(existing[0],)).fetchone()
                return {'submitted':True,'entered':bool(entry),'already':True}
            raw=d.get('phone','');phone=normalize_phone(raw) if raw else '';ph=phone_hash(phone) if phone else ''
            if phone and d.get('lottery_consent') is not True: raise ApiError(400,'추첨 연락처 수집·이용 동의가 필요합니다.')
            rid=uid();db.execute('INSERT INTO responses VALUES(?,?,?,?,?,?,?)',(rid,e,p['id'],encrypt(pack(answers)),encrypt(phone),ph,now()))
            entered=False;reason='no_contact'
            if phone:
                if not is_open('',ev['settings'].get('entry_end','')): reason='closed'
                elif not gate_ok(db,ev,p['id'],'entry_gate'): reason='conditions'
                elif db.execute('SELECT 1 FROM entries WHERE event=? AND phone_hash=?',(e,ph)).fetchone(): reason='duplicate_contact'
                else:
                    db.execute('INSERT INTO entries VALUES(?,?,?,?,?,?)',(uid(),e,rid,ph,'eligible',now()));entered=True;reason='entered'
            return {'submitted':True,'entered':entered,'reason':reason}
        if route=='report' and method=='POST':
            self.limited('report',10);p,_=self.participant(db,e)
            if not p: raise ApiError(401,'참가 패스를 먼저 생성하세요.')
            if not ev['settings'].get('reporting_enabled'): raise ApiError(409,'앱 신고 접수가 활성화되지 않았습니다. 긴급 상황에는 112·119 또는 현장 안전본부에 연락하세요.')
            kind=d.get('kind')
            if kind not in ['safety','harassment','camera']: raise ApiError(400,'신고 유형을 선택하세요.')
            rid=uid();db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,e,p['id'],kind,encrypt(text(d.get('location',''),500)),encrypt(text(d.get('body',''),5000)),'received','',now(),now()))
            audit(db,e,p['id'],'report.received',rid);return {'id':rid,'status':'received'}
        if route=='booth-data' and method=='GET':
            bid=q.get('booth',[''])[0];s=self.booth_auth(db,e,bid)
            b=next((b for b in booth_stats(db,e) if b['id']==bid),None)
            if not b: raise ApiError(404,'부스를 찾을 수 없습니다.')
            raw=db.execute('SELECT qr,manager FROM booths WHERE id=?',(bid,)).fetchone()
            ns=[]
            for n in db.execute('SELECT * FROM notices WHERE event=? AND target!="public" ORDER BY created DESC',(e,)):
                refs=unpack(n['refs'],[])
                if n['target']=='all' or (n['target']=='zone' and b['zone'] in refs) or (n['target']=='booth' and bid in refs):
                    ack=db.execute('SELECT display,created FROM acknowledgments WHERE notice=? AND booth=?',(n['id'],bid)).fetchone()
                    ns.append(dict(n,refs=refs,confirmation=dict(ack) if ack else None))
            inquiries=[dict(r,messages=[dict(x) for x in db.execute('SELECT * FROM messages WHERE inquiry=? ORDER BY created',(r['id'],))]) for r in db.execute('SELECT * FROM inquiries WHERE booth=? ORDER BY created DESC',(bid,))]
            hourly=[dict(x) for x in db.execute('SELECT substr(created,12,2) hour,COUNT(*) count FROM visits WHERE booth=? AND day=? GROUP BY hour ORDER BY hour',(bid,day()))]
            return {'booth':dict(b,qr=raw['qr'],manager=raw['manager']),'notices':ns,'inquiries':inquiries,'hourly_utc':hourly,'staff_survey':bool(db.execute('SELECT 1 FROM staff_surveys WHERE booth=?',(bid,)).fetchone())}
        if route=='booth-update' and method=='POST':
            bid=d.get('booth');s=self.booth_auth(db,e,bid);b=db.execute('SELECT * FROM booths WHERE id=? AND event=?',(bid,e)).fetchone()
            if not b: raise ApiError(404,'부스가 없습니다.')
            if 'status' in d:
                if d['status'] not in ['open','paused','closed']: raise ApiError(400,'운영 상태를 확인하세요.')
                db.execute('UPDATE booths SET status=? WHERE id=?',(d['status'],bid))
            if 'description' in d: db.execute('UPDATE booths SET description=? WHERE id=?',(text(d['description'],3000,False),bid))
            audit(db,e,self.actor(s),'booth.update',{'booth':bid,'status':d.get('status')});return {'ok':True}
        if route=='ack' and method=='POST':
            bid=d.get('booth');s=self.booth_auth(db,e,bid)
            b=db.execute('SELECT zone FROM booths WHERE event=? AND id=?',(e,bid)).fetchone()
            n=db.execute('SELECT * FROM notices WHERE event=? AND id=?',(e,d.get('notice'))).fetchone()
            if not n or not b or not n['ack'] or not (n['target']=='all' or n['target']=='zone' and b['zone'] in unpack(n['refs']) or n['target']=='booth' and bid in unpack(n['refs'])): raise ApiError(403,'해당 부스의 확인 요청이 아닙니다.')
            db.execute('INSERT OR IGNORE INTO acknowledgments VALUES(?,?,?,?)',(n['id'],bid,s.get('display') or '운영본부',now()))
            return {'ok':True}
        if route=='inquiry' and method=='POST':
            bid=d.get('booth');s=self.booth_auth(db,e,bid)
            iid=uid();category=text(d.get('category',''),60)
            if category not in ['시설·장비','통신·시스템','물품·지원','운영 문의','안전','민원·분쟁','기타']: raise ApiError(400,'문의 유형을 선택하세요.')
            db.execute('INSERT INTO inquiries VALUES(?,?,?,?,?,?,?,?,?,?)',(iid,e,bid,category,int(bool(d.get('urgent'))),text(d.get('title',''),200),'received','',now(),now()))
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(uid(),iid,'booth',s.get('display') or '운영본부',text(d.get('body',''),5000),now()));return {'id':iid}
        if route=='message' and method=='POST':
            i=db.execute('SELECT * FROM inquiries WHERE id=? AND event=?',(d.get('inquiry'),e)).fetchone()
            if not i: raise ApiError(404,'문의가 없습니다.')
            s=self.booth_auth(db,e,i['booth'])
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(uid(),i['id'],'admin' if s['user'] else 'booth',s.get('display') or '운영본부',text(d.get('body',''),5000),now()))
            db.execute('UPDATE inquiries SET updated=? WHERE id=?',(now(),i['id']));return {'ok':True}
        if route=='staff-survey' and method=='POST':
            bid=d.get('booth');s=self.booth_auth(db,e,bid)
            allowed=['transport','distance_km','staff_count','printing','disposable','reusable','local_purchase','local_hiring','lodging','food']
            answers={k:d.get('answers',{}).get(k) for k in allowed}
            for k,v in answers.items():
                if v is not None and k!='transport':
                    if isinstance(v,bool) or not isinstance(v,(float,int)) or not 0<=v<=1e10: raise ApiError(400,'실적 숫자를 확인하세요.')
                elif k=='transport' and v is not None: text(v,100,False)
            db.execute('INSERT INTO staff_surveys VALUES(?,?,?) ON CONFLICT(booth) DO UPDATE SET answers=excluded.answers,updated=excluded.updated',(bid,encrypt(pack(answers)),now()))
            audit(db,e,self.actor(s),'staff-survey.submit',bid);return {'ok':True}
        if route=='qr.svg' and method=='GET':
            bid=q.get('booth',[''])[0];self.booth_auth(db,e,bid)
            b=db.execute('SELECT qr FROM booths WHERE id=? AND event=?',(bid,e)).fetchone()
            if not b: raise ApiError(404,'부스가 없습니다.')
            base=os.environ.get('FESTIVAL_PUBLIC_URL','http://'+self.headers.get('Host','127.0.0.1:8000')).rstrip('/')
            image=qrcode.make(base+'/b/'+b['qr'],image_factory=qrcode.image.svg.SvgPathImage)
            buf=io.BytesIO();image.save(buf)
            self.send(200,buf.getvalue(),'image/svg+xml',{'Content-Disposition':'attachment; filename="booth-qr.svg"'});return None
        # Everything below this line is administrative and scoped to one event.
        s=self.admin(db,e);actor=self.actor(s)
        def need(*roles):
            if not s['roles'] & set(roles): raise ApiError(403,'이 업무의 권한이 없습니다.')
        if route=='admin' and method=='GET':
            bs=booth_stats(db,e);zones=[]
            for z in db.execute('SELECT * FROM zones WHERE event=?',(e,)):
                children=[b for b in bs if b['zone']==z['id']]
                zones.append(dict(z,today=sum(b['today'] for b in children),total=sum(b['total'] for b in children)))
            st={'participants':db.execute('SELECT COUNT(*) FROM participants WHERE event=?',(e,)).fetchone()[0],'certified':db.execute('SELECT COUNT(DISTINCT v.participant) FROM visits v JOIN booths b ON b.id=v.booth WHERE b.event=?',(e,)).fetchone()[0],'booth_total':sum(b['total'] for b in bs),'responses':db.execute('SELECT COUNT(*) FROM responses WHERE event=?',(e,)).fetchone()[0],'entries':db.execute('SELECT COUNT(*) FROM entries WHERE event=?',(e,)).fetchone()[0]}
            survey=db.execute('SELECT * FROM surveys WHERE event=?',(e,)).fetchone()
            inquiries=[dict(r,messages=[dict(x) for x in db.execute('SELECT * FROM messages WHERE inquiry=? ORDER BY created',(r['id'],))]) for r in db.execute('SELECT i.*,b.name booth_name FROM inquiries i JOIN booths b ON b.id=i.booth WHERE i.event=? ORDER BY i.created DESC',(e,))]
            notices=[]
            for n in db.execute('SELECT * FROM notices WHERE event=? ORDER BY created DESC',(e,)):
                refs=unpack(n['refs']);target=[b for b in bs if n['target']=='all' or n['target']=='zone' and b['zone'] in refs or n['target']=='booth' and b['id'] in refs]
                notices.append(dict(n,refs=refs,target_count=len(target),confirmed=[dict(x) for x in db.execute('SELECT booth,display,created FROM acknowledgments WHERE notice=?',(n['id'],))]))
            return {'event':ev,'roles':sorted(s['roles']),'booths':bs,'zones':zones,'stats':st,'missions':mission_state(db,e,None,False),'survey':dict(survey,questions=unpack(survey['questions'])) if survey else None,'programs':[dict(r) for r in db.execute('SELECT * FROM programs WHERE event=? ORDER BY date,time',(e,))],'inquiries':inquiries,'notices':notices,'prizes':[dict(r) for r in db.execute('SELECT * FROM prizes WHERE event=?',(e,))],'winners':[dict(r) for r in db.execute('SELECT w.*,p.name prize_name FROM winners w JOIN prizes p ON p.id=w.prize WHERE w.event=?',(e,))]}
        if route=='settings' and method=='POST':
            need('owner');settings=ev['settings']
            for k in ['survey_gate','entry_gate']:
                if k in d:
                    if d[k] not in ['all','missions']: raise ApiError(400,'자격 설정을 확인하세요.')
                    settings[k]=d[k]
            if 'required_missions' in d: settings['required_missions']=integer(d['required_missions'],1,100)
            if 'entry_end' in d: settings['entry_end']=date_value(d['entry_end'])
            if 'safety_phone' in d: settings['safety_phone']=text(d['safety_phone'],40,False)
            if 'reporting_enabled' in d: settings['reporting_enabled']=bool(d['reporting_enabled'])
            for k in ['primary','accent']:
                if k in d:
                    if not re.fullmatch(r'#[0-9a-fA-F]{6}',d[k]): raise ApiError(400,'색상 형식을 확인하세요.')
                    settings[k]=d[k]
            if 'hero' in d:
                if not re.fullmatch(r'/assets/[\w.-]+',d['hero']): raise ApiError(400,'등록한 이미지 경로를 사용하세요.')
                settings['hero']=d['hero']
            if 'maps' in d:
                try: settings['building_maps']=map_config.building_maps(d['maps'])
                except ValueError as error: raise ApiError(400,str(error))
            if 'outdoor_map' in d:
                try: settings['outdoor_map']=map_config.outdoor_map(d['outdoor_map'])
                except ValueError as error: raise ApiError(400,str(error))
            if 'outdoor' in d:
                try: nodes,edges=map_config.graph(d['outdoor'])
                except ValueError as error: raise ApiError(400,str(error))
                settings['outdoor_nodes']=nodes;settings['outdoor_edges']=edges
            status=d.get('status',ev['status'])
            if status not in ['draft','public','active','ended','archived']: raise ApiError(400,'행사 상태가 올바르지 않습니다.')
            db.execute('UPDATE events SET name=?,description=?,venue=?,start=?,end=?,status=?,settings=? WHERE id=?',(text(d.get('name',ev['name']),200),text(d.get('description',ev['description']),2000,False),text(d.get('venue',ev['venue']),300,False),date_value(d.get('start',ev['start'])),date_value(d.get('end',ev['end'])),status,pack(settings),e))
            audit(db,e,actor,'settings.update');return {'ok':True}
        if route=='upload' and method=='POST':
            need('owner','content');mime=d.get('mime')
            if mime not in ['image/png','image/jpeg','image/webp']: raise ApiError(400,'PNG·JPEG·WebP 이미지만 지원합니다.')
            try: content=base64.b64decode(d.get('data',''),validate=True)
            except Exception: raise ApiError(400,'이미지 파일을 확인하세요.')
            if not content or len(content)>4*1024*1024: raise ApiError(400,'이미지는 4MB 이하여야 합니다.')
            valid=(mime=='image/png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/jpeg' and content.startswith(b'\xff\xd8\xff')) or (mime=='image/webp' and content.startswith(b'RIFF') and content[8:12]==b'WEBP')
            if not valid: raise ApiError(400,'이미지 형식을 확인하세요.')
            # These are public event artwork assets; never upload private documents here.
            folder=ROOT/'public/assets';name=uid()+{'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}[mime]
            (folder/name).write_bytes(content);audit(db,e,actor,'image.upload',name);return {'url':'/assets/'+name}
        if route=='zone' and method=='POST':
            need('owner','content');zid=uid();color=d.get('color','#00a3c4')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',color): raise ApiError(400,'색상을 확인하세요.')
            db.execute('INSERT INTO zones VALUES(?,?,?,?,?)',(zid,e,text(d.get('name',''),100),color,text(d.get('description',''),1000,False)));audit(db,e,actor,'zone.create',zid);return {'id':zid}
        if route=='booth' and method=='POST':
            need('owner','content');bid=d.get('id');b=db.execute('SELECT * FROM booths WHERE id=? AND event=?',(bid,e)).fetchone()
            if not b: raise ApiError(404,'부스가 없습니다.')
            zone=d.get('zone',b['zone'])
            if not db.execute('SELECT 1 FROM zones WHERE id=? AND event=?',(zone,e)).fetchone(): raise ApiError(400,'존을 확인하세요.')
            x=float(d.get('x',b['x']));y=float(d.get('y',b['y']))
            if not 0<=x<=100 or not 0<=y<=100: raise ApiError(400,'위치는 0~100% 범위입니다.')
            lat,lng=d.get('lat',b['lat']),d.get('lng',b['lng'])
            if lat is None and lng is None: pass
            else:
                try: lat,lng=map_config.point([lat,lng])
                except ValueError as error: raise ApiError(400,str(error))
            db.execute('UPDATE booths SET name=?,zone=?,description=?,code=?,building=?,x=?,y=?,lat=?,lng=?,approved=? WHERE id=?',(text(d.get('name',b['name']),200),zone,text(d.get('description',b['description']),3000,False),text(d.get('code',b['code']),50,False),text(d.get('building',b['building']),100,False),x,y,lat,lng,int(bool(d.get('approved',b['approved']))),bid))
            audit(db,e,actor,'booth.edit',bid);return {'ok':True}
        if route=='booth-access' and method=='POST':
            need('owner');b=db.execute('SELECT id,manager,qr FROM booths WHERE id=? AND event=?',(d.get('booth'),e)).fetchone()
            if not b: raise ApiError(404,'부스가 없습니다.')
            if d.get('password'):
                pw=text(d['password'],200)
                if len(pw)<10: raise ApiError(400,'비밀번호는 10자 이상입니다.')
                db.execute('UPDATE booths SET password=? WHERE id=?',(password(pw),b['id']));db.execute('DELETE FROM sessions WHERE booth=?',(b['id'],))
                audit(db,e,actor,'booth.credentials.reset',b['id'])
            else: audit(db,e,actor,'booth.credentials.view',b['id'])
            return {'manager':b['manager'],'qr':b['qr']}
        if route=='mission' and method=='POST':
            need('owner','content');kind=d.get('kind','booths')
            if kind not in ['booths','zone','zones','quiz','text']: raise ApiError(400,'미션 유형을 확인하세요.')
            refs=d.get('refs',[])
            if not isinstance(refs,list) or len(refs)>500: raise ApiError(400,'대상 목록을 확인하세요.')
            table='zones' if kind in ['zone','zones'] else 'booths'
            for ref in refs:
                if not db.execute(f'SELECT 1 FROM {table} WHERE id=? AND event=?',(ref,e)).fetchone(): raise ApiError(400,'같은 행사 안의 대상을 선택하세요.')
            mid=uid();config={}
            if kind=='quiz': config={'question':text(d.get('question',''),1000),'answer':text(d.get('answer',''),200)}
            db.execute('INSERT INTO missions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,e,text(d.get('title',''),200),text(d.get('description',''),3000,False),kind,1 if kind in ['quiz','text'] else integer(d.get('target',1),1,500),pack(refs),date_value(d.get('start')),date_value(d.get('end')),int(bool(d.get('published',True))),pack(config)))
            audit(db,e,actor,'mission.create',mid);return {'id':mid}
        if route=='review-answers' and method=='GET':
            need('owner','content');audit(db,e,actor,'mission.answers.view')
            return [dict(r,answer=decrypt(r['answer'])) for r in db.execute('SELECT a.*,m.title FROM mission_answers a JOIN missions m ON m.id=a.mission WHERE m.event=? AND m.kind="text"',(e,))]
        if route=='review-answer' and method=='POST':
            need('owner','content');m=db.execute('SELECT id FROM missions WHERE id=? AND event=? AND kind="text"',(d.get('mission'),e)).fetchone()
            if not m: raise ApiError(404,'검토할 미션이 없습니다.')
            db.execute('UPDATE mission_answers SET approved=? WHERE participant=? AND mission=?',(int(bool(d.get('approved'))),d.get('participant'),m['id']))
            audit(db,e,actor,'mission.review',m['id']);return {'ok':True}
        if route=='program' and method=='POST':
            need('owner','content');url=text(d.get('url',''),1500,False)
            if url and urlparse(url).scheme not in ['https','http']: raise ApiError(400,'외부 링크는 HTTP(S) 주소여야 합니다.')
            t=text(d.get('time',''),20)
            if not re.fullmatch(r'\d{2}:\d{2}',t): raise ApiError(400,'시각 형식을 확인하세요.')
            pid=uid();db.execute('INSERT INTO programs VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,e,text(d.get('title',''),200),text(d.get('description',''),3000,False),date_value(d.get('date'),False),t,text(d.get('place',''),200),text(d.get('building',''),100,False),text(d.get('category','세미나'),50),url));audit(db,e,actor,'program.create',pid);return {'id':pid}
        if route=='survey-config' and method=='POST':
            need('owner','survey');qs=validate_questions(d.get('questions',[]));published=bool(d.get('published'));consent=text(d.get('consent',''),6000,False)
            if published and (not consent or not qs): raise ApiError(400,'공개 전 설문 문항과 검토한 개인정보 안내를 등록하세요.')
            if db.execute('SELECT 1 FROM responses WHERE event=?',(e,)).fetchone(): raise ApiError(409,'응답이 접수된 설문은 변경할 수 없습니다. 문항 변경은 새 행사에서 진행하세요.')
            db.execute('INSERT INTO surveys VALUES(?,?,?,?,?,?,?) ON CONFLICT(event) DO UPDATE SET title=excluded.title,questions=excluded.questions,published=excluded.published,end=excluded.end,consent=excluded.consent',(e,text(d.get('title','행사 전체 설문'),200),pack(qs),int(published),date_value(d.get('end')),consent,0))
            audit(db,e,actor,'survey.configure');return {'ok':True}
        if route=='templates' and method=='POST':
            need('owner','survey');return {'questions':templates(d.get('names',[]))}
        if route=='parse-survey' and method=='POST':
            need('owner','survey');raw=text(d.get('text',''),20000);blocks=re.split(r'(?m)^\s*\d+[.)]\s*',raw);questions=[]
            for block in blocks:
                lines=[x.strip().lstrip('-• ').strip() for x in block.splitlines() if x.strip()]
                if not lines: continue
                label=lines[0];opts=[v.strip() for line in lines[1:] for v in line.split('/') if v.strip()]
                multi='복수' in label;questions.append({'id':uid(),'label':label,'type':'multi' if multi and opts else 'choice' if opts else 'text','options':opts,'required':'선택' not in label or multi,'review':True})
            return {'questions':questions[:60],'notice':'자동 인식 초안입니다. 유형·선택지·필수 여부를 확인하세요.'}
        if route=='notice' and method=='POST':
            need('owner','operations','content');target=d.get('target','public');severity=d.get('severity','normal');refs=d.get('refs',[])
            if target not in ['public','all','zone','booth'] or severity not in ['normal','important','urgent'] or not isinstance(refs,list): raise ApiError(400,'대상·중요도를 확인하세요.')
            if target in ['zone','booth']:
                for ref in refs:
                    tbl='zones' if target=='zone' else 'booths'
                    if not db.execute(f'SELECT 1 FROM {tbl} WHERE id=? AND event=?',(ref,e)).fetchone(): raise ApiError(400,'해당 행사 대상을 선택하세요.')
            nid=uid();db.execute('INSERT INTO notices VALUES(?,?,?,?,?,?,?,?,?)',(nid,e,text(d.get('title',''),200),text(d.get('body',''),5000),severity,target,pack(refs),int(bool(d.get('ack'))),now()));audit(db,e,actor,'notice.send',nid);return {'id':nid}
        if route=='inquiry-state' and method=='POST':
            need('owner','operations');status=d.get('status')
            if status not in ['received','confirmed','progress','resolved']: raise ApiError(400,'처리 상태를 확인하세요.')
            cur=db.execute('UPDATE inquiries SET status=?,assignee=?,updated=? WHERE id=? AND event=?',(status,text(d.get('assignee',''),100,False),now(),d.get('inquiry'),e))
            if not cur.rowcount: raise ApiError(404,'문의가 없습니다.')
            audit(db,e,actor,'inquiry.status',d['inquiry']);return {'ok':True}
        if route=='reports' and method=='GET':
            need('owner','safety','support');sensitive=q.get('sensitive',['0'])[0]=='1'
            if sensitive: need('support')  # owner alone does not grant victim-support access
            else: need('owner','safety')
            clause='kind!="safety"' if sensitive else 'kind="safety"'
            audit(db,e,actor,'reports.view',{'sensitive':sensitive})
            return [dict(r,location=decrypt(r['location']),body=decrypt(r['body']),reply=decrypt(r['reply'])) for r in db.execute(f'SELECT * FROM reports WHERE event=? AND {clause} ORDER BY created DESC',(e,))]
        if route=='report-state' and method=='POST':
            r=db.execute('SELECT kind FROM reports WHERE id=? AND event=?',(d.get('id'),e)).fetchone()
            if not r: raise ApiError(404,'신고가 없습니다.')
            need('support') if r['kind']!='safety' else need('owner','safety')
            status=d.get('status')
            if status not in ['received','confirmed','progress','resolved']: raise ApiError(400,'상태를 확인하세요.')
            db.execute('UPDATE reports SET status=?,reply=?,updated=? WHERE id=?',(status,encrypt(text(d.get('reply',''),3000,False)),now(),d['id']));audit(db,e,actor,'report.update',d['id']);return {'ok':True}
        if route=='invite' and method=='POST':
            need('owner');role=d.get('role')
            if role not in ['owner','content','operations','survey','safety','support','analyst']: raise ApiError(400,'역할을 확인하세요.')
            email=text(d.get('email',''),200).lower()
            if '@' not in email: raise ApiError(400,'이메일을 확인하세요.')
            token=uid()+uid();db.execute('INSERT INTO invites VALUES(?,?,?,?,?,0)',(digest(token),e,role,email,int(time.time())+86400))
            audit(db,e,actor,'invite.create',{'role':role});return {'invite':token}
        if route=='revoke' and method=='POST':
            need('owner');user=d.get('user')
            if user==s['user']: raise ApiError(400,'자신의 권한은 여기서 회수할 수 없습니다.')
            db.execute('DELETE FROM access WHERE user=? AND event=?',(user,e));db.execute('DELETE FROM sessions WHERE user=?',(user,));audit(db,e,actor,'access.revoke');return {'ok':True}
        if route=='prize' and method=='POST':
            need('owner','survey');pid=uid();db.execute('INSERT INTO prizes VALUES(?,?,?,?,0)',(pid,e,text(d.get('name',''),200),integer(d.get('count',1),1,10000)));audit(db,e,actor,'prize.create',pid);return {'id':pid}
        if route=='draw' and method=='POST':
            need('owner','survey')
            if d.get('confirmed') is not True: raise ApiError(400,'추첨 확정 확인이 필요합니다.')
            end=ev['settings'].get('entry_end','')
            if not end or day()<=end: raise ApiError(409,'응모 마감일을 설정하고 마감 후 추첨하세요.')
            prize=db.execute('SELECT * FROM prizes WHERE id=? AND event=?',(d.get('prize'),e)).fetchone()
            if not prize or prize['drawn']: raise ApiError(409,'이미 추첨했거나 없는 상품입니다.')
            candidates=[r['id'] for r in db.execute('SELECT id FROM entries WHERE event=? AND status="eligible" AND id NOT IN (SELECT entry FROM winners WHERE event=?)',(e,e))]
            # One winning entry per normalized contact across all prizes (entries enforce uniqueness).
            picked=secrets.SystemRandom().sample(candidates,min(prize['count'],len(candidates)))
            for entry in picked: db.execute('INSERT INTO winners VALUES(?,?,?,?,?,?,?)',(uid(),e,prize['id'],entry,'ready','',now()))
            db.execute('UPDATE prizes SET drawn=1 WHERE id=?',(prize['id'],));db.execute('INSERT INTO draws VALUES(?,?,?,?,?,?,?)',(uid(),e,prize['id'],actor,pack(candidates),pack(picked),now()));audit(db,e,actor,'draw.execute',{'prize':prize['id'],'count':len(picked)})
            return {'count':len(picked)}
        if route=='delivery' and method=='POST':
            need('owner','survey');status=d.get('status')
            if status not in ['ready','requested','sent','failed']: raise ApiError(400,'발송 상태를 확인하세요.')
            cur=db.execute('UPDATE winners SET status=?,note=? WHERE id=? AND event=?',(status,text(d.get('note',''),1000,False),d.get('id'),e))
            if not cur.rowcount: raise ApiError(404,'당첨 기록이 없습니다.')
            audit(db,e,actor,'delivery.update',d['id']);return {'ok':True}
        if route=='export' and method=='GET':
            kind=q.get('kind',['booths'])[0];out=io.StringIO();w=csv.writer(out)
            def safe(v):
                v=str(v if v is not None else '')
                return "'"+v if v[:1] in ['=','+','-','@','\t','\r'] else v
            if kind=='winners':
                need('owner','survey');w.writerow(['당첨번호','상품','연락처','발송 상태'])
                for r in db.execute('SELECT w.id,p.name,r.phone,w.status FROM winners w JOIN prizes p ON p.id=w.prize JOIN entries en ON en.id=w.entry JOIN responses r ON r.id=en.response WHERE w.event=?',(e,)):
                    w.writerow([safe(r['id']),safe(r['name']),safe(decrypt(r['phone'])),safe(r['status'])])
            else:
                need('owner','analyst','operations','content');w.writerow(['존','부스','오늘 고유 패스','행사 누적 고유 패스','평균 별점','평가 수'])
                for b in booth_stats(db,e): w.writerow([safe(b['zone_name']),safe(b['name']),b['today'],b['total'],b['ratings']['average'],b['ratings']['count']])
            audit(db,e,actor,'export.'+kind);self.send(200,('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="'+('giftcard-winners' if kind=='winners' else 'booth-report')+'.csv"'});return None
        if route=='analysis' and method=='GET':
            need('owner','analyst','survey');responses=db.execute('SELECT answers FROM responses WHERE event=?',(e,)).fetchall();answers=[unpack(decrypt(r['answers']),{}) for r in responses]
            result={'responses':len(answers),'questions':{},'spend':{},'carbon':{'status':'not_calculated','reason':'배출계수·비교 기준 검증 전입니다.'},'staff_responses':db.execute('SELECT COUNT(*) FROM staff_surveys s JOIN booths b ON b.id=s.booth WHERE b.event=?',(e,)).fetchone()[0]}
            survey=db.execute('SELECT questions FROM surveys WHERE event=?',(e,)).fetchone()
            for question in unpack(survey['questions'],[]) if survey else []:
                values=[a[question['id']] for a in answers if question['id'] in a];counts={}
                for value in values:
                    for v in value if isinstance(value,list) else [value]: counts[str(v)]=counts.get(str(v),0)+1
                result['questions'][question['id']]={'label':question['label'],'count':len(values),'distribution':counts if question['type'] not in ['text','number'] else {},'total':sum(v for v in values if isinstance(v,(float,int))) if question['type']=='number' else None}
            for field in ['food','lodging','shopping','local_transport']:
                values=[a[field] for a in answers if isinstance(a.get(field),(float,int))]
                result['spend'][field]={'responses':len(values),'sum':sum(values),'average':round(sum(values)/len(values)) if values else None}
            return result
        if route=='audit' and method=='GET':
            need('owner');return [dict(r) for r in db.execute('SELECT * FROM audit WHERE event=? ORDER BY id DESC LIMIT 200',(e,))]
        if route=='purge-contact' and method=='POST':
            need('owner')
            if d.get('confirmation')!=ev['name']: raise ApiError(400,'삭제 확인에 행사명을 입력하세요.')
            db.execute('UPDATE responses SET phone="",answers=? WHERE event=?',(encrypt('{}'),e));audit(db,e,actor,'privacy.purge');return {'ok':True,'warning':'설문 원자료와 연락처를 삭제했습니다. 집계 자료는 사전에 내보내세요. 백업 삭제는 별도 절차입니다.'}
        raise ApiError(404,'지원하지 않는 API입니다.')


def main():
    initialize()
    host=os.environ.get('HOST','127.0.0.1');port=int(os.environ.get('PORT','8000'))
    print(f'Festival development server listening on {host}:{port}',flush=True)
    print('First administrator setup is available at /manage on local access only.',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__=='__main__': main()
