# D1 Edu live camera detection

Run detection on a Windows PC using the robot camera through an SSH tunnel.
The robot camera service must already be running. This project does not start
the camera service or control robot motion.

## Install once on the PC

```powershell
python -m pip install -r requirements.txt
```

## Start with two PC terminals

Terminal 1 (keep open; replace the robot IP if needed):

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 18554:127.0.0.1:8554 firefly@192.168.234.1
```

Terminal 2, from this project directory:

```powershell
python live_demo.py
```

Open http://127.0.0.1:8080. Stop an older demo with Ctrl+C before restarting.
The camera port and `/test` RTSP path must match the robot's camera service.

## Manual target-lock dashboard

The dashboard shows live annotated detections, object counts, existing event review,
and a manual person selector. This is a stationary perception demo: it sends no
robot motion commands and has no automatic following, patrol, or reacquisition.

1. Start the camera demo as above and wait for a tracked person to appear.
2. Press **Lock target** on that person's track card. The camera highlights the
   selected person in cyan and the dashboard shows **LOCKED** with confidence
   and image bounding-box coordinates.
3. If the track disappears, camera data becomes stale (over two seconds), or the
   camera reconnects, the state becomes **TARGET LOST**. It stays lost even if
   the same track ID returns. Select a visible person manually to lock again.
4. Press **Unlock / Reset** to clear the selection.

Other object detections and event review remain visible while a target is locked.
The last observed box is in image pixels, not a map position or distance estimate.
Track IDs are temporary and can switch between people during overlap; this demo
does not verify identity. Only people with assigned tracker IDs can be selected.
The selection is shared by all browser tabs connected to this local server.

For a PC webcam smoke test without the robot: `python live_demo.py --source 0`.
Camera-only preview mode cannot lock people because detection is disabled.

Run regression checks with `python -m unittest test_events test_target_lock -v`.
On the real camera, check selection with two people, disappearance, manual reset,
and camera disconnect/reconnect before presenting the demo.

## Models

- `yolov8n.pt`: general model, filtered to person, chair, and dining table.
- `models/best.pt`: user-trained detection model with gun and knife classes.
  The launcher loads it automatically when present; otherwise it prints that
  weapon detection is OFF and runs general detection only.
- `yolo26n.pt`: used by the separate webcam example `test.py`, not the live launcher.

Weapon candidates use confidence 0.65 by default. Events require the same track
for at least three frames and one second. Review events in the dashboard.
Tracks do not identify people or establish who possesses an object.
The general object totals and weapon event totals are separate.

`--preview-only` on `detect_web.py` disables detection. Use `live_demo.py` for
the combined demo. `/health` reports status; `stale=true` means no recent output.

## Validation and limits

Model loading, blank-frame inference/tracking, dual-model startup without camera
threads, and synthetic gun/knife event mapping were checked on the development PC.
The four existing tests passed with `python -m unittest test_events.py -v`.
Weapon accuracy and the combined live camera performance have not been validated.
Two models may reduce frame rate on CPU. Dining table does not cover every table type.

Camera evidence, event logs, local counts, backups, and temporary files are excluded
from Git. Model weights are included. `README_TH.md`, `START_BANK_TH.md`, and
`LIVE_DEMO_CHECK_TH.md` contain earlier setup notes; references there to missing
custom weights describe the earlier version before `models/best.pt` was added.
