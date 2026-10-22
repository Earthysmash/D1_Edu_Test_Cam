"""Local dashboard interlock and robot-side SDK reports (not odometry)."""
import math
import threading
import time


class MotionStatus:
    def __init__(self):
        self.lock = threading.RLock()
        self.at = None
        self.requested = False
        self.report = dict(state='OFFLINE', command=[0, 0, 0], error='')

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            online = self.at is not None and now - self.at <= 1
            if not online:
                self.requested = False
            return dict(self.report, online=online, requested=self.requested,
                        state=self.report['state'] if online else 'OFFLINE')

    def heartbeat(self, data, now=None):
        state, command = data.get('state'), data.get('command')
        if state not in ('READY', 'ACTIVE', 'STOPPED', 'FAULT'):
            raise ValueError('Invalid bridge state')
        if (not isinstance(command, list) or len(command) != 3 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in command)):
            raise ValueError('Invalid velocity report')
        with self.lock:
            self.snapshot(now)  # Expired bridges must be explicitly rearmed.
            self.at = time.monotonic() if now is None else now
            self.report = dict(state=state, command=command, error=str(data.get('error', ''))[:300])
            if state in ('FAULT', 'STOPPED'):
                self.requested = False
            return self.snapshot(now)

    def control(self, action, now=None):
        with self.lock:
            state = self.snapshot(now)
            if action == 'stop':
                self.requested = False
            elif action == 'start':
                if not state['online'] or state['state'] not in ('READY', 'ACTIVE'):
                    raise ValueError('Robot bridge is not ready. Start or restart robot_follow.py.')
                self.requested = True
            else:
                raise ValueError('Expected start or stop')
            return self.snapshot(now)


def register_motion(app, motion):
    from flask import jsonify, request

    @app.get('/api/motion')
    def status():
        return jsonify(motion.snapshot())

    @app.post('/api/motion')
    def control():
        if request.headers.get('X-D1-Motion') != '1':
            return jsonify(error='Missing motion control header'), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Expected JSON object'), 400
        try:
            if data.get('action') == 'heartbeat':
                return jsonify(motion.heartbeat(data))
            return jsonify(motion.control(data.get('action')))
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
