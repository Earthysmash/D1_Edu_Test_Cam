"""Observable event review; no identity or criminality scoring."""
import json
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone


class Events:
    def __init__(self, folder, frames=3, seconds=1.0):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pending = {}
        self.items = []
        self.frames, self.seconds = frames, seconds
        self.session = uuid.uuid4().hex[:8]

    def observe(self, observations, now=None):
        now = time.monotonic() if now is None else now
        fresh = []
        with self.lock:
            keys = {o['key'] for o in observations}
            self.pending = {k: v for k, v in self.pending.items()
                            if k in keys and now-v['last'] <= 3}
            for o in {o['key']: o for o in observations}.values():
                p = self.pending.setdefault(o['key'], dict(start=now, last=now, hits=0, event=None))
                p['hits'] += 1
                p['last'] = now
                if p['event'] is not None:
                    continue
                if p['hits'] < self.frames or now-p['start'] < self.seconds:
                    continue
                event = {k: v for k, v in o.items() if k != 'key'}
                event.update(id=uuid.uuid4().hex, session=self.session,
                             time=datetime.now(timezone.utc).isoformat(), review='pending')
                self.items.append(event)
                p['event'] = event['id']
                fresh.append(dict(event))
                self._log(event)
        return fresh

    def _log(self, event):
        with (self.folder / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False)+'\n')

    def review(self, event_id, verdict):
        if verdict not in ('confirmed', 'false_alarm'):
            raise ValueError('Invalid verdict')
        with self.lock:
            for e in self.items:
                if e['id'] == event_id:
                    e['review'] = verdict
                    e['reviewed_at'] = datetime.now(timezone.utc).isoformat()
                    self._log(e)
                    return dict(e)
        raise KeyError(event_id)

    def snapshot(self):
        with self.lock:
            return dict(total=len(self.items), tiers=dict(Counter(e['tier'] for e in self.items)),
                        pending=sum(e['review']=='pending' for e in self.items),
                        events=[dict(e) for e in reversed(self.items[-100:])])


def observations(result, connection, zone, weapon_labels, covered_labels, frame_shape):
    """Track detected objects, never attribute possession using proximity."""
    if result.boxes is None or result.boxes.id is None:
        return []
    height, width = frame_shape[:2]
    out = []
    for xyxy, cls, tid, conf in zip(result.boxes.xyxy.cpu().tolist(),
                                   result.boxes.cls.cpu().tolist(),
                                   result.boxes.id.cpu().tolist(),
                                   result.boxes.conf.cpu().tolist()):
        label = result.names[int(cls)].strip().lower()
        x1, y1, x2, y2 = xyxy
        cx, cy = (x1+x2)/2/width, (y1+y2)/2/height
        if label in weapon_labels:
            tier, reason = 'red', 'Weapon-like object; possession not determined'
        elif label in covered_labels and zone and zone[0] <= cx <= zone[2] and zone[1] <= cy <= zone[3]:
            tier, reason = 'orange', 'Covered-face detection inside configured policy zone'
        else:
            continue
        out.append(dict(key=f'{connection}:{int(tid)}:{tier}', tier=tier,
                        reason=reason, label=label, track_id=int(tid),
                        confidence=round(conf, 3), box=[int(v) for v in xyxy]))
    return out


def register(app, events):
    from flask import jsonify, request, abort, send_from_directory

    @app.get('/api/events')
    def list_events():
        return jsonify(events.snapshot())

    @app.post('/api/events/<event_id>/review')
    def review_event(event_id):
        if request.headers.get('X-D1-Review') != '1':
            abort(403)
        try:
            return jsonify(events.review(event_id, (request.get_json(silent=True) or {}).get('verdict')))
        except ValueError:
            abort(400)
        except KeyError:
            abort(404)

    @app.get('/evidence/<event_id>.jpg')
    def evidence(event_id):
        if len(event_id) != 32 or any(c not in '0123456789abcdef' for c in event_id):
            abort(404)
        return send_from_directory(str(events.folder.resolve()), event_id+'.jpg')
