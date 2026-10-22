#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
task_arch="$(uname -m)"
export LD_LIBRARY_PATH="$task_root/sdk/lib/zsl-1/$task_arch:${LD_LIBRARY_PATH:-}"
if [[ "${1:-}" == '--check' ]]; then
    shift
    exec python3.10 "$task_root/robot_check.py" "$@"
fi
exec python3.10 "$task_root/robot_follow.py" --sdk-root "$task_root/sdk" "$@"
