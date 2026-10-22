"""Start general detection and the local weapon model through the SSH tunnel."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='rtsp://127.0.0.1:18554/test')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--conf', type=float, default=0.25)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--follow', action='store_true', help='Person-only fast path for robot_follow.py')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    command = [
        sys.executable, str(root / 'detect_web.py'),
        '--source', args.source, '--model', str(root / 'yolov8n.pt'),
        '--device', 'cpu', '--imgsz', str(args.imgsz), '--conf', str(args.conf),
        '--port', str(args.port), '--classes', 'person', 'chair', 'dining table',
    ]
    event_model = root / 'models' / 'best.pt'
    if args.follow:
        command = command[:command.index('--classes')] + ['--classes', 'person']
        print('Person-follow mode: one model only; start robot_follow.py on D1 for motion.', flush=True)
    elif event_model.is_file():
        command.extend(['--event-model', str(event_model), '--weapon-labels', 'gun,knife'])
        print('Loading general detection + models/best.pt (gun, knife)', flush=True)
    else:
        print('models/best.pt not found: general detection only; weapon detection OFF', flush=True)
    return subprocess.call(command, cwd=root)


if __name__ == '__main__':
    raise SystemExit(main())
