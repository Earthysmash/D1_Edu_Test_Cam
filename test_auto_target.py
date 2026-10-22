import unittest
from flask import Flask
from auto_target import AutoTarget, register_target


def person(tid, x, height=100):
    return dict(track_id=tid, box=[x-20, 0, x+20, height], confidence=.9)


class AutoTargetTests(unittest.TestCase):
    def setUp(self):
        self.target = AutoTarget()

    def observe(self, people, now=10, connection=1):
        self.target.observe(connection, people, (400, 600, 3), now)
        return self.target.snapshot(now)

    def test_selects_center_without_manual_action(self):
        result = self.observe([person(1, 50), person(2, 310)])
        self.assertEqual(result['target']['track_id'], 2)
        self.assertEqual(result['suggestion'], 'FORWARD')
        self.assertFalse(result['motion_enabled'])

    def test_switches_people_freely(self):
        self.observe([person(1, 300), person(2, 500)])
        result = self.observe([person(1, 500), person(2, 300)], 11)
        self.assertEqual(result['target']['track_id'], 2)

    def test_stop_and_automatic_return(self):
        self.observe([person(1, 300)])
        result = self.observe([], 11)
        self.assertIsNone(result['target'])
        self.assertEqual(result['suggestion'], 'STOP')
        self.assertEqual(self.observe([person(2, 300)], 12, 2)['status'], 'AUTO TRACKING')
        stale = self.target.snapshot(15)
        self.assertIsNone(stale['target'])
        self.assertEqual(stale['suggestion'], 'STOP')
        self.assertEqual(self.observe([person(3, 300)], 16, 3)['status'], 'AUTO TRACKING')

    def test_direction_and_untracked_person(self):
        for x, height, expected in [(50,100,'TURN LEFT'), (550,100,'TURN RIGHT'),
                                    (300,100,'FORWARD'), (300,300,'HOLD')]:
            result = self.observe([person(None, x, height)])
            self.assertEqual(result['suggestion'], expected)
            self.assertIsNotNone(result['target'])

    def test_api_is_read_only(self):
        app = Flask(__name__)
        register_target(app, self.target)
        client = app.test_client()
        self.assertEqual(client.get('/api/target').json['suggestion'], 'STOP')
        self.assertEqual(client.post('/api/target', json={'action':'lock'}).status_code, 405)


if __name__ == '__main__':
    unittest.main()
