"""HTTP coverage for encrypted, event-scoped quiz runs and team allocation."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

import test_workflows as support
from test_workflows import app,Client
from test_mission_quiz import choice,config


class QuizWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous=app.DATA;app.DATA=Path(tempfile.mkdtemp(prefix='festival-rich-quiz-'));app.RATE.clear();app.initialize()
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);support.BASE='http://127.0.0.1:'+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.admin=Client();cls.admin.token=cls.admin.ok('/api/setup','POST',{'email':'quiz@example.test','password':'rich-quiz-owner-password','name':'Quiz owner'})['token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();shutil.rmtree(app.DATA);app.DATA=cls.previous

    def event(self):
        e=self.admin.ok('/api/events','POST',{'name':'Quiz test','venue':'Test hall','start':app.day(),'end':app.day()})['id']
        self.admin.ok(self.path(e,'settings'),'POST',{'status':'active'});return e

    def path(self,e,route):return '/api/events/'+e+'/'+route
    def participant(self,e):
        c=Client();pid=c.ok(self.path(e,'pass'),'POST',{})['participant']['id'];return c,pid
    def mission(self,e,config,kind='quiz'):
        return self.admin.ok(self.path(e,'mission'),'POST',{'title':'Quiz or survey','kind':kind,'config':config,'published':True})['id']
    def start(self,p,e,m):return p.ok(self.path(e,'quiz-session'),'POST',{'mission':m})
    def view(self,p,e,m):return p.ok(self.path(e,'quiz-session')+'?mission='+m)
    def answer(self,p,e,m,revision,answers,key='request'):
        return p.call(self.path(e,'quiz-submit'),'POST',{'mission':m,'revision':revision,'request_id':key,'answers':answers})

    def test_01_private_keys_isolated_runs_and_idempotency(self):
        e=self.event();m=self.mission(e,config([choice(explanation='After-submit explanation')],max_attempts=1));p,pid=self.participant(e)
        self.assertEqual(self.admin.call(self.path(e,'mission'),'POST',{'title':'Bad','kind':'quiz','config':[]})[0],400)
        before=self.view(p,e,m);self.assertFalse(before['ready'])
        run=self.start(p,e,m);self.assertNotIn('answers',run['questions'][0]);self.assertNotIn('explanation',run['questions'][0])
        self.assertEqual(self.answer(p,e,m,1,{'q1':'a'},'same')[0],200)
        code,replay=self.answer(p,e,m,1,{'q1':'a'},'same');self.assertEqual(code,200);self.assertEqual(replay['questions'][0]['attempts'],1)
        self.assertEqual(replay['questions'][0]['explanation'],'After-submit explanation')
        self.assertTrue(p.ok(self.path(e,'pass'))['missions'][0]['completed'])
        second,_=self.participant(e);self.assertFalse(self.view(second,e,m)['ready'])
        self.assertEqual(second.call(self.path(e,'quiz-submit'),'POST',{'mission':m,'subject':'p:'+pid,'revision':2,'request_id':'fake','answers':{'q1':'a'}})[0],409)
        other=self.event();second.ok(self.path(other,'pass'),'POST',{})
        self.assertEqual(second.call(self.path(other,'quiz-session'),'POST',{'mission':m})[0],404)
        self.assertEqual(p.call(self.path(e,'mission-answer'),'POST',{'mission':m,'answer':'a'})[0],400)
        with app.connect() as db:
            state=db.execute('SELECT state FROM quiz_runs WHERE mission=?',(m,)).fetchone()[0]
            self.assertNotIn('answers',state);self.assertIn('answers',json.loads(app.decrypt(state)))

    def test_02_staged_and_random_sessions_are_server_enforced(self):
        e=self.event();m=self.mission(e,config([choice(),choice('q2')],mode='staged'));p,_=self.participant(e)
        first=self.start(p,e,m);self.assertEqual([q['id'] for q in first['questions']],['q1'])
        self.assertEqual(self.answer(p,e,m,1,{'q2':'a'})[0],400)
        code,next_step=self.answer(p,e,m,1,{'q1':'a'},'first');self.assertEqual(code,200);self.assertEqual(next_step['current'],'q2')
        self.assertEqual(self.answer(p,e,m,1,{'q2':'a'},'stale')[0],409)
        self.assertTrue(self.answer(p,e,m,2,{'q2':'a'},'second')[1]['completed'])
        random=self.mission(e,config([choice('r'+str(i)) for i in range(6)],mode='random',random_count=2,pass_count=2))
        run=self.start(p,e,random);again=self.start(p,e,random)
        self.assertEqual([q['id'] for q in run['questions']],[q['id'] for q in again['questions']])
        missing=next('r'+str(i) for i in range(6) if 'r'+str(i) not in {q['id'] for q in run['questions']})
        self.assertEqual(self.answer(p,e,random,1,{missing:'a'})[0],400)
        self.admin.ok(self.path(e,'settings'),'POST',{'status':'ended'})
        self.assertFalse(self.view(p,e,random)['can_write']);self.assertEqual(self.answer(p,e,random,1,{run['questions'][0]['id']:'a'})[0],409)

    def test_03_code_and_random_teams_share_credit_without_overfilling(self):
        e=self.event();m=self.mission(e,config([choice(),choice('q2')],mode='team',team_size=2,team_assignment='both'))
        p1,pid1=self.participant(e);p2,pid2=self.participant(e)
        team=p1.ok(self.path(e,'quiz-team'),'POST',{'mission':m,'action':'create','name':'친구 팀'})
        self.start(p1,e,m);self.assertEqual(self.answer(p1,e,m,1,{'q1':'a'})[0],409)
        p2.ok(self.path(e,'quiz-team'),'POST',{'mission':m,'action':'join','code':team['team']['code']})
        self.assertEqual(self.answer(p1,e,m,1,{'q1':'a'},'member1')[0],200)
        self.assertEqual(self.answer(p2,e,m,1,{'q2':'a'},'stale')[0],409)
        r=self.view(p2,e,m);self.assertTrue(r['team']['started']);self.assertEqual(r['score'],1)
        self.assertTrue(self.answer(p2,e,m,r['revision'],{'q2':'a'},'member2')[1]['completed'])
        for p in [p1,p2]:self.assertTrue(p.ok(self.path(e,'pass'))['missions'][0]['completed'])
        self.assertEqual(p2.call(self.path(e,'quiz-team'),'POST',{'mission':m,'action':'leave'})[0],409)
        people=[self.participant(e)[0] for _ in range(6)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda p:p.ok(self.path(e,'quiz-team'),'POST',{'mission':m,'action':'random'}),people))
        self.assertTrue(all(r['team']['assignment']=='random' and not r['team']['code'] for r in results))
        with app.connect() as db:
            counts=[r[0] for r in db.execute('SELECT COUNT(*) FROM quiz_members WHERE mission=? GROUP BY team',(m,))]
        self.assertEqual(sorted(counts),[2,2,2,2])
        # Leaving before the first answer frees the slot without moving another team.
        people[0].ok(self.path(e,'quiz-team'),'POST',{'mission':m,'action':'leave'})
        self.assertIsNone(self.view(people[0],e,m)['team'])

    def test_04_survey_mission_aggregate_and_published_question_lock(self):
        e=self.event();c=app.mission_quiz.validate({'questions':[choice(),{'id':'rating','type':'rating','prompt':'Rate','min':1,'max':5},{'id':'text','type':'text','prompt':'Opinion'}]},True)
        m=self.mission(e,c,'survey');p,_=self.participant(e);run=self.start(p,e,m)
        code,r=self.answer(p,e,m,run['revision'],{'q1':'b','rating':4,'text':'A fictional opinion'});self.assertEqual(code,200);self.assertTrue(r['completed'])
        self.assertTrue(p.ok(self.path(e,'pass'))['missions'][0]['completed'])
        result=self.admin.ok(self.path(e,'mission-results')+'?mission='+m)
        self.assertEqual(result['questions'][0]['distribution']['Beta'],1);self.assertEqual(result['questions'][1]['average'],4)
        self.assertEqual(result['questions'][2]['texts'],['A fictional opinion'])
        self.assertEqual(p.call(self.path(e,'mission-results')+'?mission='+m)[0],401)
        self.assertEqual(p.ok(self.path(e,'survey')),{'survey':None})
        c['questions'][0]['prompt']='Changed question'
        self.assertEqual(self.admin.call(self.path(e,'mission'),'POST',{'id':m,'revision':1,'config':c})[0],409)
        self.admin.ok(self.path(e,'mission'),'POST',{'id':m,'revision':1,'title':'Edited description'})
        self.assertTrue(p.ok(self.path(e,'pass'))['missions'][0]['completed'])

    def test_05_translation_is_display_only_and_keeps_answers_private(self):
        e=self.event();m=self.mission(e,config([choice(),{'id':'secret','type':'short','prompt':'Say the secret','answers':['private-answer-never-translated'],'explanation':'private explanation'}]))
        listing=self.admin.ok(self.path(e,'translations'))['items'];self.assertNotIn('private-answer-never-translated',json.dumps(listing));self.assertNotIn('private explanation',json.dumps(listing))
        source=next(x for x in listing if x['field']=='q.q1.choices.b')
        self.admin.ok(self.path(e,'translations/review'),'POST',{'items':[{**source,'translation':'Translated Beta','reviewed':True}]})
        p,_=self.participant(e);self.start(p,e,m);view=p.ok(self.path(e,'quiz-session')+'?mission='+m+'&lang=en')
        self.assertEqual(view['questions'][0]['choices'][1],{'id':'b','label':'Translated Beta'})
        self.assertNotIn('private-answer-never-translated',json.dumps(view))


    def test_06_survey_raw_data_purge_retains_completion_and_prevents_recollection(self):
        e=self.event();m=self.mission(e,{'version':2,'questions':[{'id':'opinion','type':'text','prompt':'Opinion'}]},'survey')
        p,_=self.participant(e);self.start(p,e,m)
        self.assertEqual(self.answer(p,e,m,1,{'opinion':'Fictional survey response'})[0],200)
        self.admin.ok(self.path(e,'purge-contact'),'POST',{'confirmation':'Quiz test'})
        result=self.view(p,e,m);self.assertTrue(result['purged']);self.assertTrue(result['completed']);self.assertEqual(result['questions'],[])
        self.assertEqual(self.answer(p,e,m,result['revision'],{'opinion':'Must not recollect'},'retry')[0],409)
        self.assertTrue(p.ok(self.path(e,'pass'))['missions'][0]['completed'])
        with app.connect() as db:
            raw=app.decrypt(db.execute('SELECT state FROM quiz_runs WHERE mission=?',(m,)).fetchone()[0]);self.assertNotIn('Fictional survey response',raw)

if __name__=='__main__':unittest.main()
