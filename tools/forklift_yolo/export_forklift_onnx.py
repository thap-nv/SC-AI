"""Export a forklift detection checkpoint to models/forklift.onnx.

The POC uses keremberke/yolov8n-forklift-detection from Hugging Face (file best.pt), a YOLOv8n fine-tuned on the
Roboflow "Forklift" set (421 images, CC BY 4.0) with the classes forklift and person. The weights are an
Ultralytics YOLOv8, licensed AGPL-3.0. See models/README.md.

The file is exported at 512x896, the shape of a 16:9 frame: the worker letterboxes the whole 1280x720 frame into it.
On the port clip it found the far-off forklift of the first two seconds at 0.55 or more in 10 of 12 frames, where
384x640 and 640x640 found it in 1, for about 60 ms on 2 threads against 34 and 53 ms.

Run from the repo root, outside the worker image. Ultralytics 8.2.94 needs torch 2.4:

    pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
    pip install ultralytics==8.2.94 "numpy<2" onnx==1.16.2 onnxslim==0.1.34
    python tools/forklift_yolo/export_forklift_onnx.py path/to/best.pt

The worker reads the ONNX file with ONNX Runtime and does not import Ultralytics.
"""

import shutil
import sys
import tempfile
from pathlib import Path

# Height and width of the model input.
SIZE = (512, 896)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: python tools/forklift_yolo/export_forklift_onnx.py path/to/best.pt [out.onnx]")
    weights = Path(sys.argv[1])
    if not weights.exists():
        raise SystemExit(f"weights not found: {weights}")
    destination = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(__file__).resolve().parents[2] / "models" / "forklift.onnx"
    from ultralytics import YOLO

    with tempfile.TemporaryDirectory() as work:
        # Ultralytics writes the export beside the weights, which may be read-only.
        local = Path(work) / weights.name
        shutil.copyfile(weights, local)
        model = YOLO(str(local))
        if "forklift" not in model.names.values():
            raise SystemExit(f"no forklift class in {model.names}")
        exported = Path(model.export(format="onnx", imgsz=list(SIZE), simplify=True))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(exported, destination)
    print(destination)


if __name__ == "__main__":
    main()
