"""Export a trained Ultralytics checkpoint to models/ppe.onnx.

Train from the repo root, outside the worker image:

    pip install ultralytics
    yolo detect train model=yolov8n.pt data=tools/ppe_yolo/data.yaml imgsz=640 epochs=80
    python tools/ppe_yolo/export_ppe_onnx.py runs/detect/train/weights/best.pt

Class ids must follow tools/ppe_yolo/data.yaml. Remap a public dataset to them first.
The worker reads the ONNX file with ONNX Runtime and does not import Ultralytics.
"""

import shutil
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/ppe_yolo/export_ppe_onnx.py path/to/best.pt")
    weights = Path(sys.argv[1])
    if not weights.exists():
        raise SystemExit(f"weights not found: {weights}")
    from ultralytics import YOLO

    model = YOLO(str(weights))
    if len(model.names) != 8:
        raise SystemExit(f"expected the 8 classes in tools/ppe_yolo/data.yaml, found {len(model.names)}")
    exported = Path(model.export(format="onnx", imgsz=640, simplify=True))
    destination = Path(__file__).resolve().parents[2] / "models" / "ppe.onnx"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exported, destination)
    print(destination)


if __name__ == "__main__":
    main()
