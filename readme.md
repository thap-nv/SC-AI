# AI Safety & Compliance Monitoring POC

Hệ thống xem camera nhà máy và công xưởng, đối chiếu luật an toàn lao động, và tạo incident để người vận hành xác nhận. AI không ra quyết định kỷ luật.

Bản đặc tả gốc nằm ở [docs/SPEC.md](docs/SPEC.md). Bản đó viết cho nhà máy cà phê. Từ 10/2026 phạm vi đổi sang nhà máy và công xưởng nói chung: bỏ dây chuyền hạt cà phê, hairnet và đồng phục; trọng tâm là đồ bảo hộ lao động (mũ, đồ bảo hộ, khẩu trang).

## Chạy trên máy

Cần Docker Desktop. Trong thư mục dự án:

```text
copy .env.example .env
docker compose up -d --build
```

Lần đầu sẽ tải image và build, có thể mất vài phút.

Mở:

| Việc | Địa chỉ |
|---|---|
| Dashboard | http://localhost:3000 |
| API Swagger | http://localhost:8000/docs |
| MinIO console | http://localhost:9101 |
| Worker health | http://localhost:8081/health |

Postgres và Redis chỉ chạy trong mạng Docker, không mở cổng ra máy.

Tài khoản demo:

| Người dùng | Mật khẩu | Việc được làm |
|---|---|---|
| admin | admin123 | Camera, vùng, luật |
| safety | safety123 | Duyệt incident |
| viewer | viewer123 | Chỉ xem |

MinIO: `safetyadmin` / `safetyadmin123`.

Đưa lên server Ubuntu, sau nginx và HTTPS: xem [docs/DEPLOY.md](docs/DEPLOY.md).

## Bản đồ hệ thống

```mermaid
flowchart LR
  cam[RTSP hoặc MP4] --> worker[AI worker]
  worker --> detect[Phát hiện và theo dõi]
  detect --> zones[Vùng]
  zones --> rules[Luật]
  rules --> api[Backend]
  api --> db[(PostgreSQL)]
  api --> files[(MinIO)]
  api --> redis[(Redis)]
  redis --> ui[Dashboard]
  ui --> api
```

Worker xử lý hình tại chỗ. API chỉ nhận incident, ảnh, và cấu hình. Dashboard nhận incident mới qua Server-Sent Events.

## Tình huống mẫu

Dữ liệu khởi tạo có nhà máy Factory POC và một camera giám sát an toàn lao động:

- Camera `CAM-WORKSHOP-01` (Workshop Camera 01) nhìn xuống sàn xưởng.
- Vùng **Workshop floor**, loại **PPE required area**: ai đứng trong vùng phải đủ đồ bảo hộ. Người ở trong vùng khi chân nằm trong polygon.
- Ba luật, mỗi món một luật:

| Luật | Incident | Mức |
|---|---|---|
| Helmet required | Thiếu mũ bảo hộ | HIGH |
| Protective clothing required | Thiếu đồ bảo hộ (áo liền quần) | HIGH |
| Mask required | Thiếu khẩu trang | MEDIUM |

Không có luật giày bảo hộ: với hình camera giám sát, màu sắc không phân biệt được giày bảo hộ với giày thường, và chân hay bị bàn che. Backend vẫn nhận điều kiện `SHOES_MISSING` để bật lại khi có `ppe.onnx` nhận được giày.

Mỗi món có ba trạng thái: Có, Không, Không xác định. Chỉ **Không** mới tạo incident, sau khi giữ đủ 2 giây. Không xác định, ví dụ người quay lưng nên không thấy mặt, hoặc chân bị che, thì không báo. Kết quả của một người chỉ chốt khi bốn trong sáu lần đọc gần nhất giống nhau.

Mỗi luật chạy riêng, nên một người thiếu hai món tạo hai incident. Người bị tracker mất dấu rồi bắt lại với số mới, cùng luật, gần chỗ cũ và trong thời gian cooldown thì vẫn dùng incident cũ. Muốn một khu chỉ bắt mũ thì tắt các luật còn lại ở trang **Rules**, hoặc vẽ thêm vùng và gắn luật cho vùng đó.

