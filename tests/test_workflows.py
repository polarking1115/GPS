"""HTTP integration tests use a fresh disposable database and real server."""
import concurrent.futures
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

ROOT=Path(__file__).resolve().parents[1]
TEST_DATA=tempfile.mkdtemp(prefix='festival-tests-')
os.environ['FESTIVAL_DATA']=TEST_DATA
spec=importlib.util.spec_from_file_location('festival_server',ROOT/'server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class Client:
    def __init__(self): self.http=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()));self.token=''
    def call(self,path,method='GET',data=None):
        headers={'Content-Type':'application/json'}
        if self.token: headers['Authorization']='Bearer '+self.token
        req=Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:
            r=self.http.open(req,timeout=15);raw=r.read();ct=r.headers.get('Content-Type','');return r.status,json.loads(raw) if 'json' in ct else raw
        except HTTPError as e: return e.code,json.loads(e.read())
    def ok(self,path,method='GET',data=None):
        status,r=self.call(path,method,data)
        if status!=200: raise AssertionError((path,status,r))
        return r

class Workflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global BASE
        app.initialize();cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);BASE='http://127.0.0.1:'+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.admin=Client();r=cls.admin.ok('/api/setup','POST',{'email':'owner@example.test','password':'a-strong-test-password','name':'Owner'});cls.admin.token=r['token']
        cls.event='youth-expo'
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();shutil.rmtree(TEST_DATA)
    def e(self,route,e=None):return '/api/events/'+(e or self.event)+'/'+route
    def participant(self):
        p=Client();r=p.ok(self.e('pass'),'POST',{});self.assertIn('id',r['participant']);return p
    def survey(self):
        self.admin.ok(self.e('settings'),'POST',{'entry_gate':'all','survey_gate':'all','entry_end':'2099-01-01'})
        self.admin.ok(self.e('survey-config'),'POST',{'title':'Test survey','questions':[{'id':'score','label':'만족도','type':'choice','options':['좋음','보통'],'required':True}],'published':True,'consent':'테스트 전용 수집 목적·항목·보관·거부 안내','end':'2099-01-01'})
    def body(self,phone='010-1234-5678'):
        return {'answers':{'score':'좋음'},'age_group':'14plus','survey_consent':True,'phone':phone,'lottery_consent':True}
    def test_01_public_boundaries_and_bootstrap(self):
        status,body=Client().call('/api/setup','POST',{'email':'x','password':'x'})
        self.assertEqual(status,409)
        public=Client().ok('/api/events/youth-expo')
        for b in public['booths']:
            for key in ['password','manager','qr','contact']: self.assertNotIn(key,b)
        self.assertEqual(Client().call(self.e('admin'))[0],401)
    def test_01_seed_english_and_review_preservation(self):
        english=Client().ok('/api/events/youth-expo?lang=en')
        self.assertEqual(english['event']['name'],'22nd Korea Youth Expo')
        self.assertEqual(english['translation']['missing'],0)
        self.assertNotIn('샘플',english['notices'][0]['body'])
        self.assertEqual(Client().ok(self.e('pass')+'?lang=en')['missions'][0]['title'],'Booth Explorer')
        # Starting again must not replace a reviewed translation written by the owner.
        source=next(x for x in self.admin.ok(self.e('translations'))['items'] if x['kind']=='event' and x['field']=='name')
        self.admin.ok(self.e('translations/review'),'POST',{'items':[{**source,'translation':'Organizer title','reviewed':True}]})
        app.initialize()
        self.assertEqual(Client().ok('/api/events/youth-expo?lang=en')['event']['name'],'Organizer title')
        self.admin.ok(self.e('translations/review'),'POST',{'items':[{**source,'translation':'22nd Korea Youth Expo','reviewed':True}]})

    def test_02_auth_and_invite_scope(self):
        event2=self.admin.ok('/api/events','POST',{'name':'Other event'})['id']
        self.admin.ok(self.e('settings',event2),'POST',{'status':'public','venue':'Test hall','start':app.day(),'end':app.day()})
        invite=self.admin.ok(self.e('invite'),'POST',{'email':'content@example.test','role':'content'})['invite']
        c=Client();c.ok('/api/accept-invite','POST',{'invite':invite,'name':'Editor','password':'another-strong-password'})
        self.assertEqual(c.call('/api/accept-invite','POST',{'invite':invite,'name':'Editor','password':'another-strong-password'})[0],400)
        c.token=c.ok('/api/login','POST',{'email':'content@example.test','password':'another-strong-password'})['token']
        self.assertEqual(c.call(self.e('admin'))[0],200)
        self.assertEqual(c.call(self.e('admin',event2))[0],403)
        self.assertEqual(c.call(self.e('draw'),'POST',{'prize':'missing','confirmed':True})[0],403)
        self.assertEqual(c.call(self.e('reports')+'?sensitive=1')[0],403)
        self.assertEqual(self.admin.call(self.e('reports')+'?sensitive=1')[0],403)
    def test_03_qr_concurrent_certification_state_and_ratings(self):
        access=self.admin.ok(self.e('booth-access'),'POST',{'booth':'booth-1','password':'shared-test-password'})
        staff=Client();staff.token=staff.ok('/api/booth-login','POST',{'manager':access['manager'],'password':'shared-test-password','display':'Staff A'})['token']
        another=Client();another.token=another.ok('/api/booth-login','POST',{'manager':access['manager'],'password':'shared-test-password','display':'Staff B'})['token']
        self.assertEqual(staff.call(self.e('booth-data')+'?booth=booth-2')[0],403)
        code,svg=staff.call(self.e('qr.svg')+'?booth=booth-1');self.assertEqual(code,200);self.assertIn(b'<svg',svg)
        p=self.participant();qr=access['qr']
        self.assertEqual(p.call(self.e('certify'),'POST',{'qr':qr,'score':6})[0],400)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda _:p.call(self.e('certify'),'POST',{'qr':qr,'score':None})[0],range(5)))
        self.assertTrue(all(x==200 for x in results))
        data=self.admin.ok(self.e('admin'));b=next(b for b in data['booths'] if b['id']=='booth-1');self.assertEqual(b['total'],1);self.assertEqual(b['ratings']['count'],0)
        p.ok(self.e('certify'),'POST',{'qr':qr,'score':4})
        staff.ok(self.e('booth-update'),'POST',{'booth':'booth-1','status':'paused'})
        self.assertEqual(p.call(self.e('certify'),'POST',{'qr':qr,'score':5})[0],409)
        self.assertEqual(another.ok(self.e('booth-data')+'?booth=booth-1')['booth']['status'],'paused')
        staff.ok(self.e('booth-update'),'POST',{'booth':'booth-1','status':'open'})
        b=staff.ok(self.e('booth-data')+'?booth=booth-1')['booth'];self.assertEqual(b['ratings']['average'],4)
        self.admin.ok(self.e('booth-access'),'POST',{'booth':'booth-1','password':'replacement-password'})
        self.assertEqual(staff.call(self.e('booth-data')+'?booth=booth-1')[0],401)
    def test_04_booth_registration_and_approval(self):
        c=Client();r=c.ok('/api/booth-register','POST',{'event':self.event,'zone':'future','name':'New booth','description':'Try this','organization':'Test','password':'registration-password','contact':'private@example.test'})
        self.assertNotIn(r['id'],[b['id'] for b in c.ok('/api/events/youth-expo')['booths']])
        self.admin.ok(self.e('booth'),'POST',{'id':r['id'],'approved':True,'x':25,'y':40,'code':'T-01'})
        self.assertIn(r['id'],[b['id'] for b in c.ok('/api/events/youth-expo')['booths']])
    def test_05_survey_duplicate_phone_race_and_gate(self):
        self.survey();p1=self.participant();p2=self.participant()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            rs=list(pool.map(lambda p:p.ok(self.e('survey'),'POST',self.body()),[p1,p2]))
        self.assertEqual(sum(r['entered'] for r in rs),1)
        self.assertIn('duplicate_contact',[r['reason'] for r in rs])
        self.assertTrue(p1.ok(self.e('survey'),'POST',self.body())['already'])
        child=self.participant();d=self.body('010-8765-4321');d['age_group']='under14'
        self.assertEqual(child.call(self.e('survey'),'POST',d)[0],403)
        self.assertEqual(self.admin.call(self.e('survey-config'),'POST',{'title':'Change','questions':[]})[0],409)
        self.admin.ok(self.e('settings'),'POST',{'survey_gate':'missions','required_missions':2})
        newcomer=self.participant();self.assertEqual(newcomer.call(self.e('survey'),'POST',self.body('010-9999-8888'))[0],403)
        self.admin.ok(self.e('settings'),'POST',{'survey_gate':'all'})
        with app.connect() as db:
            raw=db.execute('SELECT phone,answers FROM responses LIMIT 1').fetchone();self.assertNotIn('010',raw['phone']);self.assertNotIn('좋음',raw['answers'])
    def test_06_mission_progress_and_zone_sum(self):
        p=self.participant()
        for bid in ['booth-1','booth-2','booth-3']:
            r=self.admin.ok(self.e('booth-access'),'POST',{'booth':bid});p.ok(self.e('certify'),'POST',{'qr':r['qr']})
        ms=p.ok(self.e('pass'))['missions'];self.assertTrue(next(m for m in ms if m['id']=='explorer')['completed']);self.assertTrue(next(m for m in ms if m['id']=='zones')['completed'])
        a=self.admin.ok(self.e('admin'));future=next(z for z in a['zones'] if z['id']=='future')
        self.assertEqual(future['total'],sum(b['total'] for b in a['booths'] if b['zone']=='future'))
    def test_07_notice_confirmation_inquiry_and_messages(self):
        access=self.admin.ok(self.e('booth-access'),'POST',{'booth':'booth-2','password':'staff-inquiry-password'})
        c=Client();c.token=c.ok('/api/booth-login','POST',{'manager':access['manager'],'password':'staff-inquiry-password','display':'Staff C'})['token']
        n=self.admin.ok(self.e('notice'),'POST',{'title':'Heads up','body':'Please confirm','target':'zone','refs':['future'],'ack':True,'severity':'important'})['id']
        c.ok(self.e('ack'),'POST',{'booth':'booth-2','notice':n});c.ok(self.e('ack'),'POST',{'booth':'booth-2','notice':n})
        ns=self.admin.ok(self.e('admin'))['notices'];self.assertEqual(len(next(x for x in ns if x['id']==n)['confirmed']),1)
        inquiry=c.ok(self.e('inquiry'),'POST',{'booth':'booth-2','category':'시설·장비','urgent':False,'title':'Table','body':'Need a table'})['id']
        self.admin.ok(self.e('message'),'POST',{'inquiry':inquiry,'body':'On the way'})
        self.admin.ok(self.e('inquiry-state'),'POST',{'inquiry':inquiry,'status':'progress','assignee':'Operator'})
        item=next(i for i in c.ok(self.e('booth-data')+'?booth=booth-2')['inquiries'] if i['id']==inquiry)
        self.assertEqual(item['status'],'progress');self.assertEqual(len(item['messages']),2)
    def test_08_sensitive_report_privileges(self):
        p=self.participant();payload={'kind':'camera','location':'Building','body':'A suspicious device'}
        self.assertEqual(p.call(self.e('report'),'POST',payload)[0],409)
        self.admin.ok(self.e('settings'),'POST',{'reporting_enabled':True,'safety_phone':'02-000-0000'})
        rid=p.ok(self.e('report'),'POST',payload)['id'];self.assertEqual(self.admin.call(self.e('reports')+'?sensitive=1')[0],403)
        i=self.admin.ok(self.e('invite'),'POST',{'email':'support@example.test','role':'support'})['invite']
        c=Client();c.ok('/api/accept-invite','POST',{'invite':i,'name':'Support','password':'support-test-password'});c.token=c.ok('/api/login','POST',{'email':'support@example.test','password':'support-test-password'})['token']
        reports=c.ok(self.e('reports')+'?sensitive=1');self.assertIn(rid,[r['id'] for r in reports])
        c.ok(self.e('report-state'),'POST',{'id':rid,'status':'confirmed','reply':'We are checking.'})
        self.assertEqual(next(r for r in p.ok(self.e('pass'))['reports'] if r['id']==rid)['reply'],'We are checking.')
        self.assertEqual(c.call(self.e('reports')+'?sensitive=0')[0],403)
    def test_09_draw_and_export(self):
        prize=self.admin.ok(self.e('prize'),'POST',{'name':'Mobile voucher','count':3})['id']
        self.assertEqual(self.admin.call(self.e('draw'),'POST',{'prize':prize,'confirmed':True})[0],409)
        self.admin.ok(self.e('settings'),'POST',{'entry_end':'2000-01-01'})
        r=self.admin.ok(self.e('draw'),'POST',{'prize':prize,'confirmed':True});self.assertGreater(r['count'],0)
        self.assertEqual(self.admin.call(self.e('draw'),'POST',{'prize':prize,'confirmed':True})[0],409)
        status,csv=self.admin.call(self.e('export')+'?kind=winners');self.assertEqual(status,200);self.assertIn(b'010',csv)
        analysis=self.admin.ok(self.e('analysis'));self.assertEqual(analysis['carbon']['status'],'not_calculated')
    def test_10_cross_site_requests_and_isolation(self):
        req=Request(BASE+'/api/login',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://attacker.test'},method='POST')
        with self.assertRaises(HTTPError) as c: build_opener().open(req)
        self.assertEqual(c.exception.code,403)
        other=self.admin.ok('/api/events','POST',{'name':'Private draft'})['id']
        self.assertEqual(Client().call('/api/events/'+other)[0],401)
        clone=self.admin.ok('/api/events','POST',{'name':'Clone','copy':self.event})['id']
        a=self.admin.ok(self.e('admin',clone));self.assertEqual(a['stats']['participants'],0);self.assertEqual(a['stats']['responses'],0);self.assertEqual(a['stats']['entries'],0);self.assertGreater(len(a['booths']),0);self.assertTrue(all(not b['approved'] and b['status']=='closed' for b in a['booths']))

    def test_11_geo_settings_roundtrip_and_validation(self):
        maps=[{'name':'센터','image':'/assets/youth-hero.png','geofence':{'enabled':True,'entrance':[34.75,127.75],'bounds':[[34.74,127.74],[34.76,127.76]],'dwell_ms':3000}}]
        config={'center':[34.75,127.75],'zoom':17,'basemap':'satellite','overlay':{'image':'/assets/youth-hero.png','bounds':[[34.74,127.74],[34.76,127.76]],'opacity':.5,'rotation':30}}
        self.admin.ok(self.e('settings'),'POST',{'maps':maps,'outdoor_map':config})
        public=Client().ok('/api/events/youth-expo')
        self.assertEqual(public['theme']['outdoor_map'],config)
        self.assertEqual(public['theme']['building_maps'][0]['geofence']['exit_buffer'],40)
        self.assertEqual(self.admin.call(self.e('settings'),'POST',{'outdoor_map':{'center':[True,127]}})[0],400)
        self.assertEqual(Client().ok('/api/events/youth-expo')['theme']['outdoor_map'],config)
        invalid={'nodes':[{'id':'a','name':'A','lat':34,'lng':127}],'edges':[{'from':'a','to':'missing'}]}
        self.assertEqual(self.admin.call(self.e('settings'),'POST',{'outdoor':invalid})[0],400)
        self.admin.ok(self.e('booth'),'POST',{'id':'booth-1','lat':34.75,'lng':127.75,'building':''})
        self.assertEqual(next(b for b in Client().ok('/api/events/youth-expo')['booths'] if b['id']=='booth-1')['lat'],34.75)
        self.assertEqual(self.admin.call(self.e('booth'),'POST',{'id':'booth-1','lat':None,'lng':127.75})[0],400)

    def test_12_translation_review_invalidation_and_sensitive_exclusion(self):
        def fake_translate(texts):
            self.assertNotIn('010', '\n'.join(texts));self.assertNotIn('A suspicious device','\n'.join(texts))
            return ['EN: '+t for t in texts]
        with patch.object(app.integrations,'translate_public',side_effect=fake_translate):
            generated=self.admin.ok(self.e('translations/generate'),'POST',{})
        self.assertGreater(generated['generated'],0)
        before=Client().ok('/api/events/youth-expo?lang=en')
        self.assertNotIn('EN:',before['event']['name'])
        listing=self.admin.ok(self.e('translations'))['items'];item=next(x for x in listing if x['kind']=='booth' and x['id']=='booth-1' and x['field']=='name')
        review={**item,'reviewed':True,'translation':'Reviewed booth title'}
        self.admin.ok(self.e('translations/review'),'POST',{'items':[review]})
        after=Client().ok('/api/events/youth-expo?lang=en');self.assertEqual(next(b for b in after['booths'] if b['id']=='booth-1')['name'],'Reviewed booth title')
        self.admin.ok(self.e('booth'),'POST',{'id':'booth-1','name':'새로운 원문'})
        stale=Client().ok('/api/events/youth-expo?lang=en');self.assertEqual(next(b for b in stale['booths'] if b['id']=='booth-1')['name'],'새로운 원문')
        self.assertEqual(self.admin.call(self.e('translations/review'),'POST',{'items':[review]})[0],409)
        notice=next(x for x in listing if x['kind']=='notice');notice.update(translation='Reviewed notice',reviewed=True)
        self.assertEqual(self.admin.call(self.e('translations/review'),'POST',{'items':[notice]})[0],400)
        self.admin.ok(self.e('translations/review'),'POST',{'items':[notice],'critical_confirmed':True})
        self.assertEqual(Client().call(self.e('translations'))[0],401)

    def test_13_translation_network_does_not_block_booth_writes(self):
        p=self.participant();access=self.admin.ok(self.e('booth-access'),'POST',{'booth':'booth-1'})
        def fake_translate(texts):
            # This nested request requires a separate SQLite writer while translation waits.
            p.ok(self.e('certify'),'POST',{'qr':access['qr']})
            return ['EN: '+t for t in texts]
        with patch.object(app.integrations,'translate_public',side_effect=fake_translate):self.admin.ok(self.e('translations/generate'),'POST',{})
        self.assertTrue(p.ok(self.e('pass'))['visits'])

    def test_14_weather_endpoint_and_configuration(self):
        self.assertEqual(Client().ok(self.e('weather'))['status'],'disabled')
        self.admin.ok(self.e('settings'),'POST',{'weather':{'enabled':True,'locations':[{'name':'행사장','nx':60,'ny':127}]}})
        with patch.dict('os.environ',{},clear=True):self.assertEqual(Client().ok(self.e('weather'))['status'],'not_configured')
        fake={'status':'ok','current':{'temperature':21},'forecast':[]}
        with patch.object(app.integrations,'weather',return_value=fake):
            result=Client().ok(self.e('weather'));self.assertEqual(result['location']['name'],'행사장');self.assertEqual(result['current']['temperature'],21)
        self.assertEqual(Client().call(self.e('weather')+'?location=99')[0],400)
        self.assertEqual(self.admin.call(self.e('settings'),'POST',{'weather':{'enabled':True,'locations':[]}})[0],400)
        self.assertEqual(self.admin.ok(self.e('integrations/grid'),'POST',{'lat':37.5665,'lng':126.978}),{'nx':60,'ny':127})

    def test_15_draft_dashboard_weather_requires_event_permission(self):
        draft=self.admin.ok('/api/events','POST',{'name':'Private weather event'})['id']
        self.admin.ok(self.e('settings',draft),'POST',{'weather':{'enabled':True,'locations':[{'name':'Private venue','nx':60,'ny':127}]}})
        self.assertEqual(Client().call(self.e('weather',draft))[0],404)
        self.assertEqual(Client().call(self.e('admin-weather',draft))[0],401)
        fake={'status':'ok','current':{'temperature':19},'forecast':[]}
        with patch.object(app.integrations,'weather',return_value=fake):
            self.assertEqual(self.admin.ok(self.e('admin-weather',draft))['current']['temperature'],19)
        self.assertEqual(self.admin.call(self.e('admin-weather',draft)+'?location=99')[0],400)
        invite=self.admin.ok(self.e('invite'),'POST',{'email':'weather-reader@example.test','role':'content'})['invite']
        reader=Client();reader.ok('/api/accept-invite','POST',{'invite':invite,'name':'Weather reader','password':'weather-reader-password'})
        reader.token=reader.ok('/api/login','POST',{'email':'weather-reader@example.test','password':'weather-reader-password'})['token']
        with patch.object(app.integrations,'weather',return_value=fake):
            self.assertEqual(reader.ok(self.e('admin-weather'))['current']['temperature'],19)
        self.assertEqual(reader.call(self.e('admin-weather',draft))[0],403)
        access=self.admin.ok(self.e('booth-access'),'POST',{'booth':'booth-1','password':'weather-staff-password'})
        staff=Client();staff.token=staff.ok('/api/booth-login','POST',{'manager':access['manager'],'password':'weather-staff-password','display':'Staff'})['token']
        self.assertEqual(staff.call(self.e('admin-weather'))[0],403)

    def test_16_key_visual_validation_permissions_and_copy(self):
        preferences={'layout':'background','show_title':False,'show_slogan':True,'title_size':40,'align':'right','text_color':'#ffffff','surface_color':'#102b55','overlay_tone':'dark','overlay_opacity':65,'position_x':80,'position_y':25,'zoom':140,'fit':'cover','poster':'/assets/youth-hero.png'}
        self.assertEqual(Client().call(self.e('settings'),'POST',{'key_visual':preferences})[0],401)
        editor=Client();editor.token=editor.ok('/api/login','POST',{'email':'content@example.test','password':'another-strong-password'})['token']
        self.assertEqual(editor.call(self.e('settings'),'POST',{'key_visual':preferences})[0],403)
        self.admin.ok(self.e('settings'),'POST',{'key_visual':preferences})
        self.assertEqual(Client().ok('/api/events/youth-expo')['theme']['key_visual'],preferences)
        for bad in [{'layout':'unsafe'}, {'show_title':'false'}, {'show_slogan':0}, {'title_size':True}, {'zoom':201}, {'position_x':-1}, {'position_y':1.5}, {'overlay_opacity':81}, {'text_color':'red;display:none'}, {'poster':'https://example.test/poster.png'}, {'poster':'/assets/../../secret.png'}, {'custom_css':'body{}'}]:
            self.assertEqual(self.admin.call(self.e('settings'),'POST',{'key_visual':bad})[0],400,bad)
            self.assertEqual(Client().ok('/api/events/youth-expo')['theme']['key_visual'],preferences)
        self.admin.ok(self.e('settings'),'POST',{'key_visual':{'layout':'split'}})
        result=Client().ok('/api/events/youth-expo')['theme']['key_visual'];self.assertEqual(result['layout'],'split');self.assertEqual(result['zoom'],140)
        copied=self.admin.ok('/api/events','POST',{'name':'Copied visual','copy':self.event})['id']
        self.assertEqual(self.admin.ok(self.e('admin',copied))['event']['settings']['key_visual'],result)

    def test_17_display_settings_and_reviewed_map_quiz_labels(self):
        e=self.admin.ok('/api/events','POST',{'name':'제23회 테스트'})['id']
        settings={'status':'public','venue':'Test hall','start':app.day(),'end':app.day(),'header_name':'상단 이름','show_sample_notice':False,
                  'maps':[{'name':'실내 건물','image':'/assets/youth-hero.png'}],
                  'outdoor':{'nodes':[{'id':'gate','name':'정문','lat':34.7523,'lng':127.7468}],'edges':[]}}
        self.admin.ok(self.e('settings',e),'POST',settings)
        for bad in ['false',0,None]:
            self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'show_sample_notice':bad})[0],400)
        self.assertEqual(Client().call(self.e('settings',e),'POST',{'header_name':'changed'})[0],401)
        mission=self.admin.ok(self.e('mission',e),'POST',{'title':'퀴즈','kind':'quiz','question':'공개 질문','answer':'private-canonical-answer','published':True})
        listing=self.admin.ok(self.e('translations',e))['items']
        self.assertNotIn('private-canonical-answer',json.dumps(listing))
        selected=[{**x,'translation':{'setting':'App title','building':'Indoor hall','node':'Main gate','mission':'Reviewed question'}[x['kind']],'reviewed':True}
                  for x in listing if x['kind'] in ['setting','building','node'] or x['kind']=='mission' and x['field']=='question']
        self.assertEqual(len(selected),4)
        self.admin.ok(self.e('translations/review',e),'POST',{'items':selected})
        data=Client().ok('/api/events/'+e+'?lang=en')
        self.assertEqual(data['event']['name'],'제23회 테스트')
        self.assertEqual(data['theme']['header_name'],'App title')
        self.assertFalse(data['theme']['show_sample_notice'])
        self.assertEqual(data['theme']['building_maps'][0]['name'],'실내 건물')
        self.assertEqual(data['theme']['building_maps'][0]['label'],'Indoor hall')
        self.assertEqual(data['theme']['outdoor_nodes'][0]['name'],'정문')
        self.assertEqual(data['theme']['outdoor_nodes'][0]['label'],'Main gate')
        missions=Client().ok(self.e('pass',e)+'?lang=en')['missions']
        quiz=next(m for m in missions if m['id']==mission['id'])
        self.assertEqual(quiz['question'],'Reviewed question')
        self.assertNotIn('private-canonical-answer',json.dumps(quiz))
        self.admin.ok(self.e('settings',e),'POST',{'header_name':'원문 변경'})
        self.assertEqual(Client().ok('/api/events/'+e+'?lang=en')['theme']['header_name'],'원문 변경')

    def new_event(self, **settings):
        e=self.admin.ok('/api/events','POST',{'name':'독립 검토 행사','venue':'Test hall','start':app.day(),'end':app.day()})['id']
        self.admin.ok(self.e('settings',e),'POST',{'status':'active','safety_phone':'02-000-0000',**settings})
        return e

    def test_18_multiple_event_passes_keep_legacy_records(self):
        first,second=self.new_event(),self.new_event()
        p=Client();a=p.ok(self.e('pass',first),'POST',{})['participant']['id']
        # Simulate a pass made before event-scoped token storage.
        jar=next(h.cookiejar for h in p.http.handlers if isinstance(h,HTTPCookieProcessor))
        token=next(c.value for c in jar if c.name=='festival_pass')
        with app.connect() as db: db.execute('UPDATE participants SET token=? WHERE id=?',(app.digest(token),a))
        b=p.ok(self.e('pass',second),'POST',{})['participant']['id']
        self.assertNotEqual(a,b)
        for e,pid in [(first,a),(second,b),(first,a)]:
            self.assertEqual(p.ok(self.e('pass',e),'POST',{})['participant']['id'],pid)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids=list(pool.map(lambda _:p.ok(self.e('pass',second),'POST',{})['participant']['id'],range(4)))
        self.assertEqual(set(ids),{b})

    def test_19_features_gate_public_routes_without_erasing_data(self):
        e=self.new_event();p=Client();p.ok(self.e('pass',e),'POST',{})
        mission=self.admin.ok(self.e('mission',e),'POST',{'title':'Quiz','kind':'quiz','question':'Q','answer':'A'})['id']
        self.admin.ok(self.e('program',e),'POST',{'title':'Program','date':app.day(),'time':'12:00','place':'Hall'})
        self.admin.ok(self.e('settings',e),'POST',{'entry_gate':'missions'})
        self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'features':{'missions':False}})[0],400)
        self.assertTrue(self.admin.ok(self.e('admin',e))['event']['settings']['features']['missions'])
        self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'features':{'missions':'false'}})[0],400)
        self.admin.ok(self.e('settings',e),'POST',{'entry_gate':'all','features':{'missions':False,'programs':False,'survey':False}})
        self.assertEqual(p.ok('/api/events/'+e)['programs'],[])
        self.assertEqual(p.ok(self.e('pass',e))['missions'],[])
        self.assertEqual(p.ok(self.e('survey',e)),{'survey':None})
        self.assertEqual(p.call(self.e('mission-answer',e),'POST',{'mission':mission,'answer':'A'})[0],409)
        self.assertEqual(p.call(self.e('survey',e),'POST',{})[0],409)
        saved=self.admin.ok(self.e('admin',e));self.assertEqual(len(saved['missions']),1);self.assertEqual(len(saved['programs']),1)
        self.assertEqual(saved['event']['settings']['hero'],'')
        self.admin.ok(self.e('settings',e),'POST',{'features':{'missions':True,'programs':True}})
        self.assertEqual(len(p.ok(self.e('pass',e))['missions']),1)

    def test_20_copied_missions_can_be_published_with_event_scope(self):
        source=self.new_event()
        self.admin.ok(self.e('mission',source),'POST',{'title':'Copy me','kind':'booths','target':1})
        copied=self.admin.ok('/api/events','POST',{'name':'Copied','copy':source})['id']
        self.admin.ok(self.e('settings',copied),'POST',{'status':'active','venue':'Test hall','start':app.day(),'end':app.day()})
        mission=self.admin.ok(self.e('admin',copied))['missions'][0]
        self.assertFalse(mission['published'])
        self.assertEqual(self.admin.call(self.e('mission-publication',source),'POST',{'id':mission['id'],'published':True})[0],404)
        self.admin.ok(self.e('mission-publication',copied),'POST',{'id':mission['id'],'published':True})
        self.assertEqual(Client().ok(self.e('pass',copied))['missions'][0]['id'],mission['id'])

    def test_21_survey_can_close_after_responses_but_not_change_questions(self):
        e=self.new_event();config={'title':'Survey','questions':[{'id':'opinion','type':'text','label':'Opinion','required':False}],'consent':'Test consent','published':True,'end':'2099-01-01'}
        self.admin.ok(self.e('survey-config',e),'POST',config)
        p=Client();p.ok(self.e('pass',e),'POST',{})
        p.ok(self.e('survey',e),'POST',{'answers':{'opinion':'Test answer'},'age_group':'14plus','survey_consent':True})
        self.admin.ok(self.e('survey-config',e),'POST',{**config,'published':False})
        self.assertEqual(p.ok(self.e('survey',e)),{'survey':None})
        self.assertEqual(self.admin.call(self.e('survey-config',e),'POST',{**config,'questions':[]})[0],400)
        self.assertEqual(self.admin.call(self.e('survey-config',e),'POST',{**config,'title':'Changed'})[0],409)
        self.admin.ok(self.e('survey-config',e),'POST',{**config,'end':'2000-01-01'})
        self.assertFalse(p.ok(self.e('survey',e))['open'])
        self.assertTrue(p.ok(self.e('pass',e))['survey']['submitted'])

    def test_22_staff_answers_reload_and_reject_cross_event_booth(self):
        answers={'transport':'도보','distance_km':0,'staff_count':3,'food':12000}
        self.admin.ok(self.e('staff-survey'),'POST',{'booth':'booth-1','answers':answers})
        saved=self.admin.ok(self.e('booth-data')+'?booth=booth-1')['staff_answers']
        for k,v in answers.items(): self.assertEqual(saved[k],v)
        other=self.new_event()
        self.assertEqual(self.admin.call(self.e('staff-survey',other),'POST',{'booth':'booth-1','answers':{}})[0],403)
        self.assertEqual(self.admin.call(self.e('inquiry',other),'POST',{'booth':'booth-1','category':'운영 문의','title':'Cross event','body':'Must reject'})[0],403)
        self.assertEqual(self.admin.ok(self.e('booth-data')+'?booth=booth-1')['staff_answers'],saved)

    def test_23_archived_event_public_access_and_report_state(self):
        e=self.new_event(reporting_enabled=True);p=Client();p.ok(self.e('pass',e),'POST',{})
        self.admin.ok(self.e('settings',e),'POST',{'status':'ended'})
        self.assertEqual(p.call(self.e('report',e),'POST',{'kind':'safety','location':'Test','body':'Test'})[0],409)
        self.admin.ok(self.e('settings',e),'POST',{'status':'archived'})
        self.assertNotIn(e,[event['id'] for event in p.ok('/api/events')])
        self.assertEqual(p.call('/api/events/'+e)[0],401)
        self.assertEqual(p.call(self.e('pass',e))[0],404)
        self.assertEqual(p.call(self.e('report',e),'POST',{'kind':'safety','location':'Test','body':'Test'})[0],404)
        self.assertEqual(self.admin.ok(self.e('admin',e))['event']['status'],'archived')

    def test_24_role_data_and_membership_revocation(self):
        e=self.new_event();email='analyst-cleanup@example.test'
        invite=self.admin.ok(self.e('invite',e),'POST',{'email':email,'role':'analyst'})['invite']
        c=Client();c.ok('/api/accept-invite','POST',{'invite':invite,'name':'Analyst','password':'analyst-review-password'})
        c.token=c.ok('/api/login','POST',{'email':email,'password':'analyst-review-password'})['token']
        self.admin.ok(self.e('prize',e),'POST',{'name':'Test prize','count':1})
        payload=c.ok(self.e('admin',e));self.assertEqual(payload['prizes'],[]);self.assertEqual(payload['inquiries'],[])
        self.assertEqual(c.call(self.e('members',e))[0],403)
        member=self.admin.ok(self.e('members',e))[0]
        self.admin.ok(self.e('revoke',e),'POST',{'user':member['id']})
        self.assertEqual(self.admin.ok(self.e('members',e)),[])
        self.assertEqual(c.call(self.e('admin',e))[0],401)

    def test_25_program_time_is_a_real_clock_time(self):
        e=self.new_event();data={'title':'Program','date':app.day(),'place':'Hall'}
        for time in ['24:00','12:99','99:00']:
            self.assertEqual(self.admin.call(self.e('program',e),'POST',{**data,'time':time})[0],400)
        self.admin.ok(self.e('program',e),'POST',{**data,'time':'23:59'})

    def detail(self,e,kind,entity):
        return self.admin.ok(self.e('content-detail',e)+f'?kind={kind}&id={entity}')

    def test_26_publication_checks_required_fields_and_optional_warnings(self):
        e=self.admin.ok('/api/events','POST',{'name':'준비 행사'})['id']
        readiness=self.admin.ok(self.e('readiness',e));self.assertFalse(readiness['can_publish'])
        self.assertEqual({x['key'] for x in readiness['items'] if x['state']=='blocked'},{'venue','dates'})
        self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'status':'public'})[0],409)
        self.assertEqual(self.admin.ok(self.e('admin',e))['event']['status'],'draft')
        valid={'venue':'온라인 참여 페이지','start':app.day(),'end':app.day(),'status':'public'}
        self.admin.ok(self.e('settings',e),'POST',valid)
        readiness=self.admin.ok(self.e('readiness',e));self.assertTrue(readiness['can_publish'])
        self.assertTrue(any(x['state']=='warning' for x in readiness['items']))
        self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'reporting_enabled':True})[0],409)
        self.assertFalse(self.admin.ok(self.e('admin',e))['event']['settings']['reporting_enabled'])
        self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'start':'2026-11-05','end':'2026-11-04'})[0],400)
        self.assertEqual(self.admin.call(self.e('settings',e),'POST',{'entry_gate':'missions','required_missions':1})[0],409)
        m=self.admin.ok(self.e('mission',e),'POST',{'title':'Quiz','kind':'quiz','question':'Q','answer':'A'})['id']
        self.admin.ok(self.e('settings',e),'POST',{'entry_gate':'missions','required_missions':1})
        self.assertEqual(self.admin.call(self.e('mission-publication',e),'POST',{'id':m,'published':False})[0],409)
        self.assertTrue(self.detail(e,'mission',m)['published'])

    def test_27_program_edit_cancel_history_and_conflict(self):
        e=self.new_event();p=self.admin.ok(self.e('program',e),'POST',{'title':'Program','date':app.day(),'time':'12:00','place':'Hall'})['id']
        old=self.detail(e,'program',p)
        self.assertEqual(self.admin.call(self.e('program',e),'POST',{'id':p,'revision':1,'time':'13:00'})[0],400)
        self.assertEqual(self.detail(e,'program',p)['revision'],1)
        self.admin.ok(self.e('program',e),'POST',{'id':p,'revision':1,'time':'13:00','change_note':'시작 시간 변경'})
        self.assertEqual(self.admin.call(self.e('program',e),'POST',{**old,'title':'Stale edit'})[0],409)
        self.admin.ok(self.e('program',e),'POST',{'id':p,'revision':2,'status':'cancelled','change_note':'기상으로 취소'})
        public=Client().ok('/api/events/'+e)['programs'][0]
        self.assertEqual((public['id'],public['status'],public['change_note']),(p,'cancelled','기상으로 취소'))
        logs=self.admin.ok(self.e('content-history',e)+f'?kind=program&id={p}')
        self.assertEqual(len(logs),3);self.assertEqual(logs[1]['before']['time'],'12:00');self.assertEqual(logs[1]['after']['time'],'13:00')
        other=self.new_event()
        self.assertEqual(self.admin.call(self.e('program',other),'POST',{'id':p,'revision':3,'title':'Cross event'})[0],404)
        self.assertEqual(Client().call(self.e('content-history',e)+f'?kind=program&id={p}')[0],401)
        copied=self.admin.ok('/api/events','POST',{'name':'Copy without cancelled program','copy':e})['id']
        self.assertEqual(self.admin.ok(self.e('admin',copied))['programs'],[])
        source=next(x for x in self.admin.ok(self.e('translations',e))['items'] if x['kind']=='program' and x['field']=='change_note')
        self.admin.ok(self.e('translations/review',e),'POST',{'items':[{**source,'translation':'Cancelled due to weather','reviewed':True}]})
        self.assertEqual(Client().ok('/api/events/'+e+'?lang=en')['programs'][0]['change_note'],'Cancelled due to weather')

    def test_28_mission_draft_edit_lock_and_record_preservation(self):
        e=self.new_event();z=self.admin.ok(self.e('zone',e),'POST',{'name':'First zone'})['id']
        self.assertEqual(self.admin.call(self.e('mission',e),'POST',{'title':'Invalid','kind':'zone','refs':[]})[0],400)
        m=self.admin.ok(self.e('mission',e),'POST',{'title':'Draft','kind':'zone','refs':[z],'published':False})['id']
        self.admin.ok(self.e('mission',e),'POST',{'id':m,'revision':1,'kind':'quiz','refs':[],'question':'Q','answer':'A','published':True})
        p=Client();p.ok(self.e('pass',e),'POST',{});p.ok(self.e('mission-answer',e),'POST',{'mission':m,'answer':'A'})
        self.admin.ok(self.e('mission',e),'POST',{'id':m,'revision':2,'title':'안내 수정'})
        self.assertTrue(p.ok(self.e('pass',e))['missions'][0]['completed'])
        for change in [{'answer':'B'},{'start':'2099-01-01'},{'kind':'text'}]:
            self.assertEqual(self.admin.call(self.e('mission',e),'POST',{'id':m,'revision':3,**change})[0],409)
        self.admin.ok(self.e('mission-publication',e),'POST',{'id':m,'revision':3,'published':False})
        self.assertTrue(self.detail(e,'mission',m)['locked'])
        self.assertEqual(self.admin.call(self.e('mission',e),'POST',{'id':m,'revision':4,'answer':'B'})[0],409)
        self.admin.ok(self.e('mission-publication',e),'POST',{'id':m,'revision':4,'published':True})
        self.assertTrue(p.ok(self.e('pass',e))['missions'][0]['completed'])
        self.assertNotIn('config',p.ok(self.e('pass',e))['missions'][0])
        self.admin.ok(self.e('zone',e),'POST',{'id':z,'revision':1,'name':'새 존 이름'})
        self.assertEqual(self.detail(e,'zone',z)['name'],'새 존 이름')

    def test_29_notice_edit_requires_new_ack_and_keeps_old_receipt(self):
        e=self.event;access=self.admin.ok(self.e('booth-access'),'POST',{'booth':'booth-2','password':'content-notice-password'})
        staff=Client();staff.token=staff.ok('/api/booth-login','POST',{'manager':access['manager'],'password':'content-notice-password','display':'확인 담당'})['token']
        n=self.admin.ok(self.e('notice'),'POST',{'title':'안내','body':'이전 내용','target':'booth','refs':['booth-2'],'ack':True})['id']
        staff.ok(self.e('ack'),'POST',{'booth':'booth-2','notice':n,'revision':1})
        self.admin.ok(self.e('notice'),'POST',{'id':n,'revision':1,'body':'수정 내용'})
        self.assertEqual(staff.call(self.e('ack'),'POST',{'booth':'booth-2','notice':n,'revision':1})[0],409)
        notices=staff.ok(self.e('booth-data')+'?booth=booth-2')['notices'];self.assertIsNone(next(x for x in notices if x['id']==n)['confirmation'])
        staff.ok(self.e('ack'),'POST',{'booth':'booth-2','notice':n,'revision':2})
        self.admin.ok(self.e('notice'),'POST',{'id':n,'revision':2,'body':'수정 내용'})  # No-op preserves confirmation.
        self.assertEqual(self.detail(e,'notice',n)['revision'],2)
        self.assertEqual(self.admin.call(self.e('notice'),'POST',{'id':n,'revision':2,'refs':['booth-1']})[0],409)
        logs=self.admin.ok(self.e('content-history')+f'?kind=notice&id={n}')
        self.assertEqual(logs[0]['before']['acknowledgments'][0]['display'],'확인 담당')
        self.assertEqual(logs[0]['after']['body'],'수정 내용')

    def test_30_completed_mission_stays_eligible_and_legacy_lock_survives_restart(self):
        e=self.new_event();ids=[]
        for title in ['Achieved','Alternative']:
            ids.append(self.admin.ok(self.e('mission',e),'POST',{'title':title,'kind':'quiz','question':'Q','answer':'A'})['id'])
        self.admin.ok(self.e('settings',e),'POST',{'entry_gate':'missions'})
        p=Client();p.ok(self.e('pass',e),'POST',{});p.ok(self.e('mission-answer',e),'POST',{'mission':ids[0],'answer':'A'})
        self.assertEqual(self.admin.call(self.e('mission-publication',e),'POST',{'id':ids[0],'published':False})[0],409)
        self.assertTrue(p.ok(self.e('pass',e))['missions'][0]['completed'])
        app.initialize(seed=False)
        self.assertTrue(self.detail(e,'mission',ids[0])['locked'])
        self.assertTrue(p.ok(self.e('pass',e))['missions'][0]['completed'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM content_history WHERE event=?',(e,)).fetchone()[0],2)

if __name__=='__main__': unittest.main(verbosity=2)
