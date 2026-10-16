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
    def test_02_auth_and_invite_scope(self):
        event2=self.admin.ok('/api/events','POST',{'name':'Other event'})['id']
        self.admin.ok(self.e('settings',event2),'POST',{'status':'public'})
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
        self.admin.ok(self.e('settings'),'POST',{'reporting_enabled':True})
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

if __name__=='__main__': unittest.main(verbosity=2)
