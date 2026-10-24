# Nhận diện thương hiệu Madison Technologies trong dashboard

Tài liệu này ghi lại cách giao diện `apps/frontend` áp dụng nhận diện của Madison Technologies, để ai sửa UI sau cũng giữ được cùng một ngôn ngữ.

Nguồn: website https://madison-technologies.com (madison.dev chuyển hướng về đây), khảo sát tháng 10/2026. Gồm:
- `assets/index-*.css`: biến màu (`--lp-brand`, `--lp-bg-primary`, `--primary`, `--destructive`…), bo góc, gradient `.section-gradient-text`.
- `madison-assets/logos/madison/madison-logo.svg`: biểu tượng logo.
- `favicon/madison-fav.svg`: favicon.

## 1. Thương hiệu nói gì

- **Màu.** Cyan Madison `#48C6FD` là màu thương hiệu duy nhất. Website đặt nó trên nền navy rất tối (`#0A1525`, `#0D1F35`).
- **Thị giác.** Tối, gọn, có vầng sáng cyan phía sau hero.
  - Nút chính nền cyan, chữ đen/navy.
  - Chữ nhấn dùng gradient cyan `#5DD0FF → #48C6FD → #29B3F5 → #1AA0E8`.
  - Bo góc 10px (`--radius: .625rem`).
- **Logo.** Biểu tượng cyan một màu, đi kèm chữ "MADISON" (đậm, giãn chữ 0.32em, tô gradient) và "TECHNOLOGIES" (nhỏ, xám, giãn chữ 0.24em). Trên website phần chữ là chữ thật, không phải ảnh.

## 2. Cách dashboard áp dụng

Dashboard là công cụ vận hành, phải đọc nhanh trong nhiều giờ, nên **vùng nội dung giữ nền sáng**. Màu navy của website dùng cho:
- sidebar (chỗ đặt logo, giống thanh điều hướng trên website),
- hero của trang đăng nhập,
- các thẻ tối (`.panel-dark`), toast, nhãn trên ảnh camera.

## 3. Bảng màu (token trong `tailwind.config.js`)

| Token | Giá trị | Dùng cho |
|---|---|---|
| `brand-500` | `#48C6FD` | Nút chính, vạch nhấn, mục sidebar đang chọn, số đếm NEW, vùng đã lưu trên canvas, logo |
| `brand-600` / `brand-700` | `#006BB8` / `#005A99` | Liên kết, eyebrow, chữ cyan cỡ nhỏ trên nền sáng, viền focus |
| `brand-50` / `brand-100` | `#EBF8FF` / `#D4F1FF` | Nền nhạt khi hover, vùng đang sửa, bôi chọn chữ |
| `brand-200` / `brand-300` | `#A9E4FE` / `#6DD4FF` | Chữ cyan trên nền navy (mục sidebar đang chọn, LIVE) |
| `danger-*` | `#D4183D` (500) … | CRITICAL, CONFIRMED, vi phạm, lỗi, nút "Confirm violation", nút Delete, frame bị bỏ, chấm REC, toast "New alert" (nền `danger-600`; toast thường vẫn nền navy viền cyan) |
| `ink` (+ `raised`, `edge`, `field`) | `#0A1525` … | Sidebar, thẻ tối, toast, nhãn trên ảnh camera |
| `paper` | `#F2F5F9` | Nền trang |
| `surface` | `#FFFFFF` | Thanh trên cùng, thẻ (`.panel`), ô nhập |
| `subtle` / `muted` / `well` | `#F7F9FC` / `#EFF3F8` / `#E3E9F1` | Hover hàng bảng; đầu bảng và hộp ghi chú; rãnh Segmented và chip |
| `line` (+ `soft`, `muted`, `strong`) | `#E0E6EE` … | Viền thẻ, kẻ bảng, viền ô nhập |
| `graphite-*` | `#0A1525` → `#A0ABBB` | Chữ trên nền sáng, ngả xám xanh theo navy: 900 tiêu đề, 800 nội dung, 500 chữ phụ |
| `fog-*` | `#F4F7FB` → `#8392A7` | Chữ trên nền navy |
| `success-600` | `#1E9E57` | Camera đang chạy, công tắc bật, RESOLVED, AI Mode REAL |
| `warn-500` | `#F78F24` | HIGH, độ tin cậy AI trung bình |
| `info-*` | `#4F5FE0` … | NEW, vùng đã dịch theo camera, hình đang vẽ trên canvas. Chọn indigo để không lẫn với cyan |

Quy tắc:

- **Cyan không đặt chữ trắng lên trên, và không làm chữ cỡ nhỏ trên nền trắng.** Cyan trên trắng chỉ đạt 1.95:1.
  - Nút chính và số đếm NEW: nền cyan, chữ `text-ink` (9.4:1).
  - Chữ cyan trên nền sáng dùng `brand-600` (5.5:1) hoặc `brand-700`.
  - Vùng đã lưu trên canvas có nhãn chữ navy.