Video MP4 tải lên được phát lặp như một camera. Mỗi lần video quay về đầu là một cảnh mới: incident đang mở được đóng, không nối sang lượt sau. Từ lượt phát thứ hai, mỗi luật báo tối đa một incident trong mỗi khoảng cooldown (tính từ lúc incident trước của luật đó kết thúc), để các lượt lặp không tạo incident trùng; luật rửa tay cũng vậy. Cooldown chỉnh ở trang **Rules**, worker áp dụng sau khoảng 1 giây; đặt 0 để tắt giới hạn. Lượt phát đầu và camera RTSP báo bình thường. Tắt camera cũng đóng các incident đang mở.

Trên ảnh camera, mỗi người có một thẻ: số, rồi một chữ cho mỗi món được kiểm tra: **H** mũ, **C** đồ bảo hộ, **M** khẩu trang. Xanh là có, đỏ là thiếu, xám là chưa xác định. Khung đỏ là có vi phạm. Chú giải nằm ở góc dưới bên phải.

Camera thứ hai, `CAM-RESTRICTED-01` (Restricted Area Camera 01), giám sát một khu vực hạn chế, ví dụ làn cân hay làn kiểm tra trong cảng:

| Luật | Incident | Mức |
|---|---|---|
| No entry for people | Có người trong khu vực hạn chế | HIGH |
| No entry for vehicles except forklifts | Có phương tiện trong khu vực hạn chế | HIGH |

Không ai được vào. Ô tô, xe tải, xe buýt, xe máy không được vào; xe nâng được phép. Người ngồi trong xe, ví dụ tài xế xe nâng, không bị tính là người đi vào. Model người (COCO) không có lớp xe nâng, nên xe nâng do `models/forklift.onnx` tìm (YOLOv8n học trên ảnh xe nâng, giấy phép AGPL-3.0, xem `models/README.md`); thiếu file này thì xe nâng chỉ hiện khi model người tình cờ thấy nó là xe tải. Loại xe do CLIP xác định (`models/clip_vision.onnx` và `models/vehicle_types.npz`); thiếu hai file này thì lấy loại của detector, và xe nâng mà model người nhận là xe tải sẽ bị báo. Vùng "Restricted lane" lúc tạo chỉ là vùng tạm ở giữa khung hình: upload video rồi vào **Draw zones**, bấm **Redraw** để vẽ đúng làn. Người được tính là trong vùng theo điểm giữa đáy khung (chỗ bàn chân): người đứng ngay trên vạch mép vùng có thể nằm ngoài vài pixel, nên vẽ vùng ra ngoài vạch nếu vạch cũng thuộc khu cấm.

Trên video cảng `sample-data/videos/retricted area 2.mp4`, camera theo được xe nâng gần suốt đường đi và ghi là được phép, ô tô bị báo suốt, người đứng xa trong làn bị báo. Trước đây, khi model người còn chạy trên nguyên khung hình và chưa có `forklift.onnx`, xe nâng chỉ có khung trong 0,8 giây cuối và người đứng xa không bao giờ được thấy. Camera này chạy khoảng 9 FPS trên máy thử, vì mỗi frame chạy cả model người lẫn model xe nâng.

Camera thứ ba, `CAM-HANDWASH-01` (Handwash Station Camera 01), đặt phía trên bồn rửa, nhìn thẳng xuống, kiểm tra quy trình rửa tay thường quy 6 bước của Bộ Y tế (cùng thứ tự với WHO):

| Bước | Động tác | Model của site (`handwash_steps.onnx`) | Model tham khảo (`handwash.onnx`) |
|---|---|---|---|
| 1 | Chà hai lòng bàn tay vào nhau | Có | Không: model không có lớp này |
| 2 | Chà lòng bàn tay lên mu và kẽ ngoài ngón tay bàn tay kia | Có | Có |
| 3 | Chà hai lòng bàn tay, miết mạnh các kẽ ngón | Có | Không: model không có lớp này |
| 4 | Chà mặt ngoài các ngón tay vào lòng bàn tay kia | Có | Không: nhầm sang bước 6 ở 9/10 ảnh thử |
| 5 | Xoay ngón cái trong lòng bàn tay kia | Có | Có |
| 6 | Xoay các đầu ngón tay trong lòng bàn tay kia | Có | Có, nhưng gần như luôn tính là có |

