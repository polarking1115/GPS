import concurrent.futures
from datetime import datetime
import hashlib
import json
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
import integrations as providers


class Providers(unittest.TestCase):
    def setUp(self): providers._CACHE.clear()
    def test_keys_are_presence_only(self):
        with patch.dict('os.environ',{'FESTIVAL_TRANSLATION_API_KEY':'private-test-value','FESTIVAL_KMA_API_KEY':'private-test-weather'}):
            data=providers.configured();self.assertTrue(data['translation']['configured']);self.assertNotIn('private-test',json.dumps(data))
    def test_translation_fixed_destination_and_safe_auth(self):
        with patch.dict('os.environ',{'FESTIVAL_TRANSLATION_API_KEY':'test-key'}),patch.object(providers,'request_json',return_value={'data':{'translations':[{'translatedText':'Hello &amp; welcome'}]}}) as request:
            self.assertEqual(providers.translate_public(['안녕하세요']),['Hello & welcome'])
            args=request.call_args;self.assertEqual(args.args[0],'https://translation.googleapis.com/language/translate/v2');self.assertNotIn('test-key',args.args[0]);self.assertEqual(args.kwargs['headers']['X-goog-api-key'],'test-key');self.assertEqual(args.kwargs['body']['q'],['안녕하세요'])
    def test_missing_translation_key_and_mismatched_output(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaises(providers.IntegrationError): providers.translate_public(['hello'])
        with patch.dict('os.environ',{'FESTIVAL_TRANSLATION_API_KEY':'key'}),patch.object(providers,'request_json',return_value={'data':{'translations':[]}}),self.assertRaises(providers.IntegrationError):providers.translate_public(['hello'])
    def test_upstream_credentials_not_in_errors(self):
        for error in [HTTPError('https://example.test/?serviceKey=secret',403,'secret',{},None),URLError('serviceKey=secret')]:
            with self.subTest(error=type(error).__name__),patch.object(providers,'urlopen',side_effect=error):
                with self.assertRaises(providers.IntegrationError) as ctx:providers.request_json('https://example.test')
                self.assertNotIn('secret',str(ctx.exception))
    def test_cross_origin_redirect_rejected(self):
        from urllib.request import Request
        handler=providers.SameOriginRedirect()
        with self.assertRaises(providers.IntegrationError):handler.redirect_request(Request('https://translation.googleapis.com/api'),None,302,'redirect',{},'https://other.example.test/api')
        with self.assertRaises(providers.IntegrationError):handler.redirect_request(Request('https://translation.googleapis.com/api'),None,302,'redirect',{},'http://translation.googleapis.com/api')
    def test_malformed_provider_response_is_not_a_server_crash(self):
        for output in [None,[],{'data':'bad'},{'data':{'translations':['bad']}}]:
            with self.subTest(output=output),patch.dict('os.environ',{'FESTIVAL_TRANSLATION_API_KEY':'test'}),patch.object(providers,'request_json',return_value=output),self.assertRaises(providers.IntegrationError):providers.translate_public(['hello'])
        for output in [None,{'response':'bad'},{'response':{'header':{'resultCode':'99'}}}]:
            with self.subTest(output=output),self.assertRaises(providers.IntegrationError):providers.kma_items(output)
    def test_kma_observation_forecast_parse_and_clock(self):
        current={'response':{'header':{'resultCode':'00'},'body':{'items':{'item':[{'category':'T1H','obsrValue':'23.5'},{'category':'REH','obsrValue':'65'},{'category':'WSD','obsrValue':'2.1'}]}}}}
        forecast={'response':{'header':{'resultCode':'00'},'body':{'items':{'item':[{'category':'T1H','fcstDate':'20261017','fcstTime':'1200','fcstValue':'24'},{'category':'RN1','fcstDate':'20261017','fcstTime':'1200','fcstValue':'강수없음'}]}}}}
        actual=providers.datetime
        class Clock(actual):
            @classmethod
            def now(cls,tz=None):return actual(2026,10,17,11,20,tzinfo=providers.KST).astimezone(tz or providers.KST)
        with patch.dict('os.environ',{'FESTIVAL_KMA_API_KEY':'key%2Bencoded'}),patch.object(providers,'datetime',Clock),patch.object(providers,'request_json',side_effect=[current,forecast]) as request:
            r=providers.kma_fetch(60,127);self.assertEqual(r['current']['temperature'],23.5);self.assertEqual(r['forecast'][0]['T1H'],24)
            self.assertIn('base_time=1000',request.call_args_list[0].args[0]);self.assertIn('base_time=1030',request.call_args_list[1].args[0]);self.assertIn('serviceKey=key%2Bencoded',request.call_args_list[0].args[0])
    def test_weather_cache_single_flight_stale_and_retry(self):
        def fetch(*args):time.sleep(.02);return {'current':{'temperature':22},'forecast':[],'fetched_at':'2026-10-17T00:00:00Z'}
        with patch.dict('os.environ',{'FESTIVAL_KMA_API_KEY':'cache-test'}),patch.object(providers,'kma_fetch',side_effect=fetch) as upstream:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:r=list(pool.map(lambda _:providers.weather(60,127),range(8)))
            self.assertEqual(upstream.call_count,1);self.assertTrue(all(x['current']['temperature']==22 for x in r))
            slot=next(iter(providers._CACHE.values()));slot['at']=time.monotonic()-400
            upstream.side_effect=providers.IntegrationError('갱신 지연')
            stale=providers.weather(60,127);self.assertEqual(stale['status'],'stale');count=upstream.call_count;providers.weather(60,127);self.assertEqual(upstream.call_count,count)
            slot['at']=time.monotonic()-3700;self.assertEqual(providers.weather(60,127)['status'],'unavailable')
    def test_grid_and_weather_validation(self):
        self.assertEqual(providers.grid_from_coordinate(37.5665,126.978),{'nx':60,'ny':127})
        for v in [{'enabled':True,'locations':[]},{'enabled':True,'locations':[{'name':'site','nx':True,'ny':127}]},{'enabled':True,'locations':[{'name':'site','nx':60,'ny':999}]}]:
            with self.subTest(v=v),self.assertRaises(ValueError):providers.grid_settings(v)
        valid=providers.grid_settings({'enabled':True,'locations':[{'name':'서울','nx':60,'ny':127}]});self.assertEqual(valid['locations'][0]['nx'],60)
    def test_no_weather_values_when_key_absent(self):
        with patch.dict('os.environ',{},clear=True):
            r=providers.weather(60,127);self.assertEqual(r['status'],'not_configured');self.assertNotIn('current',r)

if __name__=='__main__':unittest.main()
