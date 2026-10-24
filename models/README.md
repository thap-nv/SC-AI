# Person detector used by REAL mode

The local `person.onnx` is the official YOLOX-Nano COCO model:

- Source: https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx
- Upstream project and license: https://github.com/Megvii-BaseDetection/YOLOX (Apache-2.0)
- SHA256: `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`
- Input: BGR float32, 0..255, shape 1x3x416x416, resized with top-left alignment and padding value 114.
- Output: raw YOLOX predictions, shape 1x3549x85. The person adapter decodes strides 8, 16 and 32 and keeps COCO person class 0.

The person detector does not require visible facial skin. Boxes above 0.30 are kept and overlapping boxes are suppressed using the highest confidence first. The tracker only starts a new person from a box above 0.55, and shows it from its fourth frame in a row.

A wide frame goes into the model as overlapping squares as high as the frame, two for 16:9 (columns 0–720 and 560–1280 of a 1280x720 frame), instead of being squeezed whole into the model's square. Each person comes out 1.8 times bigger. On the port clip (`sample-data/videos/retricted area 2.mp4`), a worker standing in the restricted lane far from the camera, 65 px tall, scored 0.55 or more in 2 of 49 frames on the whole frame, so the tracker never started them; on two squares, in 44. A box that touches the edge two squares share is joined with the rest of the same object from the other square. Nano takes about 36 ms a frame on 2 threads this way, against 18 ms. On the workshop clip the camera loop opened the same four incidents, for the same four workers, with and without the squares.

Any official YOLOX ONNX model works as `person.onnx`; the input size is read from the file. YOLOX-S (640 px, SHA256 `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`, same release page) found 13.6 people per frame on the 15-person workshop clip against 5.5 for Nano, and kept apart two workers Nano merged into one box. It took about 146 ms a frame on 2 CPU threads against 18 ms on the whole frame, and twice that on two squares, so lower the camera AI FPS to about 3 with it.

Download from PowerShell in the project root:

```powershell
Invoke-WebRequest -Uri https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx -OutFile models/person.onnx
```

Model binaries are ignored by Git. Restart the AI worker after installing or replacing the model. Without a person model, REAL mode falls back to OpenCV HOG. PPE is a separate model; the person model does not judge helmets, clothing, shoes or masks.

## PPE detector

`ppe.onnx` is optional. REAL mode uses it when the file is present. It judges four items on each person: helmet, protective clothing, safety shoes and mask.

Contract:

- The worker runs the model once per person crop, not on the whole frame, so small items such as masks and shoes keep enough pixels. Each person is read again every `PPE_INTERVAL_S` seconds (default 0.3), not every frame.
- Input: RGB float32, 0..1, NCHW. The spatial size is read from the model.
- Output is either `Nx6` (`x1, y1, x2, y2, score, class_id`, in model pixels, input resized without letterbox) or a YOLO head of shape `(1, 12, anchors)`: `cx, cy, w, h` plus one score per class id below, input letterboxed. Boxes under score 0.35 are dropped.
- Class ids: 0 helmet, 1 no_helmet, 2 clothing, 3 no_clothing, 4 shoes, 5 no_shoes, 6 mask, 7 no_mask.
- An item takes the strongest box whose centre lies in that item's band of the person box, measured from the top: helmet 0–25%, mask 5–35%, clothing 15–80%, shoes 75–100%. A worn box gives YES, a `no_` box gives NO, no box leaves it UNKNOWN.
- Only NO raises an alert, and only after four of the last six reads of that person agree. A model trained without the `no_` classes never raises a PPE alert.

Train outside the worker image. Label your own site footage, or remap a public PPE dataset to the ids above; check each dataset's licence before using it. `tools/ppe_yolo/data.yaml` lists the classes. From the repo root: `yolo detect train model=yolov8n.pt data=tools/ppe_yolo/data.yaml imgsz=640 epochs=80`, then `python tools/ppe_yolo/export_ppe_onnx.py <best.pt>`. Do not import Ultralytics into the worker.

## Colour fallback and face detector

Without `ppe.onnx`, REAL mode reads colours on each person. It suits a POC on a clear view, such as a staged video, not a real deployment.