- **Cyan là thương hiệu, đỏ là nguy hiểm.** Khác bản Viettel (đỏ vừa là thương hiệu vừa là CRITICAL), giờ hai vai trò tách hẳn:
  - Mọi thứ mang nghĩa "nguy hiểm / sai / xoá" dùng `danger-*`, không dùng `brand-*`.
  - Ô KPI thường dùng chấm xám; chỉ "Critical today" có chấm và số màu đỏ (`<Kpi critical />`).
  - Biểu đồ "Incidents today" vẽ cột CRITICAL màu đỏ, phần còn lại màu xám (`bg-bars`).
- **Nút:** `PrimaryButton` cyan chữ navy, `DangerButton` đỏ `danger-600` chữ trắng, `OutlineButton` viền cyan chữ `brand-600`, `GhostButton` viền xám.
- **Mức độ (severity)** — `SEVERITY` trong `components/ui.tsx`: CRITICAL đỏ, HIGH cam, MEDIUM vàng, LOW xám xanh. Biểu đồ dùng đúng các màu `bar` này. Màu `hud` đậm hơn để chữ trắng đặt lên vẫn đọc được.
- **Trạng thái (status)** — `StatusPill`: NEW indigo, CONFIRMED đỏ, FALSE_POSITIVE xám, RESOLVED xanh lá.
- **AI Mode: DEMO** luôn là viên thuốc màu hổ phách ở thanh trên cùng, theo yêu cầu trong `docs/SPEC.md`.

## 4. Chữ

| Vai trò | Font | Ghi chú |
|---|---|---|
| Giao diện, nội dung, tiêu đề, số KPI | **Plus Jakarta Sans** (`font-sans`, `font-display`) | Font duy nhất của website. Tiêu đề chỉ khác ở độ đậm. |
| Giờ, mã camera/sự cố, số đo | **JetBrains Mono** (`font-mono`) | |

`font-display` vẫn được giữ làm tên vai trò "tiêu đề" trong code, nhưng trỏ cùng font với `font-sans`.

Plus Jakarta Sans có bộ chữ tiếng Việt, nên tên camera hay tên vùng do người dùng nhập in thẳng được.

Font được tải qua `next/font/google` và tự host khi build, nên lúc chạy trong nhà máy không cần Internet.

## 5. Thành phần dùng chung

- `components/ui.tsx`:
  - Hiển thị: `Kpi` (thẻ sáng/tối, biến thể `critical`), `SeverityTag`, `StatusPill`, `Snapshot` (ảnh từ API có token).
  - Điều khiển: `Switch` (tone `success` hoặc `brand`), `Segmented`.
  - Nút: `PrimaryButton`, `OutlineButton`, `GhostButton`, `DangerButton`.
  - `Drawer`: ngăn kéo trượt từ phải (Escape hoặc bấm ra ngoài để đóng), dùng cho "Camera settings".
  - Hoạ tiết: `Logo`, `Rule`, `Marker`, `LiveDot`, `RecDot`.
- `components/shell.tsx`:
  - Từ `md` trở lên: sidebar navy có logo, icon cho từng mục và số sự cố NEW; thanh trên cùng có AI Mode và đồng hồ giờ nhà máy.
  - Dưới `md`: thanh trên navy và thanh tab dưới, xem mục 6.
  - Breadcrumb và vùng nút hành động của trang.
  - Thanh trên cùng luôn cao 56px; chữ AI Mode bị cắt bớt thay vì xuống dòng.
  - `dense`: đầu trang gọn (tiêu đề 26px, bỏ câu "AI raises an alert…", ít khoảng trống) cho màn làm việc: chi tiết camera, Incidents. Các màn này dùng hết bề ngang, lề hai bên bằng nhau; các trang khác vẫn giới hạn 1680px.
  - `fill`: từ `md`, trang cao đúng một màn hình và phần tử con cuối chiếm phần còn lại. Incidents dùng để bảng cuộn trong khung của nó, bộ lọc và tên cột luôn hiện.
  - `subtitle`: dòng dưới tiêu đề, thay câu khẩu hiệu (chi tiết camera: trạng thái, mã, khu vực, số luật).
  - Mở luồng sự kiện (SSE) và bật toast khi có cảnh báo mới.
- `components/providers.tsx`: toast và ngăn kéo xem xét sự cố, gọi qua `useApp()` từ bất kỳ trang nào.
- `components/incident-drawer.tsx`: ngăn kéo xem xét. Chỉ hiện các bước mà backend cho phép (`REVIEW_TRANSITIONS`).
- `lib/live.ts`: kênh sự kiện trong trang (`useIncidentEvents`), để các trang tự làm mới khi có sự cố mới hoặc vừa được xem xét.
- `.panel-dark` và sidebar có sẵn vầng sáng cyan ở góc trên phải (`bg-glow`). Hero trang đăng nhập dùng `bg-hero`.
- `Rule` là viên thuốc tô gradient thương hiệu (`bg-brand-text`) trên một đường kẻ mảnh.
- **`Logo`**:
  - Biểu tượng chép path từ `madison-logo.svg` trên website; chữ "MADISON / TECHNOLOGIES" là chữ thật như trên website.
  - Kích thước theo cỡ chữ, ví dụ `className="text-[15px]"`.
  - Trên nền trắng truyền `light`, khi đó chữ "MADISON" chuyển sang navy vì gradient sẽ chìm vào nền.
  - `app/icon.svg` là biểu tượng cyan trên ô vuông navy.
  - **Cần bộ phận thương hiệu Madison xác nhận** trước khi đưa ra ngoài; khi có bộ logo chính thức, thay path trong `components/ui.tsx` và `app/icon.svg`.

