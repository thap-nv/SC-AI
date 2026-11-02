# Nhận diện thương hiệu Trung Nguyên Legend trong dashboard

Tài liệu này ghi lại cách giao diện `apps/frontend` áp dụng nhận diện của Tập đoàn Trung Nguyên Legend, để ai sửa UI sau cũng giữ được cùng một ngôn ngữ.

Nguồn:
- Website https://trungnguyenlegend.com (CSS theme `legend_child_theme`, logo, banner trang chủ), khảo sát tháng 10/2026.
- Bản thiết kế "Safety Monitor" trên Claude Design (`Safety Monitor.dc.html`). Bảng màu và bố cục hiện tại lấy từ bản này.

Branch `trung-nguyen-safety` dùng giao diện này trên chức năng của `madison-factory-safety` (PPE, vùng cấm, rửa tay; bố cục điện thoại và màn làm việc gọn một màn hình). Hai branch chỉ khác nhau ở theme.

## 1. Thương hiệu nói gì

- **Kiến trúc thương hiệu.** Trung Nguyên Legend là thương hiệu tập đoàn, cao cấp. Dưới nó có các thương hiệu tiêu dùng: Trung Nguyên (khiên đỏ, chữ vàng chanh) và G7. Dashboard là công cụ nội bộ của nhà máy, nên theo **thương hiệu tập đoàn (Legend)**.
- **Biểu tượng.** Mặt trống đồng Đông Sơn: ngôi sao mặt trời ở tâm, các vành hoa văn đồng tâm.
- **Giọng điệu.** Khát vọng, trang trọng: "Cà phê năng lượng – Cà phê đổi đời".
- **Thị giác.** Nền tối màu espresso, chữ hoa kiểu khắc La Mã giãn chữ, dải băng tối chữ vàng, đường kẻ mảnh có hình thoi.

## 2. Bảng màu (token trong `tailwind.config.js`)

| Token | Giá trị | Dùng cho |
|---|---|---|
| `ink` | `#17110C` | Sidebar, thanh trên và thanh tab trên điện thoại, thẻ tối (KPI đầu hàng, People and vehicles, New rule, Frame pipeline), nút chính, toast |
| `ink-soft` / `ink-raised` / `ink-edge` | `#2C2016` / `#221810` / `#33261B` | Hover nút chính, ô con và viền trên nền tối |
| `paper` | `#F3EDE3` | Nền trang |
| `surface` | `#FFFDF9` | Nền thẻ (`.panel`), ô nhập, ngăn kéo |
| `cream` / `sand` | `#FBF7F0` / `#F8F2E8` | Thanh trên cùng, thanh dưới bảng, ô camera; đầu bảng và hộp ghi chú |
| `line` (+ `soft`, `muted`, `strong`) | `#E6DCCB` … | Viền thẻ, kẻ bảng, viền ô nhập |
| `bark-*` | `#1E150E` → `#A3927F` | Chữ trên nền sáng (900 tiêu đề, 800 nội dung, 500 phụ) |
| `husk-*` | `#FBF4E8` → `#6E5D4A` | Chữ trên nền tối |
| `gold-500` | `#C99A4A` | Vạch nhấn, hình thoi, viền nút phụ, vạch mục đang chọn ở thanh tab |
| `gold-300` / `gold-200` | `#E3BE74` / `#F3DEB0` | Chữ vàng trên nền tối, số KPI tối, vùng đã lưu trên canvas |
| `gold-700` / `gold-800` | `#8A5A0E` / `#5E3D08` | Liên kết, giờ sự cố và chữ vàng trên nền sáng |
| `crimson-600` / `crimson-700` | `#9E2A1F` / `#8E2219` | CRITICAL, nút "Confirm violation", số đếm NEW, toast "New alert", cảnh báo vùng bị tạm dừng |
| `leaf-600` | `#3E8A52` | Camera đang chạy, công tắc bật, AI Mode REAL |

Quy tắc:

- **Không dùng `gold-500` cho chữ trên nền sáng** (tương phản thấp); dùng `gold-700`.
- **Nút:** `PrimaryButton` nền espresso chữ `gold-200`, `OutlineButton` viền vàng chữ nâu vàng, `GhostButton` viền xám, `DangerButton` đỏ `crimson-600`. Nút "Save rule" trên thẻ tối dùng dải vàng `bg-gold-bar`.
- **Mức độ (severity)** — `SEVERITY` trong `components/ui.tsx`: CRITICAL đỏ, HIGH vàng hổ phách, MEDIUM nâu nhạt, LOW xanh xám. Biểu đồ dùng đúng các màu `bar` này. Màu `hud` (nhãn trên ảnh) là sắc đậm của cùng màu để chữ sáng đặt lên vẫn đọc được.
- **Trạng thái (status)** — `StatusPill`: NEW vàng, CONFIRMED đỏ, FALSE_POSITIVE xanh rêu, RESOLVED xanh xám.
- **Toast:** cảnh báo mới (toast duy nhất có nút "Review →") nền `crimson-600`, hình thoi nhấp nháy; toast thường nền espresso viền vàng.
- **AI Mode: DEMO** luôn là viên thuốc màu hổ phách ở thanh trên cùng, theo yêu cầu trong `docs/SPEC.md`.

## 3. Chữ

| Vai trò | Font | Ghi chú |
|---|---|---|
| Tiêu đề trang, số KPI, chữ thương hiệu | **Cinzel** (`font-display`) | Thay cho **Trajan Pro 3** (font thương mại website dùng). |
| Giao diện, nội dung | **Be Vietnam Pro** (`font-sans`) | Đủ dấu tiếng Việt. |
| Giờ, mã camera/sự cố, số đo | **JetBrains Mono** (`font-mono`) | |

**Cinzel không có dấu thanh tiếng Việt** (ơ, ư, ạ…ỹ). Mọi chỗ in chữ động bằng Cinzel phải qua `displayFont(text)` trong `lib/labels.ts`. Hàm này trả về `font-sans` khi chuỗi có các ký tự đó, ví dụ tiêu đề trang là tên camera "Camera dây chuyền hạt 01". Tiêu đề trang (`Shell`) và tiêu đề ngăn kéo sự cố đã đi qua hàm này.

Ba font được tải qua `next/font/google` và tự host khi build, nên lúc chạy trong nhà máy không cần Internet.

## 4. Thành phần dùng chung

- `components/ui.tsx`:
  - Hiển thị: `Kpi` (thẻ sáng/tối, biến thể `critical`), `SeverityTag`, `StatusPill`, `Snapshot` (ảnh từ API có token).
  - Điều khiển: `Switch` (tone `leaf` hoặc `gold`), `Checkbox`, `Segmented`.
  - Nút: `PrimaryButton`, `OutlineButton`, `GhostButton`, `DangerButton`.
  - `Drawer`: ngăn kéo trượt từ phải (Escape hoặc bấm ra ngoài để đóng), dùng cho "Camera settings".
  - Hoạ tiết: `Rule`, `Emblem`, `Diamond`, `LiveDot`, `RecDot`.
- `components/shell.tsx`:
  - Từ `md` trở lên: sidebar espresso có `Emblem`, "TRUNG NGUYÊN LEGEND", mục đánh số La Mã và số sự cố NEW; thanh trên cùng có AI Mode và đồng hồ giờ nhà máy.
  - Dưới `md`: thanh trên espresso và thanh tab dưới (icon thay số La Mã), xem mục 5.
  - Breadcrumb và vùng nút hành động của trang.
  - Thanh trên cùng luôn cao 56px; chữ AI Mode bị cắt bớt thay vì xuống dòng.
  - `dense`: đầu trang gọn (tiêu đề 26px, bỏ câu "AI raises an alert…", ít khoảng trống) cho màn làm việc: chi tiết camera, Incidents. Các màn này dùng hết bề ngang, lề hai bên bằng nhau; các trang khác vẫn giới hạn 1680px.
  - `fill`: từ `md`, trang cao đúng một màn hình và phần tử con cuối chiếm phần còn lại. Incidents dùng để bảng cuộn trong khung của nó, bộ lọc và tên cột luôn hiện.
  - `subtitle`: dòng dưới tiêu đề, thay câu khẩu hiệu (chi tiết camera: trạng thái, mã, khu vực, số luật).
  - Mở luồng sự kiện (SSE) và bật toast khi có cảnh báo mới.
- `components/providers.tsx`: toast và ngăn kéo xem xét sự cố, gọi qua `useApp()` từ bất kỳ trang nào.
- `components/incident-drawer.tsx`: ngăn kéo xem xét. Chỉ hiện các bước mà backend cho phép (`REVIEW_TRANSITIONS`).
- `lib/live.ts`: kênh sự kiện trong trang (`useIncidentEvents`), để các trang tự làm mới khi có sự cố mới hoặc vừa được xem xét.
- Thẻ tối đầu hàng (KPI, People and vehicles, New rule) có hoạ tiết tia sáng vàng ở góc trên phải (`bg-rays`, `bg-rays-soft`).
- **`Emblem`** là hoạ tiết vẽ lại theo trống đồng, **không phải logo chính thức**. Khi có logo do phòng thương hiệu cấp, thay ở sidebar, thanh trên điện thoại, trang đăng nhập và `app/icon.svg`.

