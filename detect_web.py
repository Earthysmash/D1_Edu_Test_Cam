"""D1 camera -> YOLO -> browser. No robot motion commands."""
import argparse
from collections import Counter
import json
import os
import threading
import time
from pathlib import Path
from events import Events, observations, register
from target_lock import TargetLock, register_target


class Counts:
    """Count track IDs once per connection, not once per frame."""
    def __init__(self):
        self.seen = {}

    def add(self, connection, classes, ids, names):
        current = dict(Counter(names[int(c)] for c in classes))
        if ids is not None:
            for track_id, cls in zip(ids, classes):
                self.seen.setdefault((connection, int(track_id)), names[int(cls)])
        return {"current_count": len(classes), "current_by_class": current,
                "total_tracks": len(self.seen),
                "total_by_class": dict(Counter(self.seen.values()))}

# RTSP media must also use TCP to travel through an SSH local forward.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


class Latest:
    def __init__(self):
        self.cv = threading.Condition()
        self.value = None
        self.seq = 0
        self.at = 0.0

    def put(self, value):
        with self.cv:
            self.value = value
            self.seq += 1
            self.at = time.monotonic()
            self.cv.notify_all()

    def next(self, previous, timeout=2):
        with self.cv:
            self.cv.wait_for(lambda: self.seq != previous, timeout)
            return self.seq, self.value, self.at


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default="rtsp://192.168.234.1:8554/test")
    p.add_argument("--model", default="yolov8n.pt")
    p.add_argument("--device", default="cpu")
    p.add_argument("--imgsz", type=int, default=320)
    p.add_argument("--conf", type=float, default=0.4)
    p.add_argument("--classes", nargs="+", help='Class names to detect, e.g. person chair "dining table"')
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--preview-only", action="store_true")
    p.add_argument("--summary", default="counts.json", help="Write final counts on exit")
    p.add_argument("--event-model", help="Local custom YOLO detection weights (not included)")
    p.add_argument("--weapon-labels", default="gun,pistol,handgun,rifle,firearm")
    p.add_argument("--covered-labels", default="covered_face")
    p.add_argument("--policy-zone", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"))
    p.add_argument("--event-conf", type=float, default=0.65)
    p.add_argument("--event-seconds", type=float, default=1.0)
    p.add_argument("--event-frames", type=int, default=3)
    p.add_argument("--event-dir", default="event_data")
    args = p.parse_args()
    if not 0 < args.event_conf <= 1 or args.event_seconds < 0 or args.event_frames < 2:
        p.error("Invalid event thresholds")
    if args.policy_zone:
        x1,y1,x2,y2 = args.policy_zone
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            p.error("Zone must be normalized coordinates: 0 <= X1 < X2 <= 1, same for Y")
    if not 0 <= args.conf <= 1 or args.imgsz < 32 or not 1 <= args.port <= 65535:
        p.error("Check --conf (0..1), --imgsz (>=32), and --port (1..65535)")

    import cv2
    from flask import Flask, Response, jsonify

    if not args.preview_only:
        weights = Path(args.model).expanduser()
        if not weights.is_file():
            weights = Path(__file__).resolve().parent / args.model
        if not weights.is_file():
            p.error("Model file missing. Connect PC to Internet and run: python prepare_model.py ; "
                    "then reconnect to robot. For camera only, use --preview-only.")
        args.model = str(weights.resolve())
    model = None
    class_ids = None
    if not args.preview_only:
        from ultralytics import YOLO
        model = YOLO(args.model)
        if args.classes:
            labels = {str(name).lower(): index for index, name in model.names.items()}
            requested = [name.strip().lower() for name in args.classes]
            unknown = set(requested) - labels.keys()
            if unknown:
                p.error("Unknown model classes: " + ", ".join(sorted(unknown)))
            class_ids = [labels[name] for name in requested]

    event_model = None
    weapon_labels = {v.strip().lower() for v in args.weapon_labels.split(',') if v.strip()}
    covered_labels = {v.strip().lower() for v in args.covered_labels.split(',') if v.strip()}
    capabilities = "Weapon detection: OFF — custom weights required\nCovered-face policy: OFF — custom weights and zone required"
    if args.event_model and not args.preview_only:
        if not Path(args.event_model).is_file():
            p.error("Event model file does not exist")
        event_model = YOLO(args.event_model)
        if event_model.task != 'detect':
            p.error("Event model must be an object detection model")
        labels = {str(v).strip().lower() for v in event_model.names.values()}
        weapons = labels & weapon_labels
        covered = labels & covered_labels
        if not weapons and not covered:
            p.error("No configured event labels exist in model: " + str(sorted(labels)))
        capabilities = ("Weapon detection: " + (', '.join(sorted(weapons)) if weapons else 'OFF — labels missing')
                        + "\nCovered-face policy: " + (', '.join(sorted(covered)) if covered and args.policy_zone
                          else 'OFF — labels or policy zone missing')
                        + "\nNo possession / identity inference. Validate this model on your camera.")
    events = Events(args.event_dir, args.event_frames, args.event_seconds)
    frames, output = Latest(), Latest()
    target = TargetLock()
    stop = threading.Event()
    status_lock = threading.Lock()
    state = {"camera": "connecting", "detector": "starting", "capabilities": capabilities,
             "detection_enabled": model is not None,
             "selected_classes": args.classes or "all"}

    def update(**values):
        with status_lock:
            state.update(values)

    def capture():
        source = int(args.source) if args.source.isdecimal() else args.source
        connection = 0
        while not stop.is_set():
            cap = None
            try:
                if isinstance(source, str) and source.startswith(("rtsp://", "http://", "https://")):
                    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
                else:
                    cap = cv2.VideoCapture(source)
                if not cap.isOpened():
                    raise RuntimeError("Cannot open camera; check address/service/access")
                update(camera="connected")
                connection += 1
                while not stop.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError("Camera read failed; reconnecting")
                    frames.put((connection, frame))
            except Exception as exc:
                update(camera=str(exc))
            finally:
                if cap is not None:
                    cap.release()
            stop.wait(2)

    def detect():
        previous = 0
        counts = Counts()
        last_connection = None
        try:
            while not stop.is_set():
                seq, packet, captured = frames.next(previous)
                if seq == previous or packet is None:
                    continue
                connection, frame = packet
                previous = seq
                if time.monotonic() - captured > 5:
                    continue
                if connection != last_connection:
                    for active_model in (model, event_model):
                        predictor = getattr(active_model, 'predictor', None)
                        for tracker in getattr(predictor, 'trackers', []):
                            tracker.reset()
                    last_connection = connection
                start = time.monotonic()
                annotated = frame.copy()
                count = 0
                totals = {}
                people = []
                if model is not None:
                    result = model.track(frame, persist=True, tracker="botsort.yaml",
                                         imgsz=args.imgsz, conf=args.conf,
                                         device=args.device, classes=class_ids, verbose=False)[0]
                    annotated = result.plot()
                    count = len(result.boxes) if result.boxes is not None else 0
                    boxes = result.boxes
                    classes = boxes.cls.cpu().tolist() if boxes is not None else []
                    ids = boxes.id.cpu().tolist() if boxes is not None and boxes.id is not None else None
                    totals = counts.add(connection, classes, ids, result.names)
                    if ids is not None:
                        for tid, cls, box, confidence in zip(ids, classes,
                                boxes.xyxy.cpu().tolist(), boxes.conf.cpu().tolist()):
                            if str(result.names[int(cls)]).lower() == 'person':
                                people.append(dict(track_id=int(tid),
                                    box=[int(v) for v in box], confidence=round(confidence, 3)))
                target.observe(connection, people)
                selection = target.snapshot()
                if selection['status'] == 'LOCKED':
                    selected = selection['target']
                    x1, y1, x2, y2 = selected['box']
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 220, 0), 4)
                    cv2.putText(annotated, f"LOCKED #{selected['track_id']}",
                                (x1, max(20, y1-12)), cv2.FONT_HERSHEY_SIMPLEX,
                                .7, (255, 220, 0), 2)
                candidates = []
                if event_model is not None:
                    event_result = event_model.track(frame, persist=True, tracker="botsort.yaml",
                                                     imgsz=max(640, args.imgsz), conf=args.event_conf,
                                                     device=args.device, verbose=False)[0]
                    candidates = observations(event_result, connection, args.policy_zone,
                                              weapon_labels, covered_labels, frame.shape)
                    for candidate in candidates:
                        x1,y1,x2,y2 = candidate['box']
                        color = (80,80,255) if candidate['tier']=='red' else (0,170,255)
                        cv2.rectangle(annotated, (x1,y1), (x2,y2), color, 2)
                        cv2.putText(annotated, 'Candidate: '+candidate['label'], (x1,max(18,y1-8)),
                                    cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
                if args.policy_zone:
                    h,w = frame.shape[:2]
                    x1,y1,x2,y2 = args.policy_zone
                    cv2.rectangle(annotated,(int(x1*w),int(y1*h)),(int(x2*w),int(y2*h)),(255,180,80),2)
                new_events = events.observe(candidates)
                for event in new_events:
                    if not cv2.imwrite(str(events.folder / (event['id']+'.jpg')), annotated):
                        raise RuntimeError('Could not save event evidence')
                elapsed = time.monotonic() - start
                overlay = (f"Now: {count} | Total tracks: {totals.get('total_tracks', 0)}"
                           if model is not None else "PREVIEW ONLY - Object detection OFF")
                cv2.putText(annotated, overlay,
                            (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
                ok, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    raise RuntimeError("JPEG encoding failed")
                output.put(jpg.tobytes())
                update(detector="preview" if model is None else "running", objects=count,
                       processing_ms=round(elapsed*1000, 1), **totals)
        except Exception as exc:
            update(detector="error: " + str(exc))
            print(f"Detector stopped: {exc}", flush=True)

    app = Flask(__name__)
    register(app, events)
    register_target(app, target)

    @app.get("/")
    def index():
        return Path(__file__).with_name('dashboard.html').read_text(encoding='utf-8')

    @app.get("/health")
    def health():
        with status_lock:
            info = dict(state)
        with output.cv:
            age = time.monotonic() - output.at if output.value is not None else None
        info["frame_age_seconds"] = round(age, 1) if age is not None else None
        info["stale"] = age is None or age > 5
        return jsonify(info)

    @app.get("/stream")
    def stream():
        def generate():
            previous = 0
            while not stop.is_set():
                seq, jpg, at = output.next(previous)
                if seq == previous or jpg is None:
                    continue
                previous = seq
                if time.monotonic() - at > 5:
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame",
                        headers={"Cache-Control": "no-store"})

    for job in (capture, detect):
        threading.Thread(target=job, daemon=True).start()
    print(f"Open http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
    print("Object detection: " + ("ON" if model is not None else
          "OFF (--preview-only). Stop and run: python live_demo.py"), flush=True)
    try:
        app.run(host="127.0.0.1", port=args.port, threaded=True, use_reloader=False)
    finally:
        stop.set()
        with status_lock:
            summary = dict(state)
        summary['count_definition'] = 'Unique tracker IDs per camera connection; not guaranteed unique physical objects'
        with open(args.summary, 'w', encoding='utf-8') as file:
            json.dump(summary, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
