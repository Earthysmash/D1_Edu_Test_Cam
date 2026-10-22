"""Manual visual target selection. Never issues robot movement commands."""
import threading
import time


class TargetLock:
    def __init__(self, max_age=2):
        self.mutex = threading.RLock()
        self.max_age = max_age
        self.at = None
        self.connection = None
        self.people = []
        self.target = None
        self.status = 'UNLOCKED'

    def _expire(self, now):
        if self.at is None or now - self.at > self.max_age:
            if self.status == 'LOCKED':
                self.status = 'TARGET LOST'
            return True
        return False

    def observe(self, connection, people, now=None):
        now = time.monotonic() if now is None else now
        with self.mutex:
            self._expire(now)
            self.connection, self.people, self.at = connection, people, now
            if self.status == 'LOCKED':
                match = next((p for p in people if
                              (connection, p['track_id']) == self.target['key']), None)
                if match is None:
                    self.status = 'TARGET LOST'
                else:
                    self.target.update(match)

    def select(self, connection, track_id, now=None):
        now = time.monotonic() if now is None else now
        with self.mutex:
            if self._expire(now) or connection != self.connection:
                raise ValueError('Camera data is stale. Wait for a fresh frame.')
            person = next((p for p in self.people if p['track_id'] == track_id), None)
            if person is None:
                raise ValueError('Person is no longer visible. Select again.')
            self.target = dict(person, key=(connection, track_id))
            self.status = 'LOCKED'
            return self.snapshot(now)

    def reset(self):
        with self.mutex:
            self.target, self.status = None, 'UNLOCKED'

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.mutex:
            stale = self._expire(now)
            return dict(status=self.status, stale=stale, connection=self.connection,
                        people=[] if stale else [dict(p) for p in self.people],
                        target=dict(self.target) if self.target else None,
                        motion_enabled=False)


def register_target(app, target):
    from flask import jsonify, request

    @app.get('/api/target')
    def get_target():
        return jsonify(target.snapshot())

    @app.post('/api/target')
    def set_target():
        if request.headers.get('X-D1-Target') != '1':
            return jsonify(error='Missing target control header'), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Expected a JSON object'), 400
        if data.get('action') == 'reset':
            target.reset()
            return jsonify(target.snapshot())
        if (data.get('action') != 'lock' or type(data.get('connection')) is not int
                or type(data.get('track_id')) is not int):
            return jsonify(error='Expected lock action, connection and track_id integers'), 400
        try:
            return jsonify(target.select(data['connection'], data['track_id']))
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