- Helmet: a white, yellow, orange or red hard hat just above the face. Hair or bare skin there is no helmet. When the person faces away, the top of the box is used, and only strong evidence counts, because a light floor or wall can sit beside the head. Blue is not read as a helmet: blue bins behind a bare head would look like one.
- Clothing: a coverall. Grey, beige, white or blue workwear on the torso that carries on down the legs is YES. A brightly coloured top, or a work-coloured top over dark trousers, is NO. When the legs are hidden (box less than twice as tall as wide) it stays UNKNOWN. A site with hi-vis vests over own clothes needs the model.
- Mask: needs `face.onnx`. With `mask.onnx` (below) a trained classifier reads each face. Without it, a mask colour (surgical blue or green, white, grey) over the chin is YES, and NO only when the face is turned to the camera and the chin has the same colour as the forehead; a profile or a lowered head stays UNKNOWN.
- Shoes: never judged by colour. The seeded demo has no shoes rule.

On the 30 s workshop clip (about 15 workers, one without a helmet, one in a T-shirt instead of a coverall) the worker loop opened exactly those two incidents and no others. Every wrong NO lasted under 1 s, below the 2 s rule duration. The clip has no worker without a mask, so mask NO has only been checked on synthetic images.

Frames are processed at 1280x720 (`FRAME_WIDTH`, `FRAME_HEIGHT`). At 960x540 helmet and clothing reads on that clip were clearly worse.

`face.onnx` is YuNet from the OpenCV Zoo:

