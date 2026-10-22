import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from events import Events, register


class EventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.engine = Events(self.tmp.name, frames=3, seconds=1)
        self.ob = dict(key='1:1:red',tier='red',label='gun',track_id=1,confidence=.8,
                       reason='test',box=[0,0,10,10])

    def trigger(self):
        self.assertEqual(self.engine.observe([self.ob], 0), [])
        self.assertEqual(self.engine.observe([self.ob], .5), [])
        return self.engine.observe([self.ob], 1)[0]

    def test_confirmation_dedup_and_reentry(self):
        self.trigger()
        self.assertEqual(self.engine.observe([self.ob], 2), [])
        self.engine.observe([], 3)
        for t in (4,4.5,5):
            self.engine.observe([self.ob], t)
        self.assertEqual(self.engine.snapshot()['total'], 2)

    def test_gap_resets_confirmation(self):
        for t in (0,5,10):
            self.assertEqual(self.engine.observe([self.ob], t), [])

    def test_review_api(self):
        e=self.trigger()
        app=Flask(__name__)
        register(app,self.engine)
        c=app.test_client()
        url='/api/events/'+e['id']+'/review'
        self.assertEqual(c.post(url,json={'verdict':'confirmed'}).status_code,403)
        headers={'X-D1-Review':'1'}
        self.assertEqual(c.post(url,json={'verdict':'bad'},headers=headers).status_code,400)
        self.assertEqual(c.post(url,json={'verdict':'false_alarm'},headers=headers).status_code,200)
        self.assertEqual(c.get('/api/events').json['pending'],0)
        self.assertEqual(len((self.engine.folder/'events.jsonl').read_text().splitlines()),2)
        self.assertEqual(c.get('/evidence/not-valid.jpg').status_code,404)

    def test_dashboard_integration_without_camera(self):
        import detect_web
        def check(app, **kwargs):
            c = app.test_client()
            self.assertIn(b'D1 auto follow', c.get('/').data)
            self.assertEqual(c.get('/api/target').json['status'], 'WAITING FOR CAMERA')
            self.assertTrue(c.get('/api/target').json['stale'])
            self.assertTrue(c.get('/health').json['stale'])
            self.assertIn('OFF', c.get('/health').json['capabilities'])
            self.assertEqual(c.get('/api/events').json['total'], 0)
        with patch('sys.argv', ['detect_web.py', '--preview-only', '--event-dir', self.tmp.name,
                                '--summary', str(Path(self.tmp.name)/'counts.json')]), \
             patch('threading.Thread.start'), patch('flask.Flask.run', check):
            detect_web.main()
        self.assertTrue((Path(self.tmp.name)/'counts.json').exists())


if __name__=='__main__':
    unittest.main()
