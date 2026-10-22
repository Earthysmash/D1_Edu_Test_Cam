"""Read-only robot preflight. Does not initialize or command the motion SDK."""
import argparse
import platform
import re
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--local-ip', default='192.168.234.1')
    args = p.parse_args()
    print('Platform:', platform.system(), platform.machine(), 'Python:', platform.python_version())
    if platform.system() != 'Linux' or sys.version_info[:2] != (3, 10):
        raise RuntimeError('Official binary needs Linux Python 3.10. Use python3.10 for this check and follower.')
    path = Path('/opt/export/config/sdk_config.yaml')
    text = path.read_text()
    # Inspect only the documented top-level target fields; do not rewrite firmware config.
    values = {}
    for key in ('target_ip', 'target_port'):
        match = re.search(r'^\s*' + key + r'\s*:\s*[\'\"]?([^\s\'\"#]+)', text, re.M)
        values[key] = match.group(1) if match else None
    print('SDK feedback destination:', values)
    if values != {'target_ip': args.local_ip, 'target_port': '43988'}:
        raise RuntimeError(f'Robot-local SDK requires target_ip: "{args.local_ip}" and target_port: 43988 '
                           'in /opt/export/config/sdk_config.yaml. Back up before editing; reboot after changing. '
                           'See RUN_FOLLOW_TH.md. No configuration was changed.')
    # Import the module only: constructing HighLevel is deliberately deferred to run_follow.sh.
    import importlib
    arch = platform.machine().replace('arm64', 'aarch64').replace('amd64', 'x86_64')
    folder = Path(__file__).resolve().parent / 'sdk' / 'lib' / 'zsl-1' / arch
    sys.path.insert(0, str(folder))
    module = importlib.import_module('mc_sdk_zsl_1_py')
    missing = [name for name in ('initRobot', 'move', 'getCurrentCtrlmode') if not hasattr(module.HighLevel, name)]
    if missing:
        raise RuntimeError('SDK methods missing: ' + ', '.join(missing))
    print('Preflight OK. No movement sent. SDK control ownership/standing still require robot verification.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('PRECHECK FAILED:', exc, file=sys.stderr)
        raise SystemExit(1)
