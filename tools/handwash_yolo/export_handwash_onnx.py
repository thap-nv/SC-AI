"""Export a hand-washing gesture checkpoint to models/handwash.onnx.

The reference checkpoints come from https://github.com/r-ozakar/synthetic-hand-washing, trained on the
synthetic set of Özakar and Gedikli, "Hand Washing Gesture Recognition Using Synthetic Dataset",
J. Imaging 2025, 11(7), 208. Their 8 classes are four WHO movements, each done once per side.
Use pre-trained/yolo8n-seg.pt: on the repo's 40 real test frames it named the step in 27, the
detection model yolo8n.pt in 24. See models/README.md.

Run from the repo root, outside the worker image. Ultralytics 8.2.94 needs torch 2.4:

    pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
    pip install ultralytics==8.2.94 "numpy<2" onnx==1.16.2 onnxslim==0.1.34
    python tools/handwash_yolo/export_handwash_onnx.py path/to/yolo8n-seg.pt

The worker reads the ONNX file with ONNX Runtime and does not import Ultralytics.
"""

import shutil
import sys
import tempfile
from pathlib import Path

# 8 for the reference model. 10 adds palm to palm (8) and palms with fingers interlaced (9).
CLASS_COUNTS = (8, 10)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: python tools/handwash_yolo/export_handwash_onnx.py path/to/best.pt [out.onnx]")
    weights = Path(sys.argv[1])
    if not weights.exists():
        raise SystemExit(f"weights not found: {weights}")
    destination = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(__file__).resolve().parents[2] / "models" / "handwash.onnx"
    from ultralytics import YOLO

    with tempfile.TemporaryDirectory() as work:
        # Ultralytics writes the export beside the weights, which may be read-only.
        local = Path(work) / weights.name
        shutil.copyfile(weights, local)
        model = YOLO(str(local))
        if len(model.names) not in CLASS_COUNTS:
            raise SystemExit(f"expected {' or '.join(map(str, CLASS_COUNTS))} classes, found {len(model.names)}")
        exported = Path(model.export(format="onnx", imgsz=640, simplify=True))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(exported, destination)
    print(destination)


if __name__ == "__main__":
    main()
