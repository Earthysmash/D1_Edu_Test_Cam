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
