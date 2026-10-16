"""Run once on the PC while connected to the Internet."""
from pathlib import Path
import os
import sys

def main():
    os.chdir(Path(__file__).resolve().parent)
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")
        print("READY:", Path("yolov8n.pt").resolve())
        print("General-object model only; weapon/covered-face weights are separate.")
    except Exception as exc:
        print("Model preparation failed:", exc, file=sys.stderr)
        print("Check Internet/DNS access to github.com, then retry.", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
