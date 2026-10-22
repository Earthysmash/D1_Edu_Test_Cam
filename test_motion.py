import unittest
from unittest.mock import Mock, patch
from flask import Flask
from auto_target import AutoTarget, register_target
from motion_status import MotionStatus, register_motion
from robot_follow import Controller, command_for, main, ZERO


def detection(**changes):
    data = dict(motion_requested=True, stale=False, target={'track_id': 1},
                frame_age_seconds=.1, suggestion='FORWARD')
    data.update(changes)
    return data


class MotionTests(unittest.TestCase):
    def test_velocity_mapping(self):
        for action, expected in [('FORWARD', (.15,0,0)), ('TURN LEFT', (0,0,.2)),
                                 ('TURN RIGHT', (0,0,-.2)), ('HOLD', ZERO), ('STOP', ZERO)]:
            self.assertEqual(command_for(detection(suggestion=action)), expected)

    def test_fail_closed(self):
        for changes in [dict(stale=True), dict(target=None), dict(motion_requested=False),
                        dict(frame_age_seconds=2), dict(frame_age_seconds=None),
                        dict(frame_age_seconds=float('nan')), dict(frame_age_seconds=-1),
                        dict(suggestion='unknown')]:
            self.assertEqual(command_for(detection(**changes)), ZERO)
        self.assertEqual(command_for(detection(), elapsed=1), ZERO)
        self.assertEqual(command_for({}), ZERO)

    def test_real_sdk_signature_and_zero(self):
        app = Mock()
        app.getCurrentCtrlmode.return_value = 1
        app.move.return_value = 0
        control = Controller(app)
        control.step(detection())
        app.move.assert_called_with(.15, 0., 0.)
        control.step(detection(target=None))
        app.move.assert_called_with(*ZERO)
        app.move.return_value = 0x3007
        with self.assertRaises(RuntimeError):
            control.step(detection())
        app.getCurrentCtrlmode.return_value = 0
        with self.assertRaises(RuntimeError):
            control.step(detection())

    def test_interlock_expiration_requires_rearm(self):
        status = MotionStatus()
        with self.assertRaises(ValueError):
            status.control('start', 10)
        status.heartbeat(dict(state='READY', command=list(ZERO)), 10)
        self.assertTrue(status.control('start', 10)['requested'])
        self.assertFalse(status.snapshot(12)['requested'])
        self.assertFalse(status.heartbeat(dict(state='READY', command=list(ZERO)), 12)['requested'])
        status.control('start', 12)
        self.assertFalse(status.control('stop', 12)['requested'])

    def test_api_and_target_integration(self):
        app, target, motion = Flask(__name__), AutoTarget(), MotionStatus()
        register_target(app, target, motion)
        register_motion(app, motion)
        client = app.test_client()
        headers = {'X-D1-Motion': '1'}
        self.assertEqual(client.post('/api/motion', json={'action':'start'}).status_code, 403)
        client.post('/api/motion', headers=headers, json=dict(action='heartbeat', state='READY', command=[0,0,0]))
        self.assertEqual(client.post('/api/motion', headers=headers, json={'action':'start'}).status_code, 200)
        self.assertTrue(client.get('/api/target').json['motion_requested'])
        client.post('/api/motion', headers=headers, json={'action':'stop'})
        self.assertFalse(client.get('/api/target').json['motion_requested'])

    def test_network_failure_sends_final_zero(self):
        app = Mock()
        app.checkConnect.return_value = True
        app.getCurrentCtrlmode.return_value = 1
        app.move.return_value = 0
        calls = 0
        def network(base, path, data=None):
            nonlocal calls
            if path == '/api/target':
                calls += 1
                if calls >= 3:
                    raise TimeoutError('network gone')
                return detection()
            return {}
        with patch('sys.argv', ['robot_follow.py', '--sdk-root', 'fake', '--enable-motion']), \
             patch('robot_follow.load_sdk', return_value=app), \
             patch('robot_follow.exchange', side_effect=network), \
             patch('robot_follow.time.sleep'):
            self.assertEqual(main(), 1)
        self.assertIn(unittest.mock.call(.15, 0., 0.), app.move.call_args_list)
        self.assertEqual(app.move.call_args_list[-1], unittest.mock.call(*ZERO))

    def test_old_capture_time_and_invalidate(self):
        target = AutoTarget()
        target.observe(1, [dict(track_id=1, box=[20,0,50,50],confidence=.9)], (100,100), now=1)
        self.assertTrue(target.snapshot(3)['stale'])
        target.invalidate()
        self.assertIsNone(target.snapshot(3)['target'])


if __name__ == '__main__':
    unittest.main()