## 5. Điện thoại (dưới `md`, 768px)

Người dùng điện thoại chủ yếu là quản lý an toàn đang ở xưởng: nhận cảnh báo, mở ra xem, quyết định. Layout ưu tiên việc đó.

- **Khung.** Thanh trên espresso cao 56px gồm `Emblem`, "Safety Monitor", chip "AI Mode: …" và avatar viền vàng mở menu tài khoản (tên, vai trò, Sign out). Năm mục chuyển xuống thanh tab cố định ở đáy, có số sự cố NEW. Đồng hồ nhà máy chỉ hiện trên màn rộng.
- **Đầu trang.** Chỉ giữ link quay lại và tiêu đề (26px). Eyebrow và câu "AI raises an alert…" bị ẩn vì thanh trên đã nói điều đó. Nút hành động trải hết chiều ngang.
- **Bảng thành thẻ.** Incidents và Rules hiển thị mỗi dòng thành một thẻ, với mức độ và trạng thái luôn thấy được; bảng chỉ dùng từ `md`.
- **Bộ lọc sự cố.** Chỉ để thanh trạng thái (New, Confirmed…); mức độ, camera, vùng, vi phạm và ngày nằm sau nút "Filters", nút này hiện số bộ lọc đang bật. Cả thanh dính ngay dưới thanh trên khi cuộn.
- **Thứ tự.** Overview đưa "Awaiting review" lên trước biểu đồ. Chi tiết camera xếp khung hình, rồi "People and vehicles", "Zones", "Recent alerts", đúng thứ tự trong DOM.
- **KPI** hai ô một hàng; ô tối đầu tiên trải hai cột.
- **Canvas vẽ vùng** vẽ nét, điểm góc và nhãn theo tỉ lệ hiển thị thật, nên nhãn vẫn cao ~13px trên điện thoại.
- **Toast** trải ngang ngay trên thanh tab. Thanh tab tự chừa khoảng `safe-area-inset-bottom` (viewport `cover` trong `app/layout.tsx`).

## 6. Màn rộng: hai màn làm việc nằm gọn trong một màn hình

- **Incidents.**
  - Một thanh lọc: trạng thái dạng tab; mức độ, camera, vùng, vi phạm và ngày dạng dropdown, rộng vừa giá trị đang chọn (`field-sizing: content`, có trên Chrome/Edge); "Clear" khi đang lọc.
  - Chọn camera thì danh sách vùng chỉ còn vùng của camera đó.
  - Bảng cuộn trong khung, tên cột dính trên cùng; thanh dưới bảng có tổng số và "Show more".
  - Mỗi sự cố một dòng; sự cố của hôm nay không ghi ngày.
- **Chi tiết camera.**
  - Khung hình co theo chiều cao màn hình: `max-h-[calc(100dvh-284px)]`, 284px là phần đầu trang, thanh công cụ và lề. Sửa đầu trang thì sửa số này.
  - Cột phải (People and vehicles, Zones, Recent alerts) cao đúng bằng khung hình và tự cuộn bên trong.
  - Số đo (AI FPS đo được / mục tiêu, inference, frames, dropped) nằm trên thanh công cụ của khung, cạnh công tắc overlay và nút toàn màn hình. Cảnh báo vùng bị tạm dừng nằm đè lên đầu khung hình.
  - Bật/tắt camera nằm ngay trên viên trạng thái dưới tiêu đề (chỉ admin thấy công tắc): "Camera on · Live" xanh, "Camera on · Offline" xám, "Camera off" hổ phách để dễ thấy camera đang không giám sát.
  - Các cài đặt còn lại (AI FPS, nguồn RTSP/file, worker, nhiều view, upload MP4) nằm trong ngăn kéo "Camera settings", mở bằng nút Settings (chỉ admin).

## 7. Những gì cố ý chưa làm theo design

- **"Undo decision"**: backend coi quyết định review là một chiều và lưu vết (`OperatorFeedback`), nên ngăn kéo không có nút hoàn tác.
- Lớp phủ khung người/vùng trên ảnh camera vẫn do ai-worker vẽ sẵn vào snapshot, không vẽ lại ở trình duyệt. Màu của lớp phủ này (`apps/ai-worker/app/drawing.py`) không theo thương hiệu.
- Ngôn ngữ giao diện vẫn là tiếng Anh.