- Vùng **Sink**, loại **Hand-wash station**: vẽ quanh bồn rửa, chỗ tay rửa. Model của site tìm bàn tay trong vùng này (bằng `models/hand_palm.onnx`) rồi nhìn một khung vuông quanh hai bàn tay, nên vẽ vùng rộng hay hẹp hơn một chút không làm đổi kết quả.
- Luật **WHO 6-step hand washing** (incident "Hand wash incomplete", mức MEDIUM). Mỗi lần rửa được chấm một lần, khi tay rời bồn quá 1,5 giây (`HANDWASH_GAP_S`) hoặc khi video upload chạy lại từ đầu. Bước nào được tính chưa đủ 1,5 giây (ô "Min per step" ở trang **Rules**) là thiếu, và tạo một incident cho cả lần rửa. Ảnh incident ghi các bước bị thiếu. Tay xuất hiện dưới 3 giây thì không tính là một lần rửa.
- **Model của site** `models/handwash_steps.onnx` (có file này thì worker dùng nó, cần thêm `hand_palm.onnx` và `hand_pose.onnx`): MobileNetV3-Small phân loại khung quanh hai bàn tay thành không có tay, có tay nhưng không phải bước nào (làm ướt, lấy xà phòng, xả nước), hoặc một trong 6 bước. Bước 2, 5, 6 phải làm cho từng tay nên được nhận riêng tay trái và tay phải (tay được làm sạch: mu tay nào, ngón cái nào, đầu ngón của tay nào). Mỗi tay cần ít nhất một nửa thời gian tối thiểu (0,75 giây). Thiếu một tay thì bước đó bị báo thiếu cho tay đó, ví dụ "5 Thumbs: right hand only". Mỗi lần đọc cho xác suất của từng bước, và mỗi bước được cộng thời gian theo xác suất đó, nên cùng một video chạy lại cho cùng kết quả. Huấn luyện bằng `tools/handwash_classifier/train_handwash.py` trên hai clip mẫu. Nhãn từng đoạn thời gian nằm trong `tools/handwash_classifier/labels/`, sửa được rồi huấn luyện lại.
- Trên vòng lặp camera thật, chạy video ghép 4 lần với vùng vẽ hẹp (22–82% bề ngang) và vùng vẽ rộng (6–92%), lần nào cũng ra cùng kết quả, khớp với lời người rửa: lần rửa đúng qua, lần rửa sai thứ nhất thiếu bước 3 và bước 5 tay trái (chỉ xoay ngón cái phải), lần rửa sai thứ hai thiếu bước 4. Mới chỉ có hai clip của một người ở một bồn, nên người khác, áo khác, ánh sáng khác cần thêm clip để huấn luyện. Chi tiết và số đo xem `models/README.md`.
- **Model tham khảo** `models/handwash.onnx` (YOLOv8n-seg của repo `synthetic-hand-washing`, chỉ học trên ảnh dựng 3D) chỉ dùng khi không có model của site. Với model này đặt `HANDWASH_SKIP_STEPS=fingers`. `HANDWASH_SCALE` (mặc định 0.6) thu nhỏ khung hình cho camera gần bồn. Chi tiết và giấy phép (trọng số Ultralytics là AGPL-3.0) xem `models/README.md`.
- Video upload chạy đúng tốc độ thật như camera thật.

