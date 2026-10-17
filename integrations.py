"""Server-only providers. Fixed HTTPS destinations; never expose API keys or upstream errors."""
import copy
import hashlib
import html
import json
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener
from zoneinfo import ZoneInfo

KST=ZoneInfo('Asia/Seoul')
MAX_RESPONSE=2*1024*1024

class IntegrationError(Exception): pass


def configured():
    return {'translation':{'provider':'google','configured':bool(os.environ.get('FESTIVAL_TRANSLATION_API_KEY'))},'weather':{'provider':'kma','configured':bool(os.environ.get('FESTIVAL_KMA_API_KEY'))}}


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        source,target=urlparse(req.full_url),urlparse(newurl)
        if target.scheme!='https' or source.netloc!=target.netloc:
            raise IntegrationError('외부 서비스의 다른 출처 리다이렉트를 차단했습니다.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

urlopen=build_opener(SameOriginRedirect()).open


def request_json(url, *, headers=None, body=None):
    req=Request(url,headers={'Accept':'application/json','User-Agent':'FestivalPlatform/1.0',**(headers or {})},data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,method='POST' if body is not None else 'GET')
    try:
        with urlopen(req,timeout=10) as response:
            data=response.read(MAX_RESPONSE+1)
        if len(data)>MAX_RESPONSE: raise IntegrationError('외부 서비스 응답이 너무 큽니다.')
        return json.loads(data)
    except HTTPError as error:
        if error.code in [401,403]: raise IntegrationError('외부 서비스 인증·허용 도메인·사용 권한을 확인하세요.') from None
        if error.code==429: raise IntegrationError('외부 서비스 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.') from None
        raise IntegrationError('외부 서비스 요청에 실패했습니다.') from None
    except (URLError,TimeoutError,OSError): raise IntegrationError('외부 서비스에 연결할 수 없습니다. 네트워크와 설정을 확인하세요.') from None
    except (ValueError,UnicodeDecodeError): raise IntegrationError('외부 서비스 응답 형식을 확인할 수 없습니다.') from None


def translate_public(texts):
    key=os.environ.get('FESTIVAL_TRANSLATION_API_KEY')
    if not key: raise IntegrationError('번역 API 키가 설정되지 않았습니다. 서버 보안 환경 설정에 FESTIVAL_TRANSLATION_API_KEY를 등록하세요.')
    if not isinstance(texts,list) or not texts or len(texts)>50 or any(not isinstance(v,str) or not v or len(v)>7000 for v in texts) or sum(len(v) for v in texts)>30000: raise IntegrationError('한 번에 번역할 공개 콘텐츠의 양을 줄여주세요.')
    out=request_json('https://translation.googleapis.com/language/translate/v2',headers={'Content-Type':'application/json; charset=utf-8','X-goog-api-key':key},body={'q':texts,'source':'ko','target':'en','format':'text'})
    data=out.get('data',{}) if isinstance(out,dict) else {}
    rows=data.get('translations',[]) if isinstance(data,dict) else []
    if not isinstance(rows,list) or len(rows)!=len(texts) or any(not isinstance(r,dict) or not isinstance(r.get('translatedText'),str) or not r['translatedText'] or len(r['translatedText'])>20000 for r in rows): raise IntegrationError('번역 응답이 입력과 일치하지 않습니다.')
    return [html.unescape(r['translatedText']) for r in rows]


def grid_settings(value):
    if not isinstance(value,dict): raise ValueError('날씨 설정 형식을 확인하세요.')
    result={'enabled':value.get('enabled',False),'locations':[]}
    if type(result['enabled']) is not bool: raise ValueError('날씨 사용 여부를 확인하세요.')
    locations=value.get('locations',[])
    if not isinstance(locations,list) or len(locations)>20: raise ValueError('날씨 기준 지역은 최대 20곳입니다.')
    for loc in locations:
        if not isinstance(loc,dict) or not isinstance(loc.get('name'),str) or not 1<=len(loc['name'].strip())<=100: raise ValueError('날씨 기준 지역명을 입력하세요.')
        if type(loc.get('nx')) is not int or type(loc.get('ny')) is not int or not 1<=loc['nx']<=149 or not 1<=loc['ny']<=253: raise ValueError('기상청 격자 nx(1~149)·ny(1~253)를 확인하세요.')
        result['locations'].append({'name':loc['name'].strip(),'nx':loc['nx'],'ny':loc['ny']})
    if result['enabled'] and not result['locations']: raise ValueError('날씨를 사용할 기준 지역을 등록하세요.')
    return result


def numeric(value):
    try:
        x=float(value)
        return x if math.isfinite(x) and x>-900 else None
    except (TypeError,ValueError): return None


def kma_items(response):
    if not isinstance(response,dict): raise IntegrationError('기상청 응답 형식을 확인할 수 없습니다.')
    result=response.get('response',{})
    if not isinstance(result,dict) or not isinstance(result.get('header'),dict):raise IntegrationError('기상청 응답 형식을 확인할 수 없습니다.')
    code=str(result.get('header',{}).get('resultCode',''))
    if code!='00': raise IntegrationError('기상청 자료를 가져오지 못했습니다. 키·서비스 승인·발표 시각을 확인하세요.')
    body=result.get('body',{})
    rows=body.get('items',{}) if isinstance(body,dict) else {}
    rows=rows.get('item',[]) if isinstance(rows,dict) else []
    if isinstance(rows,dict): rows=[rows]
    if not isinstance(rows,list): raise IntegrationError('기상청 자료 형식을 확인할 수 없습니다.')
    return rows


def kma_fetch(nx,ny):
    key=os.environ.get('FESTIVAL_KMA_API_KEY')
    if not key: raise IntegrationError('기상청 API 키가 설정되지 않았습니다.')
    t=datetime.now(KST);base=t-timedelta(minutes=40);forecast_base=t-timedelta(minutes=45)
    common={'serviceKey':unquote(key),'pageNo':1,'numOfRows':1000,'dataType':'JSON','nx':nx,'ny':ny}
    current_params={**common,'base_date':base.strftime('%Y%m%d'),'base_time':base.strftime('%H00')}
    rows=kma_items(request_json('https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst?'+urlencode(current_params)))
    observed={r.get('category'):numeric(r.get('obsrValue')) for r in rows if isinstance(r,dict)}
    if observed.get('T1H') is None: raise IntegrationError('기상청 현재 기온 자료가 없습니다.')
    result={'source':'기상청 초단기실황·초단기예보','observed_at':base.strftime('%Y-%m-%dT%H:00:00+09:00'),'fetched_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'current':{'temperature':observed.get('T1H'),'humidity':observed.get('REH'),'wind_speed':observed.get('WSD'),'precipitation_1h':observed.get('RN1'),'precipitation_type':observed.get('PTY')},'forecast':[],'forecast_error':None,'warning_url':'https://www.weather.go.kr/w/weather/warning/status.do','warning_note':'특보는 기상청 공식 페이지에서 확인하세요. 이 화면은 특보 자동 판정·재난 경보를 제공하지 않습니다.'}
    try:
        fc={**common,'base_date':forecast_base.strftime('%Y%m%d'),'base_time':forecast_base.strftime('%H30')}
        forecast=kma_items(request_json('https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst?'+urlencode(fc)))
        slots={}
        for r in forecast:
            if not isinstance(r,dict):continue
            date=str(r.get('fcstDate',''));clock=str(r.get('fcstTime',''))
            if len(date)!=8 or len(clock)!=4: continue
            try: stamp=datetime.strptime(date+clock,'%Y%m%d%H%M').replace(tzinfo=KST)
            except ValueError: continue
            if stamp<t-timedelta(hours=1): continue
            slot=slots.setdefault(stamp.isoformat(),{'at':stamp.isoformat()})
            if r.get('category') in ['T1H','SKY','PTY','RN1','WSD']: slot[r['category']]=numeric(r.get('fcstValue')) if r['category']!='RN1' else str(r.get('fcstValue',''))[:100]
        result['forecast']=[slots[k] for k in sorted(slots)][:6]
    except IntegrationError: result['forecast_error']='예보 갱신이 지연되고 있습니다. 현재 관측값과 공식 안내를 확인하세요.'
    return result


_CACHE={};_CACHE_LOCK=threading.Lock()

def weather(nx,ny):
    key=os.environ.get('FESTIVAL_KMA_API_KEY')
    if not key: return {'status':'not_configured','message':'기상청 API 키가 설정되지 않았습니다.','source':'기상청','forecast':[]}
    identifier=(nx,ny,hashlib.sha256(key.encode()).hexdigest())
    with _CACHE_LOCK:
        if len(_CACHE)>256:
            for old in [k for k,v in _CACHE.items() if time.monotonic()-v['at']>3600]: _CACHE.pop(old,None)
            if len(_CACHE)>256:_CACHE.pop(next(iter(_CACHE)))
        slot=_CACHE.setdefault(identifier,{'lock':threading.Lock(),'at':0,'value':None,'error':None,'retry':0})
    with slot['lock']:
        t=time.monotonic()
        if slot['value'] and t-slot['at']<300:return {**copy.deepcopy(slot['value']),'status':'ok','cached':True}
        if t>=slot['retry']:
            try:
                value=kma_fetch(nx,ny);slot.update(at=t,value=value,error=None,retry=0)
                return {**copy.deepcopy(value),'status':'ok','cached':False}
            except IntegrationError as error:slot.update(error=str(error),retry=t+60)
        if slot['value'] and t-slot['at']<3600:return {**copy.deepcopy(slot['value']),'status':'stale','message':slot['error'],'cached':True}
        return {'status':'unavailable','message':slot['error'] or '날씨 정보를 확인할 수 없습니다.','source':'기상청','forecast':[]}


def grid_from_coordinate(lat,lng):
    if isinstance(lat,bool) or isinstance(lng,bool) or not isinstance(lat,(int,float)) or not isinstance(lng,(int,float)) or not math.isfinite(lat) or not math.isfinite(lng) or not 32<=lat<=44 or not 123<=lng<=133: raise ValueError('대한민국 주변의 위도·경도를 입력하세요.')
    rad=math.pi/180;re=6371.00877/5;slat1=30*rad;slat2=60*rad;olon=126*rad;olat=38*rad
    sn=math.log(math.cos(slat1)/math.cos(slat2))/math.log(math.tan(math.pi*.25+slat2*.5)/math.tan(math.pi*.25+slat1*.5))
    sf=math.tan(math.pi*.25+slat1*.5)**sn*math.cos(slat1)/sn;ro=re*sf/(math.tan(math.pi*.25+olat*.5)**sn)
    ra=re*sf/(math.tan(math.pi*.25+lat*rad*.5)**sn);theta=(lng*rad-olon)*sn
    return {'nx':math.floor(ra*math.sin(theta)+43+.5),'ny':math.floor(ro-ra*math.cos(theta)+136+.5)}
