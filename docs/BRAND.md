# Nhận diện thương hiệu Viettel IDC trong dashboard

Tài liệu này ghi lại cách giao diện `apps/frontend` áp dụng nhận diện của Viettel IDC, để ai sửa UI sau cũng giữ được cùng một ngôn ngữ.

Nguồn: website https://viettelidc.com.vn, khảo sát tháng 10/2026. Gồm:
- `variable.css`, `styles.css`, `custom.css`: màu, bo góc, kiểu nút.
- `logo-IDC.svg`: logo.
- `Favicon-IDC.png`: favicon.

## 1. Thương hiệu nói gì

- **Màu.** Đỏ Viettel `#EE0033` là màu duy nhất mang thương hiệu. Phần còn lại là trắng, xám nhạt và xám than.
- **Thị giác.** Gọn, phẳng, nhiều khoảng trắng.
  - Nút chính nền đỏ, chữ trắng, bo 8px.
  - Thẻ bo 12px, viền xám mảnh.
  - Thanh chỉ báo slide đang chọn là một viên thuốc đỏ dài; dashboard dùng hình này cho `Rule` và vạch đánh dấu mục đang chọn ở sidebar.
- **Logo.** Chữ "viettel" màu đỏ, chữ "IDC" màu tối. Trên nền đỏ thì cả logo in một màu trắng.

## 2. Bảng màu (token trong `tailwind.config.js`)

| Token | Giá trị | Dùng cho |
|---|---|---|
| `brand-500` | `#EE0033` | Nút chính, vạch nhấn, mục sidebar đang chọn, số đếm NEW, vùng đã lưu trên canvas, CRITICAL |
| `brand-600` / `brand-700` | `#D1002D` / `#AD0025` | Liên kết, eyebrow, chữ đỏ cỡ nhỏ trên nền sáng; `brand-700` là nút "Confirm violation" |
| `brand-50` / `brand-100` | `#FFF0F3` / `#FFDDE4` | Nền mục sidebar đang chọn, nền thẻ CRITICAL, vòng focus ô nhập |
| `brand-200` / `brand-300` | `#FFB8C6` / `#FF7A93` | Chữ đỏ trên nền than chì |
| `ink` (+ `raised`, `edge`, `field`) | `#23262A` … | Thẻ tối (KPI đầu hàng, People in view, New rule, Frame pipeline), toast, nhãn trên ảnh camera |
| `paper` | `#F4F5F7` | Nền trang |
| `surface` | `#FFFFFF` | Sidebar, thanh trên cùng, thẻ (`.panel`), ô nhập |
| `subtle` / `muted` / `well` | `#F8F9FA` / `#F2F3F5` / `#E9EBEE` | Hover hàng bảng; đầu bảng và hộp ghi chú; rãnh Segmented và chip |
| `line` (+ `soft`, `muted`, `strong`) | `#E1E1E1` … | Viền thẻ, kẻ bảng, viền ô nhập |
| `graphite-*` | `#252525` → `#A5A9AE` | Chữ trên nền sáng: 900 tiêu đề (`--title`), 800 nội dung (`--content`), 500 chữ phụ |
| `fog-*` | `#F7F7F8` → `#8D9298` | Chữ trên nền than chì |
| `success-600` | `#1E9E57` | Camera đang chạy, công tắc bật, RESOLVED, AI Mode REAL |
| `warn-500` | `#F78F24` | HIGH, độ tin cậy AI trung bình (màu cam trên site) |
| `info-*` | `#4199E4` … | NEW, vùng đã dịch theo camera (`--primary` trên site) |

Quy tắc:

- **Màu đỏ vừa là thương hiệu vừa là CRITICAL.** Vì vậy:
  - Ô KPI thường dùng chấm xám; chỉ "Critical today" có chấm và số màu đỏ (`<Kpi critical />`).
  - Biểu đồ "Incidents today" vẽ cột CRITICAL màu đỏ, phần còn lại màu xám (`bg-bars`).