Trên camera, tay đang rửa có thẻ "Wash Ns" và số của từng bước được kiểm tra: xanh là xong, xám là chưa, đỏ là thiếu (chỉ có trên ảnh incident). Có `models/hand_palm.onnx` và `models/hand_pose.onnx` (MediaPipe Hands từ OpenCV Zoo, Apache-2.0) thì mỗi bàn tay được vẽ thành bộ khung 21 khớp màu xanh teal, đầu ngón tay màu vàng cam, kiểu đang quét cử chỉ tay. Khung này chỉ để hiển thị, không dùng để chấm bước. Camera chỉ có luật rửa tay thì không chạy nhận diện người nữa.

Các mẫu luật vùng nguy hiểm máy và làn forklift vẫn còn trong trang **Rules** cho camera sau này.

Trong **AI Mode: DEMO**, ở khu vực hạn chế có một người đi vào, một ô tô chạy vào rồi ra, và một xe nâng đỗ bên trong (được phép). Trên sàn xưởng, worker tự tạo năm công nhân: một người đủ đồ, ba người mỗi người thiếu một món, và một người đứng yên mà AI không đọc được (để thấy Không xác định không báo). Bốn người đầu lần lượt đi vào rồi ra khỏi vùng. Ở bồn rửa, mỗi 70 giây có một lần rửa đủ 6 bước (không báo), rồi một lần chỉ làm 3 bước đầu (báo thiếu). Demo không cần file model. Banner trên dashboard ghi rõ đang ở DEMO.

Nút **Simulate an incident** trên trang camera giữ mọi người đứng trong vùng vài giây để luật chạy ngay.

Database đã khởi tạo từ bản cà phê được chuyển một lần khi backend khởi động: năm camera cũ (`CAM-PACK-01`, `CAM-PROD-01`, `CAM-MACHINE-01`, `CAM-WAREHOUSE-01`, `CAM-BEAN-01`) bị xóa cùng vùng, luật, incident và phần duyệt của chúng; camera tự thêm bằng tay được giữ; camera xưởng được thêm vào. Ảnh và video cũ trong MinIO không bị xóa. Muốn sạch hẳn thì chạy `docker compose down -v`.

## Việc nên thử

1. Đăng nhập `admin`.
2. Mở Workshop Camera 01. Bật **Show AI overlay** để thấy người, vùng và món đồ bảo hộ đang thiếu trên từng người. Khung đỏ là vi phạm, xám là chưa xác định, xanh là đủ đồ.
3. Vào **Draw zones**, bấm các góc trên ảnh, lưu polygon.
4. Vào **Rules**, chọn mẫu luật và vùng.
5. Đợi khoảng 20 giây, hoặc bấm Simulate. Incident xuất hiện ở Overview mà không cần tải lại trang.
6. Mở incident, xem ảnh, bấm Confirm, False positive, hoặc Resolve.

Upload MP4 ở trang camera nếu muốn dùng video thật làm nền. Worker phát lại file đó. RTSP điền vào ô stream URL, dạng `rtsp://user:password@địa-chỉ/stream`. Mật khẩu không được ghi ra log và không trả về nguyên văn trên API.

## Vùng và camera bị lệch

Người ở trong vùng khi điểm chân, tức giữa cạnh dưới của khung người, nằm trong polygon. Vùng vẽ được bao nhiêu góc cũng được, miễn các cạnh không cắt nhau. **Redraw** sửa hình vùng tại chỗ, luật và incident cũ vẫn gắn với vùng.

Mỗi vùng lưu khung hình đã dùng để vẽ. Khoảng mỗi giây, worker so khung hình hiện tại với khung đó:

| Kết quả so | Vùng |
|---|---|
| Lệch dưới 1% | Giữ nguyên |
| Lệch 1–20% | Dịch theo camera, nhãn ghi "auto-aligned" |
| Lệch hơn 20%, không khớp, hoặc vùng ra ngoài khung quá 40% | Tạm dừng: không vẽ trên khung hình, luật của vùng không chạy. Tự bật lại khi góc nhìn khớp lại |

Tạm dừng hay bật lại cần hai lần so liên tiếp cùng kết quả.

