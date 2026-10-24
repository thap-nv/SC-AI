"""Train the site's hand-washing step classifier and export models/handwash_steps.onnx.

Classes, in this order: none (no hands), other (hands, but no step: wetting, soap, rinsing,
changing step), then the six Bo Y te / WHO steps: palms, backs, interlaced, fingers, thumbs,
fingertips. Sides are not told apart.

Training data is labelled video: a JSON file per clip under labels/ gives the video, the crop
(the hand-wash zone's bounding box, as fractions of the frame) and time spans per class. Frames
within 0.25 s of a span's edge are left out, and spans marked "unsure" are not trained on.

The worker feeds the model what sink_crop() makes here: the zone's bounding box, padded square
on grey 127, 224 px, RGB, ImageNet mean and std.

Run outside the worker image, from the repo root:

    pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
    pip install onnx==1.16.2 opencv-python-headless==4.10.0.84 "numpy<2"
    python tools/handwash_classifier/train_handwash.py --train tools/handwash_classifier/labels/handwash-correct.json \
        --test tools/handwash_classifier/labels/handwash-wrong.json --out models/handwash_steps.onnx
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms

CLASSES = ["none", "other", "palms", "backs", "interlaced", "fingers", "thumbs", "fingertips"]
SIZE = 224
STORED = 256
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
# Frames this close to the edge of a span are a change of step, not the step.
EDGE_S = 0.25
# Every 2nd frame of a 30 fps clip: neighbouring frames are near copies.
EVERY = 2


def sink_crop(frame: np.ndarray, crop: list[float], size: int) -> np.ndarray:
    """The zone's bounding box, padded square on grey 127 and resized, as the worker feeds the model."""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = int(crop[0] * width), int(crop[1] * height), int(crop[2] * width), int(crop[3] * height)
    region = frame[y1:y2, x1:x2]
    side = max(region.shape[:2])
    canvas = np.full((side, side, 3), 127, dtype=np.uint8)
    top, left = (side - region.shape[0]) // 2, (side - region.shape[1]) // 2
    canvas[top : top + region.shape[0], left : left + region.shape[1]] = region
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def labelled_frames(label_file: Path, root: Path, keep_unsure: bool) -> tuple[list[np.ndarray], list[int], list[float]]:
    spec = json.loads(label_file.read_text(encoding="utf-8"))
    spans = [(float(span[0]), float(span[1]), span[2], len(span) > 3 and span[3] == "unsure") for span in spec["segments"]]
    capture = cv2.VideoCapture(str(root / spec["video"]))
    fps = capture.get(cv2.CAP_PROP_FPS)
    images, labels, times = [], [], []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        t = index / fps
        index += 1
        if (index - 1) % EVERY:
            continue
        span = next((span for span in spans if span[0] <= t <= span[1]), None)
        if span is None or (span[3] and not keep_unsure) or (min(t - span[0], span[1] - t) < EDGE_S and span[2] != "none"):
            continue
        images.append(cv2.cvtColor(sink_crop(frame, spec["crop"], STORED), cv2.COLOR_BGR2RGB))
        labels.append(CLASSES.index(span[2]))
        times.append(round(t, 2))
    return images, labels, times


class Frames(torch.utils.data.Dataset):
    def __init__(self, images, labels, transform):
        self.images, self.labels, self.transform = images, labels, transform

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        return self.transform(Image.fromarray(self.images[index])), self.labels[index]


def evaluate(model, images, labels, transform) -> tuple[float, dict[str, str], Counter]:
    model.eval()
    predicted = []
    with torch.no_grad():
        for start in range(0, len(images), 64):
            batch = torch.stack([transform(Image.fromarray(image)) for image in images[start : start + 64]])
            predicted += model(batch).argmax(1).tolist()
    confusion = Counter(zip(labels, predicted))
    per_class = {}
    for index, name in enumerate(CLASSES):
        total = sum(count for (truth, _), count in confusion.items() if truth == index)
        if total:
            right = confusion[(index, index)]
            wrong = Counter({CLASSES[guess]: count for (truth, guess), count in confusion.items() if truth == index and guess != index})
            per_class[name] = f"{right}/{total}" + (f" (else {dict(wrong.most_common(2))})" if wrong else "")
    accuracy = sum(confusion[(index, index)] for index in range(len(CLASSES))) / max(1, len(labels))
    return accuracy, per_class, confusion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", nargs="+", required=True, type=Path)
    parser.add_argument("--test", nargs="*", default=[], type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    torch.manual_seed(7)
    random.seed(7)
    torch.set_num_threads(8)

    train_images, train_labels = [], []
    for label_file in args.train:
        images, labels, _ = labelled_frames(label_file, args.root, keep_unsure=False)
        train_images += images
        train_labels += labels
        print(f"train {label_file.name}: {len(images)} frames {dict(Counter(CLASSES[label] for label in labels))}", flush=True)
    tests = []
    for label_file in args.test:
        images, labels, _ = labelled_frames(label_file, args.root, keep_unsure=False)
        tests.append((label_file.name, images, labels))
        print(f"test {label_file.name}: {len(images)} frames", flush=True)

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(SIZE, scale=(0.75, 1.0), ratio=(0.9, 1.1)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(0.35, 0.35, 0.3, 0.03),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    eval_tf = transforms.Compose([transforms.Resize((SIZE, SIZE)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    # Every class drawn about as often: one clip has seconds of "none" and a minute of the rest.
    counts = Counter(train_labels)
    weights = [1.0 / counts[label] for label in train_labels]
    sampler = torch.utils.data.WeightedRandomSampler(weights, num_samples=len(train_labels), replacement=True)
    loader = torch.utils.data.DataLoader(Frames(train_images, train_labels, train_tf), batch_size=32, sampler=sampler, num_workers=0)

    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, len(CLASSES))
    optimiser = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=2e-3, total_steps=args.epochs * len(loader))
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    for epoch in range(args.epochs):
        model.train()
        total = 0.0
        for images, labels in loader:
            optimiser.zero_grad()
            loss = loss_fn(model(images), labels)
            loss.backward()
            optimiser.step()
            schedule.step()
            total += loss.item()
        line = f"epoch {epoch + 1:2d}  loss {total / len(loader):.3f}"
        for name, images, labels in tests:
            line += f"  {name} {evaluate(model, images, labels, eval_tf)[0]:.3f}"
        print(line, flush=True)
    # The last epoch is kept: picking the best on the test clip would make its score look better than it is.
    for name, images, labels in tests:
        accuracy, per_class, _ = evaluate(model, images, labels, eval_tf)
        print(f"{name}: {accuracy:.3f} of frames right")
        for cls, text in per_class.items():
            print(f"    {cls:11} {text}")

    model.eval()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(model, torch.zeros(1, 3, SIZE, SIZE), str(args.out), input_names=["image"], output_names=["logits"], dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17)
    import onnx

    exported = onnx.load(str(args.out))
    for key, value in {"classes": ",".join(CLASSES), "input": "zone bounding box padded square on grey 127, 224 px, RGB, ImageNet mean/std", "trained_on": ",".join(path.name for path in args.train)}.items():
        entry = exported.metadata_props.add()
        entry.key, entry.value = key, value
    onnx.save(exported, str(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
