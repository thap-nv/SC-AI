"""Train the site's hand-washing step classifier and export models/handwash_steps.onnx.

Classes, in this order: none (no hands), other (hands, but no step: wetting, soap, rinsing,
changing step), then the six Bo Y te / WHO steps: palms, backs, interlaced, fingers, thumbs,
fingertips. Backs, thumbs and fingertips are done once per hand and have a class per hand, named
by the hand cleaned: thumbs_left is the left thumb turned in the right palm. On the site camera
the washer faces it from the top of the frame, so their right hand is on the left of the picture.

Training data is labelled video: a JSON file per clip under labels/ gives the video, the crop
(the hand-wash zone's bounding box, as fractions of the frame, where the hands are looked for) and
time spans per class. Frames within 0.25 s of a span's edge are left out, and spans marked "unsure"
are trained on only with --unsure.

The model sees what the worker feeds it: the square round the palms that app.handpose.hands_box
gives, cut by hand_square, 224 px, RGB, ImageNet mean and std. Both come from the worker's own code,
so a change there changes training too. Frames where the palm detector finds no hands are left out:
the worker does not run the model on them.

Run outside the worker image, from the repo root:

    pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
    pip install onnx==1.16.2 onnxruntime==1.20.1 opencv-python-headless==4.10.0.84 shapely==2.1.2 "numpy<2"
    python tools/handwash_classifier/train_handwash.py \
        --train tools/handwash_classifier/labels/handwash-correct.json tools/handwash_classifier/labels/handwash-wrong.json \
        --out models/handwash_steps.onnx
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "ai-worker"))
from app.handpose import HandPose, hand_square, hands_box  # noqa: E402

CLASSES = [
    "none", "other", "palms", "backs_left", "backs_right", "interlaced", "fingers",
    "thumbs_left", "thumbs_right", "fingertips_left", "fingertips_right",
]
# A frame flipped left to right shows the other hand doing the step.
FLIPPED = [CLASSES.index(name.replace("_left", "_x").replace("_right", "_left").replace("_x", "_right")) for name in CLASSES]
SIZE = 224
STORED = 256
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
# Frames this close to the edge of a span are a change of step, not the step.
EDGE_S = 0.25
# Every 2nd frame of a 30 fps clip: neighbouring frames are near copies.
EVERY = 2


def labelled_frames(label_file: Path, root: Path, pose: HandPose, keep_unsure: bool) -> tuple[list[np.ndarray], list[int], list[float]]:
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
        height, width = frame.shape[:2]
        left, top = int(spec["crop"][0] * width), int(spec["crop"][1] * height)
        square = hands_box(pose.palms(frame[top : int(spec["crop"][3] * height), left : int(spec["crop"][2] * width)]))
        if square is None:
            continue
        square = [square[0] + left, square[1] + top, square[2] + left, square[3] + top]
        images.append(cv2.cvtColor(hand_square(frame, square, STORED), cv2.COLOR_BGR2RGB))
        labels.append(CLASSES.index(span[2]))
        times.append(round(t, 2))
    return images, labels, times


class Frames(torch.utils.data.Dataset):
    """Training frames, half of them flipped left to right with the hand in the label swapped."""

    def __init__(self, images, labels, transform):
        self.images, self.labels, self.transform = images, labels, transform

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        image, label = Image.fromarray(self.images[index]), self.labels[index]
        if random.random() < 0.5:
            image, label = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT), FLIPPED[label]
        return self.transform(image), label


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
    parser.add_argument("--models", type=Path, default=Path("models"), help="where hand_palm.onnx and hand_pose.onnx are")
    parser.add_argument("--unsure", action="store_true", help="train on spans marked unsure too")
    args = parser.parse_args()
    torch.manual_seed(7)
    random.seed(7)
    torch.set_num_threads(8)
    pose = HandPose(str(args.models / "hand_palm.onnx"), str(args.models / "hand_pose.onnx"), ["CPUExecutionProvider"], 4)

    train_images, train_labels = [], []
    for label_file in args.train:
        images, labels, _ = labelled_frames(label_file, args.root, pose, keep_unsure=args.unsure)
        train_images += images
        train_labels += labels
        print(f"train {label_file.name}: {len(images)} frames {dict(Counter(CLASSES[label] for label in labels))}", flush=True)
    tests = []
    for label_file in args.test:
        images, labels, _ = labelled_frames(label_file, args.root, pose, keep_unsure=False)
        tests.append((label_file.name, images, labels))
        print(f"test {label_file.name}: {len(images)} frames", flush=True)

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(SIZE, scale=(0.75, 1.0), ratio=(0.9, 1.1)),
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
    for key, value in {"classes": ",".join(CLASSES), "crop": "hands", "input": "square round the palms (hands_box), grey 127 off the frame, 224 px, RGB, ImageNet mean/std", "trained_on": ",".join(path.name for path in args.train)}.items():
        entry = exported.metadata_props.add()
        entry.key, entry.value = key, value
    onnx.save(exported, str(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
