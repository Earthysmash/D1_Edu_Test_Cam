import unittest
from flask import Flask
from target_lock import TargetLock, register_target


def person(tid=7):
    return dict(track_id=tid, box=[10, 20, 80, 160], confidence=.9)


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.target = TargetLock()
        self.target.observe(1, [person()], now=10)

    def test_manual_selection_only(self):
        self.assertEqual(self.target.snapshot(10)['status'], 'UNLOCKED')
        self.assertEqual(self.target.select(1, 7, 10)['status'], 'LOCKED')
        self.target.observe(1, [person(), person(8)], 11)
        self.assertEqual(self.target.snapshot(11)['target']['track_id'], 7)

    def test_loss_is_latched_even_if_same_id_returns(self):
        self.target.select(1, 7, 10)
        self.target.observe(1, [person(8)], 11)
        self.target.observe(1, [person()], 12)
        self.assertEqual(self.target.snapshot(12)['status'], 'TARGET LOST')
        self.assertEqual(self.target.select(1, 7, 12)['status'], 'LOCKED')

    def test_reconnect_cannot_reuse_lock(self):
        self.target.select(1, 7, 10)
        self.target.observe(2, [person()], 11)
        self.assertEqual(self.target.snapshot(11)['status'], 'TARGET LOST')
        with self.assertRaises(ValueError):
            self.target.select(1, 7, 11)

    def test_stale_and_missing_selection(self):
        self.target.select(1, 7, 10)
        self.assertEqual(self.target.snapshot(13)['status'], 'TARGET LOST')
        self.assertEqual(self.target.snapshot(13)['people'], [])
        with self.assertRaises(ValueError):
            self.target.select(1, 7, 13)
        self.target.observe(1, [person()], 14)
        with self.assertRaises(ValueError):
            self.target.select(1, 99, 14)
        self.assertEqual(self.target.snapshot(14)['status'], 'TARGET LOST')
        self.target.reset()
        self.assertIsNone(self.target.snapshot(14)['target'])

    def test_capture_gap_loses_lock_without_poll(self):
        self.target.select(1, 7, 10)
        self.target.observe(1, [person()], 14)
        self.assertEqual(self.target.snapshot(14)['status'], 'TARGET LOST')

    def test_api_validation_and_control(self):
        app = Flask(__name__)
        register_target(app, self.target)
        client = app.test_client()
        headers = {'X-D1-Target': '1'}
        self.target.observe(1, [person()])
        self.assertEqual(client.post('/api/target', json={}).status_code, 403)
        for body in ([], {}, {'action':'lock', 'connection':True, 'track_id':7}):
            self.assertEqual(client.post('/api/target', json=body, headers=headers).status_code, 400)
        response = client.post('/api/target', json=dict(action='lock', connection=1, track_id=7), headers=headers)
        self.assertEqual(response.json['status'], 'LOCKED')
        self.assertFalse(response.json['motion_enabled'])
        self.assertEqual(client.post('/api/target', json=dict(action='lock', connection=2, track_id=7), headers=headers).status_code, 409)
        self.assertEqual(client.post('/api/target', json=dict(action='reset'), headers=headers).json['status'], 'UNLOCKED')


if __name__ == '__main__':
    unittest.main()