- **Không dùng `brand-500` cho chữ cỡ nhỏ trên nền trắng** (tương phản 4.5:1, sát ngưỡng); dùng `brand-600` hoặc `brand-700`.
- **Nút:** `PrimaryButton` đỏ `brand-500`, `DangerButton` đỏ đậm `brand-700`, nên hai nút vẫn phân biệt được khi đứng cạnh nhau ở trang chi tiết sự cố. `OutlineButton` viền đỏ, `GhostButton` viền xám.
- **Mức độ (severity)** — `SEVERITY` trong `components/ui.tsx`: CRITICAL đỏ, HIGH cam, MEDIUM vàng, LOW xám xanh. Biểu đồ dùng đúng các màu `bar` này. Màu `hud` đậm hơn để chữ trắng đặt lên vẫn đọc được.
- **Trạng thái (status)** — `StatusPill`: NEW xanh dương, CONFIRMED đỏ, FALSE_POSITIVE xám, RESOLVED xanh lá.
- **AI Mode: DEMO** luôn là viên thuốc màu hổ phách ở thanh trên cùng, theo yêu cầu trong `docs/SPEC.md`.

## 3. Chữ

| Vai trò | Font | Ghi chú |
|---|---|---|
| Giao diện, nội dung | **Sarabun** (`font-sans`) | Font nội dung của website. |
| Tiêu đề trang, số KPI, chữ thương hiệu | **Be Vietnam Pro** (`font-display`) | Thay cho **FS PF BeauSans Pro**, font thương mại website dùng cho tiêu đề. |
| Giờ, mã camera/sự cố, số đo | **JetBrains Mono** (`font-mono`) | |

Cả Sarabun và Be Vietnam Pro đều đủ dấu tiếng Việt, nên tên camera hay tên vùng do người dùng nhập in thẳng bằng `font-display` được.

Ba font được tải qua `next/font/google` và tự host khi build, nên lúc chạy trong nhà máy không cần Internet.

## 4. Thành phần dùng chung

- `components/ui.tsx`:
  - Hiển thị: `Kpi` (thẻ sáng/tối, biến thể `critical`), `SeverityTag`, `StatusPill`, `Snapshot` (ảnh từ API có token).
  - Điều khiển: `Switch` (tone `success` hoặc `brand`), `Segmented`.
  - Nút: `PrimaryButton`, `OutlineButton`, `GhostButton`, `DangerButton`.
  - Hoạ tiết: `Logo`, `Rule`, `Marker`, `LiveDot`, `RecDot`.
- `components/shell.tsx`:
  - Sidebar trắng có logo, icon cho từng mục và số sự cố NEW.
  - Thanh trên cùng có AI Mode và đồng hồ giờ nhà máy.
  - Breadcrumb và vùng nút hành động của trang.
  - Mở luồng sự kiện (SSE) và bật toast khi có cảnh báo mới.
- `components/providers.tsx`: toast và ngăn kéo xem xét sự cố, gọi qua `useApp()` từ bất kỳ trang nào.
- `components/incident-drawer.tsx`: ngăn kéo xem xét. Chỉ hiện các bước mà backend cho phép (`REVIEW_TRANSITIONS`).
- `lib/live.ts`: kênh sự kiện trong trang (`useIncidentEvents`), để các trang tự làm mới khi có sự cố mới hoặc vừa được xem xét.
- `.panel-dark` có sẵn vệt sáng đỏ ở góc trên phải (`bg-glow`), giống các banner tối trên site.
- **`Logo`** chép path từ `logo-IDC.svg` trên website. `app/icon.svg` dùng chữ "v" của logo đó. **Cần phòng thương hiệu Viettel IDC xác nhận** trước khi đưa ra ngoài; khi có file logo chính thức, thay path trong `components/ui.tsx` và `app/icon.svg`.

## 5. Những gì cố ý chưa làm theo design

- **"Undo decision"**: backend coi quyết định review là một chiều và lưu vết (`OperatorFeedback`), nên ngăn kéo không có nút hoàn tác.
- Lớp phủ khung người/vùng trên ảnh camera vẫn do ai-worker vẽ sẵn vào snapshot, không vẽ lại ở trình duyệt. Màu của lớp phủ này (`apps/ai-worker/app/drawing.py`) không theo thương hiệu.
- Ngôn ngữ giao diện vẫn là tiếng Anh.
