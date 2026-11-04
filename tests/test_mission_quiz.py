import copy
import unittest

import mission_quiz as quiz


def choice(qid='q1',**extra):
    return {'id':qid,'type':'single','prompt':'Choose A','choices':[{'id':'a','label':'Alpha'},{'id':'b','label':'Beta'}],'answers':['a'],**extra}


def config(questions=None,**options):
    qs=questions or [choice()]
    return quiz.validate({'version':2,'questions':qs,'pass_count':len(qs),**options},options.pop('survey',False))


class MissionQuiz(unittest.TestCase):
    def test_all_nine_question_types_grade_without_client_scores(self):
        questions=[
            (choice(type='ox',choices=[],answers=['o']),'o','x'),
            (choice(),'a','b'),
            (choice(type='multi',answers=['a','b']),['b','a'],['a']),
            ({'id':'short','type':'short','prompt':'Text','answers':[' Hello ','안녕']},'HELLO','no'),
            ({'id':'blank','type':'blank','prompt':'Fill','blanks':[{'id':'one','label':'First','answers':['A']}]},{'one':'a'},{'one':'B'}),
            ({'id':'match','type':'match','prompt':'Match','pairs':[{'id':'a','left':'A','right':'1'},{'id':'b','left':'B','right':'2'}]},{'a':'a','b':'b'},{'a':'b','b':'a'}),
            ({'id':'order','type':'order','prompt':'Order','items':[{'id':'a','label':'A'},{'id':'b','label':'B'}],'order':['b','a']},['b','a'],['a','b']),
            (choice(type='scenario'),'a','b'),
            (choice(type='hotspot',media={'kind':'image','url':'/assets/test.png','caption':'Left and right'},regions={'a':{'x':0,'y':0,'width':50,'height':100},'b':{'x':50,'y':0,'width':50,'height':100}}),{'x':25,'y':50},{'x':75,'y':50})]
        for source,right,wrong in questions:
            with self.subTest(kind=source['type']):
                q=config([source])['questions'][0]
                self.assertTrue(quiz.evaluate(q,right)[1]);self.assertFalse(quiz.evaluate(q,wrong)[1])

    def test_survey_types_and_optional_answers(self):
        for q,value in [(choice(),'b'),(choice(type='multi'),['b']),({'id':'t','type':'text','prompt':'Opinion'},'Test'),({'id':'n','type':'number','prompt':'How many','min':0,'max':100},0),({'id':'r','type':'rating','prompt':'Rate','min':1,'max':5},3)]:
            c=quiz.validate({'questions':[q],'mode':'pack'},True)
            r=quiz.submit(c,quiz.new_run(c),{q['id']:value},True);self.assertTrue(r['completed'])
            self.assertNotIn('answers',c['questions'][0])
        c=quiz.validate({'questions':[choice(required=False)]},True)
        self.assertTrue(quiz.submit(c,quiz.new_run(c),{'q1':None},True)['completed'])

    def test_projection_hides_keys_future_questions_and_match_relationships(self):
        qs=[choice(hint='Hint',explanation='The answer is A'),choice('q2')]
        c=config(qs,mode='staged',hints=False,feedback='after_complete');r=quiz.new_run(c)
        v=quiz.view(c,r);self.assertEqual(len(v['questions']),1)
        for forbidden in ['answers','branches','explanation','hint']:self.assertNotIn(forbidden,v['questions'][0])
        with self.assertRaises(ValueError):quiz.submit(c,r,{'q2':'a'})
        r=quiz.submit(c,r,{'q1':'a'});self.assertEqual(r['current'],'q2')
        self.assertNotIn('explanation',quiz.view(c,r)['questions'][0])
        r=quiz.submit(c,r,{'q2':'a'});self.assertTrue(r['completed']);self.assertIn('explanation',quiz.view(c,r)['questions'][0])
        m={'id':'m','type':'match','prompt':'Match','pairs':[{'id':'a','left':'A','right':'1'},{'id':'b','left':'B','right':'2'}]}
        c=config([m]);r=quiz.new_run(c);v=quiz.view(c,r)['questions'][0]
        self.assertTrue({x['id'] for x in v['left']}.isdisjoint({x['id'] for x in v['right']}))
        answer={p['id']:r['match_tokens']['m'][p['id']] for p in m['pairs']}
        self.assertTrue(quiz.submit(c,r,{'m':answer})['completed'])

    def test_random_allocation_persists_and_threshold_is_reachable(self):
        c=config([choice('q'+str(i)) for i in range(8)],mode='random',random_count=3,pass_count=2)
        r=quiz.new_run(c);self.assertEqual(len(set(r['ids'])),3)
        s=quiz.submit(c,r,{r['ids'][0]:'a'});self.assertEqual(r['ids'],s['ids']);self.assertFalse(s['completed'])
        s=quiz.submit(c,s,{qid:'a' for qid in r['ids'][1:]});self.assertTrue(s['completed'])
        with self.assertRaises(ValueError):config([choice('a'),choice('b')],mode='random',random_count=1,pass_count=2)

    def test_forward_branches_and_retry(self):
        c=config([choice(branches={'b':'end'}),choice('q2')],mode='branch',pass_count=1)
        r=quiz.submit(c,quiz.new_run(c),{'q1':'b'});self.assertTrue(r['finished']);self.assertFalse(r['completed'])
        r=quiz.retry(c,r);self.assertEqual(r['attempts']['q1'],1)
        r=quiz.submit(c,r,{'q1':'a'});self.assertEqual(r['current'],'q2')
        r=quiz.submit(c,r,{'q2':'a'});self.assertTrue(r['completed'])
        with self.assertRaises(ValueError):config([choice(branches={'a':'q1'})],mode='branch')
        with self.assertRaises(ValueError):config([choice(branches={'b':'end'}),choice('q2')],mode='branch',pass_count=2)

    def test_retry_limit_and_completed_credit_never_regress(self):
        c=config(max_attempts=1);r=quiz.submit(c,quiz.new_run(c),{'q1':'b'})
        with self.assertRaises(ValueError):quiz.submit(c,r,{'q1':'a'})
        c=config(max_attempts=0);r=quiz.new_run(c)
        for _ in range(4):r=quiz.submit(c,r,{'q1':'b'})
        r=quiz.submit(c,r,{'q1':'a'});self.assertTrue(r['completed'])
        self.assertEqual(quiz.submit(c,r,{'q1':'b'}),r)

    def test_media_bounds_and_invalid_definition(self):
        for medium in ['image','audio','video']:
            c=config([choice(media={'kind':medium,'url':'/assets/file.mp4','caption':'Description'})])
            self.assertEqual(c['questions'][0]['media']['kind'],medium)
        bad=[choice(media={'kind':'image','url':'https://example.com/file.png','caption':'Description'}),choice(media={'kind':'video','url':'/assets/file.mp4'}),choice(answers=['missing']),choice('duplicate')]
        for q in bad[:-1]:
            with self.assertRaises(ValueError):config([q])
        with self.assertRaises(ValueError):config([bad[-1],bad[-1]])
        with self.assertRaises(ValueError):config([choice(),choice('q2')],mode='single')
        with self.assertRaises(ValueError):config(team_size=1)
        for malformed in [choice(media=['bad']),{'id':'b','type':'blank','prompt':'Fill','blanks':['bad']},{'id':'m','type':'match','prompt':'Match','pairs':['bad','bad']}]:
            with self.assertRaises(ValueError):config([malformed])
        with self.assertRaises(ValueError):quiz.evaluate(config([choice(type='multi')])['questions'][0],['a','a'])


if __name__=='__main__':unittest.main()
