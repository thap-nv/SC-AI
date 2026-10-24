"""Write models/vehicle_types.npz: one CLIP text vector per vehicle type, for the worker's vehicle typer.

The worker compares a vehicle crop's CLIP image vector with these, so it needs no tokenizer.
The vectors only fit the CLIP model they were made with: Xenova/clip-vit-base-patch32 (quantized).

Run outside the worker image, from the repo root, with the CLIP files downloaded into one folder:

    pip install tokenizers onnxruntime numpy
    python tools/vehicle_types/export_vehicle_types.py path/to/clip models/vehicle_types.npz

The folder needs tokenizer.json and text_model_quantized.onnx from
https://huggingface.co/Xenova/clip-vit-base-patch32 (the onnx/ subfolder for the model).
"""

import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

# The first type is the one allowed into restricted areas. Several phrasings per type are averaged.
TYPES = {
    "forklift": ["a photo of a forklift", "a yellow forklift truck in a port", "an industrial forklift with a mast and forks", "a forklift with a driver"],
    "car": ["a photo of a car", "a photo of a sedan car", "a silver passenger car"],
    "truck": ["a photo of a truck", "a photo of a lorry", "a container truck"],
    "bus": ["a photo of a bus"],
    "motorcycle": ["a photo of a motorcycle", "a person riding a motorbike"],
    "van": ["a photo of a van", "a pickup truck"],
}
PAD = 49407


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python tools/vehicle_types/export_vehicle_types.py <clip folder> <out.npz>")
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    model = ort.InferenceSession(str(folder / "text_model_quantized.onnx"), providers=["CPUExecutionProvider"])
    vectors = []
    for prompts in TYPES.values():
        rows = []
        for prompt in prompts:
            ids = tokenizer.encode(prompt).ids[:77]
            rows.append(ids + [PAD] * (77 - len(ids)))
        embedded = model.run(None, {"input_ids": np.array(rows, dtype=np.int64)})[0]
        embedded = embedded / np.linalg.norm(embedded, axis=1, keepdims=True)
        mean = embedded.mean(axis=0)
        vectors.append(mean / np.linalg.norm(mean))
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, labels=np.array(list(TYPES)), vectors=np.stack(vectors).astype(np.float32))
    print(f"wrote {out}: {', '.join(TYPES)}")


if __name__ == "__main__":
    main()
