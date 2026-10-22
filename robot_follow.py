"""Run ON D1 (Linux/Python 3.10): consume detections and call official motion SDK."""
import argparse
import importlib
import json
import math
import platform
import signal
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ZERO = (0.0, 0.0, 0.0)


def decision_reason(data, elapsed=0):
    if not data.get('motion_requested'):
        return 'PAUSED: dashboard permission is off'
    age = data.get('frame_age_seconds')
    if (type(age) not in (int, float) or not math.isfinite(age) or age < 0):
        return 'STOP: no valid frame timestamp'
    if data.get('stale', True) or age + elapsed > 1:
        return 'STOP: camera/inference data older than 1 second'
    if not data.get('target'):
        return 'STOP: no person detected'
    if data.get('suggestion') == 'HOLD':
        return 'HOLD: person box >=65% of image height (image heuristic, not measured distance)'
    return 'TARGET: ' + str(data.get('suggestion', 'UNKNOWN'))


def command_for(data, elapsed=0, speed=.15, turn=.2):
    """Reject missing, stale, or disabled detections; never reverse or strafe."""
    age = data.get('frame_age_seconds')
    if (not data.get('motion_requested') or data.get('stale', True) or
            not data.get('target') or type(age) not in (int, float) or
            not math.isfinite(age) or age < 0 or age + elapsed > 1.0):
        return ZERO
    return {'FORWARD': (speed, 0., 0.), 'TURN LEFT': (0., 0., turn),
            'TURN RIGHT': (0., 0., -turn)}.get(data.get('suggestion'), ZERO)


def checked_move(app, command):
    result = app.move(*command)
    if result != 0:
        raise RuntimeError(f'SDK move rejected: {result!r}; check SDK control ownership / firmware')


class Controller:
    def __init__(self, app, speed=.15, turn=.2):
        self.app, self.speed, self.turn = app, speed, turn
        self.mode = None

    def step(self, data, elapsed=0):
        self.mode = self.app.getCurrentCtrlmode()
        if self.mode not in (1, 3):
            raise RuntimeError(f'Robot mode={self.mode!r}, expected standing=1 or moving=3. '
                               'Use remote to stand and select SDK control.')
        command = command_for(data, elapsed, self.speed, self.turn)
        checked_move(self.app, command)
        return command

    def stop(self):
        checked_move(self.app, ZERO)


def exchange(base, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(base + path, data=body, headers={
        'Content-Type': 'application/json', 'X-D1-Motion': '1'})
    with urlopen(req, timeout=.3) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError('Invalid dashboard response')
    return result


def load_sdk(root):
    if platform.system() != 'Linux' or sys.version_info[:2] != (3, 10):
        raise RuntimeError('Official SDK requires Linux Python 3.10; run this on the D1, not Windows.')
    arch = platform.machine().lower().replace('arm64', 'aarch64').replace('amd64', 'x86_64')
    folder = Path(root).expanduser().resolve() / 'lib' / 'zsl-1' / arch
    if not folder.is_dir():
        raise RuntimeError(f'SDK library directory missing: {folder}')
    sys.path.insert(0, str(folder))
    return importlib.import_module('mc_sdk_zsl_1_py').HighLevel()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-root', required=True)
    p.add_argument('--dashboard', default='http://127.0.0.1:18080')
    p.add_argument('--local-ip', default='192.168.234.1')
    p.add_argument('--dog-ip', default='192.168.234.1')
    p.add_argument('--local-port', type=int, default=43988)
    p.add_argument('--enable-motion', action='store_true', help='Required: enable REAL movement')
    p.add_argument('--speed', type=float, default=.15)
    p.add_argument('--turn-rate', type=float, default=.2)
    args = p.parse_args()
    if not args.enable_motion:
        p.error('Use --enable-motion to run real following; no SDK commands were sent.')
    if not (.05 <= args.speed <= .2 and .02 <= args.turn_rate <= .3):
        p.error('Speed must be 0.05..0.2 m/s and turn-rate 0.02..0.3 rad/s')
    if not args.dashboard.startswith('http://127.0.0.1:'):
        p.error('Use a loopback SSH reverse tunnel for --dashboard')
    app = None
    controller = None
    failed = False
    def interrupt(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        # Verify dashboard before touching the SDK.
        exchange(args.dashboard, '/api/target')
        app = load_sdk(args.sdk_root)
        app.initRobot(args.local_ip, args.local_port, args.dog_ip)
        # Python binding names have differed in vendor docs; inspect installed binding.
        check = getattr(app, 'checkConnect', None) or getattr(app, 'checkConnection', None)
        if check is None:
            raise RuntimeError('SDK lacks connection check; use the documented SDK release.')
        deadline = time.monotonic() + 5
        while not check():
            if time.monotonic() >= deadline:
                raise RuntimeError('SDK connection timeout: check sdk_config.yaml and local IP/port')
            time.sleep(.1)
        # Do not unexpectedly stand up or change remote-control ownership.
        if app.getCurrentCtrlmode() not in (1, 3):
            raise RuntimeError('Stand the robot using its remote, then enable SDK control before starting.')
        controller = Controller(app, args.speed, args.turn_rate)
        controller.stop()
        exchange(args.dashboard, '/api/motion', dict(action='heartbeat', state='READY', command=list(ZERO)))
        exchange(args.dashboard, '/api/motion', dict(action='start'))
        print('REAL FOLLOW ENABLED. Ctrl+C / dashboard Stop to stop. Keep remote stop available.', flush=True)
        last_log = 0
        while True:
            started = time.monotonic()
            data = exchange(args.dashboard, '/api/target')
            if not check():
                raise RuntimeError('SDK connection lost')
            elapsed = time.monotonic() - started
            command = controller.step(data, elapsed)
            if time.monotonic() - last_log >= 1:
                print(f"{decision_reason(data, elapsed)} | frame_age={data.get('frame_age_seconds')}s "
                      f"| mode={controller.mode} | move{command} accepted by SDK", flush=True)
                last_log = time.monotonic()
            exchange(args.dashboard, '/api/motion', dict(action='heartbeat',
                     state='ACTIVE' if any(command) else 'READY', command=list(command)))
            time.sleep(max(0, .1 - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print('Stopping follower.', flush=True)
    except Exception as exc:
        failed = True
        print(f'FOLLOW STOPPED: {exc}', file=sys.stderr, flush=True)
    finally:
        # Repeat zero on shutdown/error. Stop failures are explicit, never reported as success.
        if controller is not None:
            for _ in range(3):
                try:
                    controller.stop()
                except Exception as exc:
                    failed = True
                    print(f'STOP COMMAND FAILED: {exc}. Use physical remote stop.', file=sys.stderr, flush=True)
                time.sleep(.05)
        try:
            exchange(args.dashboard, '/api/motion', dict(action='heartbeat',
                     state='FAULT' if failed else 'STOPPED', command=list(ZERO),
                     error='Bridge stopped; inspect robot terminal' if failed else ''))
        except Exception:
            pass
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