Không muốn vùng theo camera thì tắt **Follow camera moves** trong form vẽ trước khi lưu, hoặc bấm **Unlink** ở vùng đã lưu. Vùng không gắn thì nằm cố định đúng chỗ đã vẽ, không bao giờ tạm dừng, và luôn được kiểm tra, kể cả trên camera nhiều góc. Hợp với camera cố định, hoặc video đổi cảnh giữa chừng (vùng gắn sẽ tạm dừng ở những đoạn không khớp). **Redraw** giữ lựa chọn hiện tại của vùng.

Camera xoay giữa nhiều góc (PTZ preset) thì bật **Camera has several views** trong Camera settings. Mặc định tắt. Các vùng khóa cùng một khung hình là một góc nhìn: mở Draw zones khi camera đang ở góc đó, vẽ hoặc bấm **Lock to this view** cho từng vùng của góc đó. Worker chỉ dùng góc nhìn khớp nhất với khung hình hiện tại; vùng của góc khác bị ẩn và không chạy luật. Đổi góc cần góc mới khớp hơn ít nhất 25% trong hai lần so liên tiếp. Không bật cho camera cố định: hai vùng vẽ vào hai ngày khác nhau sẽ thành hai góc nhìn và ẩn lẫn nhau. Trang camera có mục **Zones** ghi trạng thái từng vùng. Vùng vẽ trước khi có chức năng này giữ nguyên vị trí; bấm **Lock to this view** trong Draw zones nếu vùng đang khớp với khung hình.

## CPU và GPU

Mặc định chạy CPU. Dashboard không cần GPU.

Mỗi camera chạy model với `AI_THREADS` luồng, mặc định 2, và các luồng nghỉ giữa hai frame. Trên máy 22 luồng CPU, 4 camera đạt khoảng 27 FPS mỗi camera và dùng khoảng 4.5 lõi. Một camera trên máy nhiều lõi có thể tăng `AI_THREADS`; nhiều camera thì giữ thấp. Worker đọc cấu hình camera mỗi giây và gửi trạng thái lên backend hai lần mỗi giây, không theo từng frame.

`AI_MODE=REAL` dùng YOLOX-Nano khi có `models/person.onnx`, nhận diện toàn thân mà không yêu cầu thấy mặt. Khung 16:9 được chia thành hai ô vuông chồng lên nhau rồi mới đưa vào model, nên người ở xa hiện to gấp 1,8 lần: trên video cảng, người đứng xa cao 65 px được thấy đủ chắc để theo dõi ở 44/49 frame thay vì 2/49. Đổi lại model người chạy khoảng 36 ms một frame thay vì 18 ms. Cách tải model chính thức và checksum nằm ở [models/README.md](models/README.md). Không có model thì dùng OpenCV HOG. Khi chưa có `ppe.onnx`, worker đọc màu trên từng người, chỉ phù hợp kiểm thử POC với video rõ, chưa phù hợp triển khai thật:

- **Mũ:** mũ cứng trắng, vàng, cam hoặc đỏ ngay trên mặt là có; tóc hoặc da đầu là không.
- **Đồ bảo hộ:** áo liền quần, nghĩa là thân và chân cùng màu đồ lao động (xám, be, trắng, xanh). Áo màu sặc sỡ, hoặc áo màu đồ lao động với quần tối, là không. Không thấy chân thì để Không xác định.
- **Khẩu trang:** cần `models/face.onnx` (detector mặt YuNet, MIT) để tìm mặt. Có thêm `models/mask.onnx` thì một model nhỏ đã train phân loại từng khuôn mặt: đeo đúng, không đeo, đeo sai cách; bắt được cả mặt nghiêng không đeo khẩu trang. Khẩu trang kéo xuống dưới cằm vẫn chưa bắt được. Không có `mask.onnx` thì dùng màu: thấy màu khẩu trang ở cằm là có, mặt nhìn thẳng mà cằm cùng màu da trán là không.

Trên video xưởng 30 giây khoảng 15 người, cách này mở đúng 2 incident cho 2 vi phạm thật (một người không đội mũ, một người mặc áo thun) và không báo sai. Video đó không có ai bỏ khẩu trang, nên phần "không khẩu trang" mới kiểm tra trên ảnh tổng hợp. Chi tiết và cách tải `face.onnx` ở [models/README.md](models/README.md).