- Source: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet, file `face_detection_yunet_2023mar.onnx` (the 2026 file needs OpenCV 5)
- License: MIT
- SHA256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`
- It runs through `cv2.FaceDetectorYN` on each person's head region, enlarged to 160 px, a few times a second.

```powershell
Invoke-WebRequest -Uri https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx -OutFile models/face.onnx
```

Without `face.onnx` the helmet is read from the top of the box only and the mask stays UNKNOWN.

## Mask classifier

`mask.onnx` is optional and needs `face.onnx`. It classifies the face YuNet finds: mask worn incorrectly, mask worn, no mask. Worn incorrectly counts as no mask.

- Built by `tools/mask_classifier/train_mask.py`: MobileNetV3-Small (torchvision, ImageNet start) fine-tuned on the Hugging Face set `poolrf2001/FaceMask` (declared MIT; face crops from the Kaggle "Face Mask Detection" set by Andrew Maranhao, listed as CC0). Check both licences before shipping a product.
- Input 1x3x96x96 RGB, ImageNet mean and std. Output three logits in the order above.
- Training shrinks the 128 px crops to 16-48 px and blurs them, to look like CCTV faces.
- SHA256 of the file built for this POC: `dee8fa35f7b9c393a0d5f7d6d147b35a0fd74fb26aa65d109d74199e3522ed62` (rebuild gives a different file).
- A face is NO when incorrect plus no-mask reach 0.7, YES when worn reaches 0.7, otherwise UNKNOWN. On four workshop clips 0.7 caught a worker without a mask seen side on and flagged nobody wrongly; 0.6 flagged two masked workers looking down.
- Known gap: a mask pulled under the chin is still read as worn, because the mask is in view. The training set has 500 incorrect examples, all close-up photos.

Rebuild from the repo root, outside the worker image:

```text
pip install torch torchvision onnx --index-url https://download.pytorch.org/whl/cpu
python tools/mask_classifier/train_mask.py path/to/FaceMask models/mask.onnx
```

## Forklift detector

The person model (any official YOLOX) also reports COCO vehicles: car, motorcycle, bus and truck. COCO has no forklift. On the port clip YOLOX-Nano read the forklift as a truck at 0.55 or more, enough to start a track, in 6 of 55 frames and never while it was far off, so the forklift went without a box for all but the last second of its pass. Even YOLOX-M on three squares, at about 1 s a frame, read it at 0.2–0.5 while it was far off.

`forklift.onnx` is optional. It is loaded only by a camera with a person or vehicle zone rule (people may not enter, no vehicles but forklifts), and runs on the whole frame every frame. Without it a forklift is only a truck the person model happens to find, and its driver can count as a person in the zone.

- Source: `best.pt` of https://huggingface.co/keremberke/yolov8n-forklift-detection, a YOLOv8n fine-tuned on the Roboflow "Forklift" set (https://universe.roboflow.com/mohamed-traore-2ekkp/forklift-dsitv, 421 images, classes forklift and person). SHA256 of the checkpoint: `0dc3816283226f0f7ac5410620394c8ddeef32c5200b371194ac4df4a1ee7d38`.
- License: the dataset is CC BY 4.0. The weights are a fine-tuned Ultralytics YOLOv8, which Ultralytics licenses under AGPL-3.0 (the export says so in its metadata), as for `handwash.onnx`. Check this before shipping a product.
- Built by `tools/forklift_yolo/export_forklift_onnx.py`, outside the worker image, at 512x896, the shape of a 16:9 frame. The export gives a different file each time (it stores the date). SHA256 of the file built for this POC: `7f76b76c2b5b9b18894bbee37f181c322dfd1203d286bd2dd6b2e9feaeb08b28`.
- Input 1x3x512x896 RGB, 0..1, letterboxed with grey 114; the size is read from the file. Output: a YOLO head `(1, 4 + classes, anchors)`. Class names come from the file; only `forklift` boxes above 0.30 are kept, people come from YOLOX.

On the port clip, every fourth frame, with the forklift marked by YOLOv8m of the same set on two squares:

| Input | Forklift at 0.55 or more | at 0.3 or more | First 2 s, far off, at 0.55 or more | ms a frame, 2 threads |
|---|---|---|---|---|
| 384x640 | 44/55 | 50/55 | 1/12 | 34 |
| 640x640 | 44/55 | 51/55 | 1/12 | 53 |
| 512x896 | 52/55 | 55/55 | 10/12 | 60 |
| YOLOv8s 640x640 | 54/55 | 55/55 | 12/12 | 147 |

The model was trained on photos with no cars in them. It read the clip's white car as a forklift at up to 0.89, and once boxed the car and the forklift behind it as one forklift, while YOLOX read the car at 0.8 or more in every frame and the forklift as a car at most 0.61, as it left the frame. So a forklift box on a YOLOX car or bus of 0.7 or more is dropped, and any other YOLOX vehicle on a forklift box (a truck, a motorcycle, a weak car) gives way to it. It also put a forklift box at 0.35–0.48 on cranes and a yellow barrier, too weak to start a track. On the first port clip (`retricted area.mp4`, one worker, container trucks far off) it boxed nothing.

Through the worker's own camera loop on the port clip, two plays, with the zone as drawn: the forklift was followed from 0.4 s to 9 s of its 9 s pass and typed as a forklift throughout, the car was a violation throughout, and the far worker in the lane was followed from 1.4 s and opened the intrusion incident. Before, the forklift had a box for 0.8 s and the far worker none. The loop took about 107 ms a frame against 21 ms, so the camera runs at about 9 FPS on this machine whatever its AI FPS is set to. The near worker walks on the yellow line that edges the drawn lane, 4–13 px outside it, and is not counted as inside.

Rebuild from the repo root, outside the worker image:

```text
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
pip install ultralytics==8.2.94 "numpy<2" onnx==1.16.2 onnxslim==0.1.34
python tools/forklift_yolo/export_forklift_onnx.py path/to/best.pt
```

## Vehicle types

A restricted area that allows forklifts needs the vehicle type, so each tracked vehicle is typed by CLIP twice a second and keeps the most common of its last five reads, whichever detector found it.

- `clip_vision.onnx`: CLIP ViT-B/32 image encoder, int8 quantised. File `onnx/vision_model_quantized.onnx` from https://huggingface.co/Xenova/clip-vit-base-patch32. OpenAI released CLIP under MIT; the converted repo states no licence of its own, so check before shipping a product. SHA256 `583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299`.
- `vehicle_types.npz`: one text vector per type (forklift, car, truck, bus, motorcycle, van), written by `tools/vehicle_types/export_vehicle_types.py` with the matching text encoder. The worker needs no tokenizer. It only fits the CLIP model above.
- On the port reference image the two forklifts scored 0.97 and 0.99 forklift, the two cars 0.00 and 0.02.
- Without these two files the detector's class is used: a box from `forklift.onnx` is a forklift, and a forklift YOLOX detected as a truck is not allowed.

A person whose box lies at least 60% inside a vehicle's box is taken to be riding it, such as a forklift driver, and does not count as a person in a restricted area.

## Hand-washing gestures

`handwash.onnx` is optional. It is needed in REAL mode on a camera with a WHO hand-washing rule, and is loaded only by such a camera. Without it no wash is checked and the worker logs a warning.

- Source: `pre-trained/yolo8n-seg.pt` from https://github.com/r-ozakar/synthetic-hand-washing (commit `87e81d6`), the YOLOv8n segmentation model of Özakar and Gedikli, "Hand Washing Gesture Recognition Using Synthetic Dataset", J. Imaging 2025, 11(7), 208. Trained only on rendered images. SHA256 of the checkpoint: `496166a9ca5cfb160d4865016170d35076a6af0e4b9424981b38dee730d20a74`.
- License: the repo is MIT and the dataset CC BY, but the weights are a fine-tuned Ultralytics YOLOv8, which Ultralytics licenses under AGPL-3.0 (the export says so in its metadata). Check this before shipping a product.
- Built by `tools/handwash_yolo/export_handwash_onnx.py`, outside the worker image. The export gives a different file each time (it stores the date). SHA256 of the file built for this POC: `59ee8e43aa67654fedee2bda6e83f81a4fced09cc5580aae9516f3d997ff684f`.
- Input 1x3x640x640 RGB, 0..1, letterboxed with grey 114. The whole frame goes in: the model was trained on whole frames from a camera above the sink.
- Output: a YOLO head `(1, 4 + classes, anchors)`, or with 32 mask channels after the class scores for a segmentation export. The class count is read from the names Ultralytics writes into the file; mask channels are ignored. Boxes under 0.35 are dropped. The best box whose centre lies in the hand-wash zone is the gesture of that read.
- Class ids: 0 and 1 backs of hands (palm over the back of the other hand, fingers interlaced), 2 and 3 backs of fingers, 4 and 5 thumbs, 6 and 7 fingertips. Each pair is one WHO step done with the left and with the right hand; the worker does not tell sides apart. A model trained on all six steps can add 8 palm to palm and 9 palms with fingers interlaced.

The reference model has no class for WHO steps 1 (palm to palm) and 3 (palms with fingers interlaced), so they are never checked. On the repo's 40 real test frames (5 per class, one person, one sink) it named the right step in 27:

| Step | Right | Mostly read as |
|---|---|---|
| 2 Backs of hands | 10/10 | |
| 4 Backs of fingers | 1/10 | fingertips (9) |
| 5 Thumbs | 7/10 | fingertips |
| 6 Fingertips | 9/10 | thumbs |

The detection model `yolo8n.pt` named 24 of 40 and was worse on thumbs (4/10). Cropping the frame to the sink made neither better. Hands were found in 37 of the 40 frames. The paper reports 79.3% for the segmentation model on its own, larger real set.

Backs of fingers would be reported missing on nearly every wash, so with this model set `HANDWASH_SKIP_STEPS=fingers` in `.env` (the default is empty, for the site classifier below, which reads every step). The worker then checks steps 2, 5 and 6. A wash where only backs of fingers was done can still pass on fingertips.

Camera distance matters more than angle. The model learned hands about a tenth of the frame wide. On the site's sink, filmed from above but closer, hands are about a fifth of the frame wide and the model found them in 21 of 170 labelled reads. `HANDWASH_SCALE` letterboxes the frame smaller, as if the camera were further away. Two sample washes of the site were labelled by eye: `sample-data/videos/handwash - correct.mp4` does all six steps in order, about 42 s of rubbing, 4–8 s a step; `handwash - wrong.mp4` is two rushed washes, steps 1–4 s each. As the person who washed tells it, the first leaves out step 3 and turns only one thumb (step 5 half done), the second leaves out step 4. Both went through the worker's reads and wash logic on a live timeline (loop at 12 and 18.7 fps, a read every 0.2 s, three start offsets each), with the rule's 3 s per step:

| Scale | Wash gap | Correct passed | Wrong flagged |
|---|---|---|---|
| 1.0 | 4 s | never: hands seen in 13 of 65 s | always, only because no hands were seen |
| 0.65 | 4 s | 6/6 | 0/6: the two washes ran together and the thumbs of the first carried the second |
| 0.6 | 2–3 s | 6/6 | 6/6 |
| 0.7 | 2–2.5 s | 6/6 | 6/6 |

The defaults are scale 0.6 and a 2.5 s gap, the middle of the range that got every run right. Live, on the camera, the correct video passed all three plays. The wrong video was flagged on every play, by its first wash (missing thumbs); its second wash, which also leaves out thumbs, still passed, as the model credits thumbs there. Each play of the wrong video also opened an incident for the first 4 s, where the hands are wetted before a walk to the soap longer than the gap: a wash with no step at all. Raising the step minimum to 6 s instead of shortening the gap flagged the wrong video but also one play in three of the correct one. All of this rests on two videos of one person at one sink.

On the reference test frames, which want 1.0, shrinking costs accuracy: 27/40 at 1.0, 25 at 0.7, 19 at 0.6. The model also reads palm to palm, palms interlaced and rinsing as fingertips, so fingertips is nearly always credited: a wash that skips only fingertips passes.

An uploaded video plays at its own speed, like a live camera: frames the loop is too slow for are skipped. Before, one frame was read per loop step, so a 30 fps video ran at about half speed on this camera and every step looked twice as long.

How a wash is judged:

- The gesture is read every `HANDWASH_INTERVAL_S` (default 0.2 s). With the site classifier, each read credits every step the time since the last read times the step's chance. With this reference model, which gives a gesture but no chance per step, a read settles when two of the last three agree and the settled gesture is credited. In a clip made of the test frames (each held 0.5 s, 6 s per step), three of five credited thumbs anywhere from 2.8 to 6.8 s, and one full wash in three was reported missing thumbs; two of three credited 4.2–5.4 s. A step not done picked up at most 2.4 s from misreads of the step before it.
- A wash starts when hands show up in the zone and ends when none have been seen for `HANDWASH_GAP_S` (1.5 s), or when an uploaded video starts over. Hands seen for less than 3 s in all are someone passing, not a wash.
- A step is done once it has been credited the rule's minimum duration (1.5 s in the seeded rule). When the wash ends, a checked step not done is missing, and one incident is opened and closed at once, spanning the wash. Its snapshot lists the missed steps.
- The 3 s minimum and 2.5 s gap in the table above were set for this reference model. The site classifier below uses 1.5 s for both.

## Site hand-washing step classifier

`handwash_steps.onnx` is optional and, when present, is used instead of `handwash.onnx`. It was trained on the site's own sink, so it knows all six Bo Y te / WHO steps. It needs `hand_palm.onnx` and `hand_pose.onnx` (below): it looks at the hands the palm detector finds.

- Built by `tools/handwash_classifier/train_handwash.py`: MobileNetV3-Small (torchvision, ImageNet start), fine-tuned on frames of `sample-data/videos/handwash - correct.mp4` (the reference wash) and `handwash - wrong.mp4`. Time spans per class are in `tools/handwash_classifier/labels/*.json`, labelled by eye from frames every 0.25–0.5 s; the 0.25 s at each step change is not trained on, nor are spans marked `unsure` unless `--unsure` is passed.
- Classes: `none` (no hands), `other` (hands but no step: wetting, soap, rinsing), `palms`, `backs_left`, `backs_right`, `interlaced`, `fingers`, `thumbs_left`, `thumbs_right`, `fingertips_left`, `fingertips_right`. Steps 2, 5 and 6 are done once per hand and have a class per hand, named by the hand cleaned: `thumbs_left` is the left thumb turned in the right palm. On the site camera the washer faces it from the top of the frame, so their right hand is on the left of the picture; the person in the sample clips confirmed the hands. Step 4 has one class: the correct clip does it once, fingers locked together. A frame flipped left to right in training has its hand swapped in the label. The class order is stored in the file's metadata; a file with one class per step still works, without telling the hands apart.
- A step per hand is done once each hand has been credited half the rule's minimum (0.75 s of the seeded 1.5 s). With one hand short the step is missing for that hand, and the panel and incident say so: "5 Thumbs: right hand only", "Thumbs (left hand)".
- Input: the square round the hands, from `hands_box` in `app/handpose.py`: centred between the two best palms the palm detector finds in the hand-wash zone, four palm widths a side, grey 127 where it runs off the frame, 224 px, RGB, ImageNet mean and std. Output: one logit per class. No palm in the zone, or hands read as `none`, gives no hit, so the wash gap counts; `other` keeps the wash going without crediting a step. The training script cuts its frames with the same functions.
- The metadata entry `crop=hands` says so. A file without it, such as the first one built, looks at the zone's bounding box instead, and the zone then has to be drawn exactly as for training (22% to 82% of the frame width, full height). Drawn at 6% to 92% on another install, that file read backs of hands and almost nothing else: every wash of the wrong clip came out missing steps 1, 3, 4, 5 and 6.
- Each read gives the chance of every step, and the wash credits each step the time since the last read times its chance. The vote of two in three, used before, made the credit depend on which frames the reads fell on: scored by a model that had not seen the correct clip, its fingertips were credited anywhere from 0.8 to 5.3 s over 200 plays, and a step near the minimum passed some plays and was missing in others. Credited by chance, the same fingertips got 2.5–4.8 s; with the deployed file in the camera loop, no step varied by more than 0.5 s between plays.
- SHA256 of the file built for this POC: `8822e60ccb718fb6bf5bf8959e614fe0820af22e5a69b156082b9e6a1c7e5e1c` (training is not bit-for-bit repeatable). The hand-wash part of the loop takes about 29 ms a frame on 2 threads: the palm detector and the classifier five times a second, the overlay's joints ten times a second.

Each wrong wash was also scored by a model trained without it (leave one wash out), the honest measure of how it does on a wash it has not seen. Frames named right: first wrong wash 98.5% (its one thumb read as the right thumb 8/8), second 94.1% (every class per hand right but one left-thumb frame of four). Through the worker's own camera loop on the wrong clip, three plays each, both models gave the person's own account every time: the first wash missing step 3 and step 5 for the left hand (left thumb credited 0.2–0.3 s, every hand that did its step 1.3 s or more), the second missing step 4.

Before the classes per hand, a model with one class per step, scored the same way, counted the single thumb of the first wrong wash as a whole step 5: credited 1.6–2.1 s, longer than that wash's 2 s backs of fingers, so no minimum could separate them.

The deployed file is trained on both clips. Through the camera loop on the combined clip, four plays each with the zone drawn at 22–82% and at 6–92% of the width, every play gave the same three results: the correct wash passed, the first wrong wash missed step 3 and the left hand of step 5, the second missed step 4. Both clips are one person at one sink in one light: other people, sleeves and lighting need more labelled clips before the alerts can be trusted.

Retrain from the repo root, outside the worker image:

```text
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
pip install onnx==1.16.2 onnxruntime==1.20.1 opencv-python-headless==4.10.0.84 shapely==2.1.2 "numpy<2"
python tools/handwash_classifier/train_handwash.py --train tools/handwash_classifier/labels/handwash-correct.json tools/handwash_classifier/labels/handwash-wrong.json --out models/handwash_steps.onnx
```

Pass `--test labels/<clip>.json` with a clip left out of `--train` to see how it does on footage it has not seen.

## Hand joints and palms

`hand_palm.onnx` and `hand_pose.onnx` are needed by the site step classifier above, which looks at the square round the palms the palm detector finds; with only the reference model they are optional. With both, the camera view draws each washing hand as a skeleton of 21 joints in deep teal, with white-centred joints and the fingertips in amber. The joints only draw: the wash is judged by the step classifier.

- On the two sample clips the palm detector found at least one hand in every frame of every step, and in 95–99% of the frames with hands but no step.

- Source: MediaPipe Hands as converted in the OpenCV Zoo, https://github.com/opencv/opencv_zoo, `models/palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx` (SHA256 `78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c`) and `models/handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx` (SHA256 `db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c`). License: Apache-2.0.
- `app/handpose.py` ports the zoo's pre- and post-processing to ONNX Runtime: the palm detector on the hand-wash zone's bounding box, then the landmark model on each palm, turned upright. Up to two hands; a hand the landmark model gives under 0.8 is dropped.
- Joints are found again every 0.1 s while a wash is in view, about 16 ms each time on the sink area. The incident snapshot shows the last joints found.
- On the two sample clips the joints were found in 70–75% of reads taken every 0.5 s, and two hands in about 29%. Fingers tightly interlaced and parts of rinsing lose the hands; the overlay then shows the wash tag without a skeleton.
- A camera whose rules are all hand-wash rules no longer runs the person detector, which no rule there uses.

```powershell
Invoke-WebRequest -Uri https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx -OutFile models/hand_palm.onnx
Invoke-WebRequest -Uri https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx -OutFile models/hand_pose.onnx
```