## 6. Điện thoại (dưới `md`, 768px)

Người dùng điện thoại chủ yếu là quản lý an toàn đang ở xưởng: nhận cảnh báo, mở ra xem, quyết định. Layout ưu tiên việc đó.

- **Khung.** Thanh trên navy cao 56px gồm biểu tượng logo, "Safety Monitor", chip "AI Mode: …" và avatar mở menu tài khoản (tên, vai trò, Sign out). Năm mục chuyển xuống thanh tab cố định ở đáy, có số sự cố NEW. Đồng hồ nhà máy chỉ hiện trên màn rộng.
- **Đầu trang.** Chỉ giữ link quay lại và tiêu đề (26px). Eyebrow và câu "AI raises an alert…" bị ẩn vì thanh trên đã nói điều đó. Nút hành động trải hết chiều ngang.
- **Bảng thành thẻ.** Incidents và Rules hiển thị mỗi dòng thành một thẻ, với mức độ và trạng thái luôn thấy được; bảng chỉ dùng từ `md`.
- **Bộ lọc sự cố.** Chỉ để thanh trạng thái (New, Confirmed…); mức độ, camera, vùng, vi phạm và ngày nằm sau nút "Filters", nút này hiện số bộ lọc đang bật. Cả thanh dính ngay dưới thanh trên khi cuộn.
- **Thứ tự.** Overview đưa "Awaiting review" lên trước biểu đồ. Chi tiết camera xếp khung hình, rồi "People and vehicles", "Zones", "Recent alerts", đúng thứ tự trong DOM.
- **KPI** hai ô một hàng; ô tối đầu tiên trải hai cột.
- **Canvas vẽ vùng** vẽ nét, điểm góc và nhãn theo tỉ lệ hiển thị thật, nên nhãn vẫn cao ~13px trên điện thoại.
- **Toast** trải ngang ngay trên thanh tab. Thanh tab tự chừa khoảng `safe-area-inset-bottom` (viewport `cover` trong `app/layout.tsx`).

## 7. Màn rộng: hai màn làm việc nằm gọn trong một màn hình

- **Incidents.**
  - Một thanh lọc: trạng thái dạng tab; mức độ, camera, vùng, vi phạm và ngày dạng dropdown, rộng vừa giá trị đang chọn (`field-sizing: content`, có trên Chrome/Edge); "Clear" khi đang lọc.
  - Chọn camera thì danh sách vùng chỉ còn vùng của camera đó.
  - Bảng cuộn trong khung, tên cột dính trên cùng; thanh dưới bảng có tổng số và "Show more".
  - Mỗi sự cố một dòng; sự cố của hôm nay không ghi ngày.
- **Chi tiết camera.**
  - Khung hình co theo chiều cao màn hình: `max-h-[calc(100dvh-284px)]`, 284px là phần đầu trang, thanh công cụ và lề. Sửa đầu trang thì sửa số này.
  - Cột phải (People and vehicles, Zones, Recent alerts) cao đúng bằng khung hình và tự cuộn bên trong.
  - Số đo (AI FPS đo được / mục tiêu, inference, frames, dropped) nằm trên thanh công cụ của khung, cạnh công tắc overlay và nút toàn màn hình. Cảnh báo vùng bị tạm dừng nằm đè lên đầu khung hình.
  - Bật/tắt camera nằm ngay trên viên trạng thái dưới tiêu đề (chỉ admin thấy công tắc): "Camera on · Live" xanh, "Camera on · Offline" xám, "Camera off" cam để dễ thấy camera đang không giám sát.
  - Các cài đặt còn lại (AI FPS, nguồn RTSP/file, worker, nhiều view, upload MP4) nằm trong ngăn kéo "Camera settings", mở bằng nút Settings (chỉ admin).

## 8. Những gì cố ý chưa làm theo design

- **Vùng nội dung không chuyển sang nền tối** như website (xem mục 2).
- **"Undo decision"**: backend coi quyết định review là một chiều và lưu vết (`OperatorFeedback`), nên ngăn kéo không có nút hoàn tác.
- Lớp phủ khung người/vùng trên ảnh camera vẫn do ai-worker vẽ sẵn vào snapshot, không vẽ lại ở trình duyệt. Màu của lớp phủ này (`apps/ai-worker/app/drawing.py`) không theo thương hiệu.
- Ngôn ngữ giao diện vẫn là tiếng Anh.