Video quay demo nên thấy trọn người từ mũ đến chân, người không che nhau, người cao ít nhất khoảng 1/4 khung hình; người vi phạm khẩu trang thì quay mặt về camera. Worker xử lý khung 1280x720.

Đặt file ONNX vào thư mục `models/`:

| File | Hợp đồng |
|---|---|
| `person.onnx` | YOLOX-Nano chính thức: đầu vào 1x3x416x416 BGR 0..255, đầu ra raw 1x3549x85; class COCO 0 là người. |
| `forklift.onnx` | Detector xe nâng YOLOv8, export bằng `tools/forklift_yolo/export_forklift_onnx.py`: đầu vào RGB 0..1 (POC dùng 1x3x512x896), đầu ra YOLO `(1, 4 + lớp, anchors)`, tên lớp đọc từ file, chỉ giữ lớp `forklift`. Chỉ chạy trên camera có luật người hoặc xe trong vùng. |
| `face.onnx` | YuNet 2023mar của OpenCV Zoo, MIT. Tìm mặt trong vùng đầu của từng người để kiểm tra khẩu trang và mũ. |
| `mask.onnx` | MobileNetV3-Small phân loại khuôn mặt: đeo sai cách, đeo đúng, không đeo. Train bằng `tools/mask_classifier/train_mask.py`; nguồn dữ liệu và giấy phép ở [models/README.md](models/README.md). |
| `ppe.onnx` | Detector đồ bảo hộ, chạy trên ảnh cắt của từng người. Tám lớp: 0 helmet, 1 no_helmet, 2 clothing, 3 no_clothing, 4 shoes, 5 no_shoes, 6 mask, 7 no_mask. Chấp nhận tensor Nx6 hoặc đầu YOLO `(1, 12, anchors)`. Mỗi món lấy box mạnh nhất nằm đúng phần cơ thể: mũ ở đầu, khẩu trang ở mặt, áo ở thân, giày ở chân. Cách train và export ở [models/README.md](models/README.md) và `tools/ppe_yolo`. |

GPU trên máy Linux có NVIDIA Container Toolkit:

```text
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Image mặc định vẫn là CPU. Muốn inference CUDA thì cài `onnxruntime-gpu` trong image worker và giữ `AI_DEVICE=cuda`.

## Giấy phép model

- OpenCV và bộ HOG phát hiện người: Apache-2.0.
- Theo dõi người: ByteTrack qua thư viện supervision, Apache-2.0.
- ONNX Runtime: MIT.

Detector người dùng YOLOX (Apache-2.0), không dùng Ultralytics YOLO vì giấy phép AGPL. Hai model tùy chọn là ngoại lệ, đều là trọng số Ultralytics YOLOv8 nên theo AGPL-3.0: `handwash.onnx` và `forklift.onnx`. Cần xem lại trước khi bán sản phẩm; chi tiết ở [models/README.md](models/README.md).

## Theo dõi

- `http://localhost:8000/health`, `/ready`, `/metrics`
- `http://localhost:8081/health`, `/ready`, `/metrics`

Metric của worker gồm trạng thái camera, số frame, FPS, độ trễ inference, số phát hiện, số incident, và frame bị bỏ.

Trang Evaluation cho tỷ lệ false positive trên các incident đã được người duyệt. Đó chưa phải độ chính xác của model. Recall cần nhãn các vụ bị bỏ sót, POC này chưa thu thập phần đó.

## Dừng và xóa dữ liệu

Dừng, giữ database và ảnh:

```text
docker compose down
```

Xóa toàn bộ dữ liệu POC, gồm Postgres và MinIO:

```text
docker compose down -v
docker compose up -d --build
```

## Kiểm tra đã chạy

```text
docker compose ps
```

Backend và worker phải healthy. Đăng nhập xong phải thấy camera Workshop Camera 01 và các incident mẫu về mũ, đồ bảo hộ và khẩu trang.
