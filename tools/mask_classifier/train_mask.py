"""Train the face-mask classifier and export models/mask.onnx.

Classes, in this order: 0 mask_weared_incorrect, 1 with_mask, 2 without_mask.
Data: an image folder per class, such as the poolrf2001/FaceMask dataset on Hugging Face
(face crops from the CC0 Kaggle "Face Mask Detection" set by Andrew Maranhao).

CCTV faces are 20-50 px, often under a helmet and turned aside, so training shrinks and
blurs the clean 128 px crops to look like that.

Run outside the worker image, from the repo root:

    pip install torch torchvision onnx --index-url https://download.pytorch.org/whl/cpu
    python tools/mask_classifier/train_mask.py path/to/FaceMask models/mask.onnx
"""

import random
import sys
from pathlib import Path

import torch
from PIL import Image, ImageFilter
from torch import nn
from torchvision import datasets, models, transforms

SIZE = 96
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


class LowResolution:
    """Shrink to a CCTV-sized face and back, sometimes with blur."""

    def __call__(self, image: Image.Image) -> Image.Image:
        if random.random() < 0.8:
            side = random.randint(16, 48)
            image = image.resize((side, side), Image.BILINEAR).resize((SIZE, SIZE), Image.BICUBIC)
        if random.random() < 0.3:
            image = image.filter(ImageFilter.GaussianBlur(random.uniform(0.3, 1.2)))
        return image


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python tools/mask_classifier/train_mask.py <data folder with train/ and validation/> <out.onnx>")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    torch.manual_seed(7)
    random.seed(7)
    torch.set_num_threads(8)
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(SIZE, scale=(0.65, 1.0), ratio=(0.85, 1.15)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        LowResolution(),
        transforms.ColorJitter(0.4, 0.4, 0.4, 0.05),
        transforms.RandomGrayscale(0.1),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    eval_tf = transforms.Compose([transforms.Resize((SIZE, SIZE)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    train = datasets.ImageFolder(next(root.glob("train*/**/with_mask")).parent, train_tf)
    valid = datasets.ImageFolder(next(root.glob("validation*/**/with_mask")).parent, eval_tf)
    assert train.classes == ["mask_weared_incorrect", "with_mask", "without_mask"], train.classes
    loader = torch.utils.data.DataLoader(train, batch_size=64, shuffle=True, num_workers=0)
    check = torch.utils.data.DataLoader(valid, batch_size=128)

    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 3)
    optimiser = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    epochs = 14
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=2e-3, total_steps=epochs * len(loader))
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    best, best_state = 0.0, None
    for epoch in range(epochs):
        model.train()
        for images, labels in loader:
            optimiser.zero_grad()
            loss = loss_fn(model(images), labels)
            loss.backward()
            optimiser.step()
            schedule.step()
        model.eval()
        right = total = 0
        with torch.no_grad():
            for images, labels in check:
                right += int((model(images).argmax(1) == labels).sum())
                total += len(labels)
        accuracy = right / total
        print(f"epoch {epoch + 1:2d}  loss {loss.item():.3f}  validation accuracy {accuracy:.3f}", flush=True)
        if accuracy >= best:
            best, best_state = accuracy, {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(model, torch.zeros(1, 3, SIZE, SIZE), str(out), input_names=["image"], output_names=["logits"], dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17)
    print(f"best validation accuracy {best:.3f}; wrote {out}")


if __name__ == "__main__":
    main()
