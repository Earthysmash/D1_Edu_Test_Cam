"""Automatic person selection; robot_follow.py consumes the output for motion."""
import threading
import time


class AutoTarget:
    def __init__(self, max_age=1):
        self.mutex = threading.RLock()
        self.max_age = max_age
        self.at = None
        self.connection = None
        self.people = []
        self.target = None
        self.suggestion = 'STOP'

    def invalidate(self):
        with self.mutex:
            self.at, self.target, self.people = None, None, []
            self.suggestion = 'STOP'

    def observe(self, connection, people, frame_shape, now=None):
        now = time.monotonic() if now is None else now
        height, width = frame_shape[:2]
        with self.mutex:
            self.connection, self.people, self.at = connection, people, now
            # Deliberately no identity persistence: choose afresh on every frame.
            self.target = min(people, key=lambda p: abs(
                (p['box'][0] + p['box'][2]) / 2 - width / 2), default=None)
            self.suggestion = 'STOP'
            if self.target is not None:
                x1, y1, x2, y2 = self.target['box']
                offset = ((x1 + x2) / 2 - width / 2) / width
                # Image-size heuristic only, not measured range or collision checking.
                if (y2 - y1) / height >= .65:
                    self.suggestion = 'HOLD'
                elif offset < -.12:
                    self.suggestion = 'TURN LEFT'
                elif offset > .12:
                    self.suggestion = 'TURN RIGHT'
                else:
                    self.suggestion = 'FORWARD'

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.mutex:
            stale = self.at is None or now - self.at > self.max_age
            target = None if stale else self.target
            return dict(status='WAITING FOR CAMERA' if stale else
                        'AUTO TRACKING' if target else 'WAITING FOR PERSON',
                        stale=stale, connection=self.connection,
                        people=[] if stale else [dict(p) for p in self.people],
                        target=dict(target) if target else None,
                        suggestion='STOP' if stale else self.suggestion,
                        frame_age_seconds=None if self.at is None else max(0, now-self.at),
                        motion_enabled=False, mode='automatic_demo')


def register_target(app, target, motion=None):
    from flask import jsonify

    @app.get('/api/target')
    def get_target():
        data = target.snapshot()
        if motion is not None:
            state = motion.snapshot()
            data.update(motion_requested=state['requested'],
                        motion_enabled=state['online'] and state['requested'],
                        motion=state, mode='automatic_follow')
        return jsonify(data)
