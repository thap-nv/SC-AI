# Triển khai lên server Ubuntu

Cách chạy POC trên một server Ubuntu, trong thư mục `~/factory-safety` của user SSH (ví dụ `/home/customer/factory-safety`), sau nginx có HTTPS của Let's Encrypt.

```text
Internet ──443──> nginx trên server (HTTPS, HTTP/2)
                    ├── /api/*  → 127.0.0.1:8000  backend
                    └── /       → 127.0.0.1:3000  frontend (dashboard)

Docker Compose: backend, frontend, ai-worker, postgres, redis, minio
```

**Postgres, Redis và MinIO không cài riêng lên server.** Chúng nằm trong `docker-compose.yml`. Lệnh `docker compose up` tự tải image (Postgres 16, Redis 7, MinIO) và chạy chúng, dữ liệu nằm trong volume Docker, giống hệt trên máy dev. Postgres và Redis không mở cổng ra ngoài. MinIO, backend, frontend và worker chỉ mở trên `127.0.0.1` (`docker-compose.prod.yml`), nên từ Internet chỉ vào được qua nginx.

Tài liệu này dùng domain `safety-monitor.madlab.tech`. Thay:
- `ubuntu` bằng user SSH,
- `SERVER` bằng IP của server.

Server có thể đang chạy các site khác. Các bước dưới đây không xoá hay sửa cấu hình của site nào khác. Stack này có tên Compose là `factory-safety` (theo tên thư mục), nên container, volume và network của nó không trùng với các project Docker khác.

## 0. Cần chuẩn bị

- Server Ubuntu 22.04 hoặc 24.04, user có quyền `sudo`. Cho 2–4 camera chạy AI bằng CPU: khoảng 4 vCPU, 8 GB RAM, 30 GB ổ trống.
- Domain có bản ghi A trỏ về IP server (thêm AAAA nếu server có IPv6). Kiểm tra từ máy bất kỳ: `dig +short safety-monitor.madlab.tech`.
- Code đã push lên GitHub, branch `madison-factory-safety`.
- Thư mục `models/` trên máy dev có các file `.onnx`. Chúng không nằm trong git.

## 1. Cài Docker, nginx, certbot

Xem server đã có gì:

```bash
docker --version; docker compose version; nginx -v; certbot --version
```

Chỉ cài những gì còn thiếu. Không chạy `apt upgrade` trên server dùng chung, vì nó có thể khởi động lại dịch vụ của các site khác.

```bash
sudo apt update
curl -fsSL https://get.docker.com | sudo sh            # chỉ khi chưa có Docker
sudo usermod -aG docker $USER                          # chỉ khi user chưa thuộc nhóm docker
sudo apt install -y nginx certbot python3-certbot-nginx git
```

Thoát SSH rồi đăng nhập lại nếu vừa thêm nhóm `docker`. `docker compose version` phải từ 2.24.4 trở lên.

Firewall: xem trạng thái trước.

```bash
sudo ufw status
```

- Nếu `active`: chỉ cần mở 80 và 443 (có thể đã mở sẵn cho các site khác): `sudo ufw allow 'Nginx Full'`.
- Nếu `inactive`: **đừng tự bật ufw**. Bật lên mà chưa mở cổng của các dịch vụ khác thì chúng bị chặn. Stack này không cần ufw: mọi cổng Docker của nó chỉ mở trên `127.0.0.1`.

## 2. Tạo thư mục và lấy code

```bash
mkdir -p ~/factory-safety
cd ~/factory-safety
ls -A   # thư mục phải trống thì mới clone vào được
git clone -b madison-factory-safety https://github.com/thap-nv/SC-AI.git .
```

Dấu `.` ở cuối lệnh clone đưa code vào ngay thư mục hiện tại, không tạo thêm thư mục `SC-AI` bên trong.

Repo private thì dùng deploy key hoặc personal access token khi clone.

## 3. Chép model lên server

Trên máy dev, trong thư mục dự án (PowerShell hoặc Git Bash):

```bash
scp -r models ubuntu@SERVER:factory-safety/
```

Đường dẫn bên phải không có `/` ở đầu nên tính từ thư mục home của user trên server. Kiểm tra trên server: `ls -lh ~/factory-safety/models/*.onnx`.

## 4. Tạo `.env`

```bash
cd ~/factory-safety
cp .env.example .env
openssl rand -hex 32   # chạy 4 lần: JWT_SECRET, INTERNAL_API_TOKEN, POSTGRES_PASSWORD, MINIO_SECRET_KEY
nano .env
```

Sửa **đúng các dòng đã có** trong file, chỉ thêm dòng nào chưa có (như `COMPOSE_FILE`). Đừng dán cả khối mới mà vẫn để dòng cũ: nếu một biến xuất hiện hai lần, Docker Compose lấy dòng **cuối**. Khi đó, ví dụ `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` có sẵn trong `.env.example` sẽ thắng, và trang đăng nhập báo `Failed to fetch`.

```env
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml

NEXT_PUBLIC_API_URL=https://safety-monitor.madlab.tech
CORS_ORIGINS=https://safety-monitor.madlab.tech

POSTGRES_PASSWORD=<hex>
MINIO_ACCESS_KEY=factorysafety
MINIO_SECRET_KEY=<hex>
JWT_SECRET=<hex>
INTERNAL_API_TOKEN=<hex>

DEMO_ADMIN_PASSWORD=<mật khẩu mạnh>
DEMO_SAFETY_PASSWORD=<mật khẩu mạnh>
DEMO_VIEWER_PASSWORD=<mật khẩu mạnh>

AI_MODE=REAL
```

Kiểm tra Docker Compose sẽ dùng giá trị nào:

```bash
grep -cE '^NEXT_PUBLIC_API_URL=' .env                         # phải ra 1
docker compose config | grep -E 'NEXT_PUBLIC_API_URL|CORS_ORIGINS|AI_MODE'
```

Phải thấy `NEXT_PUBLIC_API_URL: https://safety-monitor.madlab.tech`, `CORS_ORIGINS: https://safety-monitor.madlab.tech` và `AI_MODE: REAL`.

Lưu ý:

- `COMPOSE_FILE` làm mọi lệnh `docker compose` trong thư mục này tự dùng thêm `docker-compose.prod.yml`, không cần gõ `-f`.
- `NEXT_PUBLIC_API_URL` được build cứng vào frontend. Đổi domain sau này thì chạy lại `docker compose up -d --build frontend`.
- **Đặt mật khẩu trước lần chạy đầu tiên.** Mật khẩu Postgres và MinIO chỉ được dùng khi volume được tạo. Ba tài khoản `admin`, `safety`, `viewer` chỉ được tạo một lần với các mật khẩu `DEMO_*`; sửa `.env` sau đó không đổi được mật khẩu.
- Dùng chuỗi hex cho mật khẩu Postgres: nó nằm trong URL kết nối database, nên ký tự như `@ : /` sẽ làm hỏng URL.

**Kiểm tra cổng.** Stack mở 5 cổng trên `127.0.0.1`: 3000 (dashboard), 8000 (API), 8081 (worker), 9100 và 9101 (MinIO). Trên server dùng chung, các app khác có thể đã chiếm một trong số đó:

```bash
sudo ss -ltnp | grep -E ':(3000|8000|8081|9100|9101)\b'
```

Không ra dòng nào là các cổng còn trống. Nếu có cổng đã bị chiếm, chọn cổng khác trong `.env`:

```env
FRONTEND_PORT=3100      # thay 3000
BACKEND_PORT=8100       # thay 8000
WORKER_PORT=8181        # thay 8081
MINIO_API_PORT=9200     # thay 9100
MINIO_CONSOLE_PORT=9201 # thay 9101
```

Chỉ cần thêm những dòng cho cổng bị trùng. Nếu đổi `FRONTEND_PORT` hoặc `BACKEND_PORT`, nhớ sửa theo trong file nginx ở bước 6.

## 5. Chạy stack

```bash
docker compose up -d --build
docker compose ps
```

Lần đầu mất vài phút để tải image và build. Đợi đến khi `postgres`, `redis`, `minio`, `backend`, `ai-worker` đều `healthy` và `frontend` `running`. Kiểm tra:

```bash
curl -s http://127.0.0.1:8000/ready                                   # {"status": "ok", "database": "up", "redis": "up"}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/login  # 200 (đổi 8000, 3000 nếu đã đổi cổng)
docker compose exec postgres psql -U safety -d safety -c '\dt'        # các bảng đã tạo
docker compose exec minio mc ready local                              # MinIO sẵn sàng
```

Container tự khởi động lại khi server reboot (`restart: unless-stopped`).

## 6. Cấu hình nginx cho domain

```bash
sudo cp infrastructure/nginx/factory-safety.conf /etc/nginx/sites-available/factory-safety
sudo sed -i 's/safety\.example\.com/safety-monitor.madlab.tech/' /etc/nginx/sites-available/factory-safety
sudo ln -s /etc/nginx/sites-available/factory-safety /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Kiểm tra ngay trên server, chưa cần DNS:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: safety-monitor.madlab.tech' http://127.0.0.1/login   # 200
```

### Chỉ khi đã đổi cổng ở bước 4

**Bỏ qua mục này nếu `.env` không có `FRONTEND_PORT` hay `BACKEND_PORT`.** Chạy nó khi không đổi cổng thì nginx gửi request tới cổng không có gì, và trang báo 502 Bad Gateway.

Nếu có đổi, thay `<FRONTEND_PORT>` và `<BACKEND_PORT>` bằng đúng số trong `.env`. Nếu dán nguyên văn, `nginx -t` sẽ báo lỗi và không reload.

```bash
sudo sed -i -e 's/127\.0\.0\.1:3000;/127.0.0.1:<FRONTEND_PORT>;/' -e 's/127\.0\.0\.1:8000;/127.0.0.1:<BACKEND_PORT>;/' /etc/nginx/sites-available/factory-safety
grep -n 'server 127' /etc/nginx/sites-available/factory-safety
sudo nginx -t && sudo systemctl reload nginx
```

Giữ nguyên các site khác, kể cả `default`. nginx chọn site theo domain (`server_name`), nên site này không ảnh hưởng tới chúng. `nginx -t` kiểm tra toàn bộ cấu hình trước khi reload; nếu báo lỗi thì nginx vẫn chạy cấu hình cũ, các site khác không bị gián đoạn.

File cấu hình đã có sẵn:

- `/api/*` vào backend, phần còn lại vào dashboard;
- luồng sự kiện SSE không bị đệm;
- upload video tới 200 MB;
- chặn `/api/internal/*`, phần API chỉ dành cho worker.

Mở `http://safety-monitor.madlab.tech` sẽ thấy trang đăng nhập. Chưa đăng nhập được cho đến bước 7, vì dashboard gọi API qua `https://`.

## 7. HTTPS với Let's Encrypt

```bash
sudo certbot --nginx -d safety-monitor.madlab.tech --redirect -m you@example.com --agree-tos --no-eff-email
```

certbot lấy chứng chỉ cho đúng domain này, thêm cổng 443 vào file `factory-safety`, và chuyển hướng HTTP sang HTTPS. Chứng chỉ và cấu hình của các site khác không bị đụng tới.

Bật HTTP/2. Không có HTTP/2, trình duyệt chỉ mở 6 kết nối tới một domain, và mỗi tab dashboard giữ một kết nối SSE; mở khoảng 6 tab là API treo.

```bash
sudo sed -i -E 's/listen (\[::\]:)?443 ssl( ipv6only=on)?;/listen \1443 ssl http2\2;/' /etc/nginx/sites-available/factory-safety
grep -n 'listen' /etc/nginx/sites-available/factory-safety   # các dòng 443 phải có http2
sudo nginx -t && sudo systemctl reload nginx
curl -sI --http2 https://safety-monitor.madlab.tech/login | head -1   # HTTP/2 200
```

Lệnh trên dành cho nginx của Ubuntu 22.04 (1.18) và 24.04 (1.24). Với nginx 1.25.1 trở lên, dùng dòng `http2 on;` trong block server thay cho chữ `http2` sau `listen`.

Trên nginx 1.18 và 1.24, HTTP/2 bật theo cổng chứ không theo site, nên mọi site HTTPS khác trên server cũng sẽ dùng HTTP/2. Trình duyệt và client hiện nay đều hỗ trợ, và client nào không hỗ trợ thì tự quay về HTTP/1.1.

Chứng chỉ tự gia hạn qua systemd timer của certbot. Thử trước một lần:

```bash
sudo certbot renew --dry-run
```

## 8. Dùng lần đầu

1. Mở `https://safety-monitor.madlab.tech`, đăng nhập `admin` với mật khẩu đã đặt.
2. Camera trong dữ liệu khởi tạo chưa có nguồn hình. Vào từng camera:
   - bấm **Upload MP4** (tối đa 200 MB; video mẫu ở `sample-data/videos` trên máy dev không nằm trong git), hoặc
   - nhập địa chỉ RTSP ở **Camera settings**. Server phải kết nối được tới camera.
3. Bật **Enable camera**.

## Vận hành

Cập nhật code:

```bash
cd ~/factory-safety
git pull
docker compose up -d --build
```

Xem log:

```bash
docker compose logs -f backend ai-worker
```

Sao lưu database (nên đặt cron chạy hằng ngày):

```bash
docker compose exec -T postgres pg_dump -U safety safety | gzip > ~/factory-safety-$(date +%F).sql.gz
```

Ảnh bằng chứng và video upload nằm trong volume `factory-safety_miniodata`.

MinIO console: mở SSH tunnel `ssh -L 9101:127.0.0.1:9101 ubuntu@SERVER` (thay vế sau bằng `MINIO_CONSOLE_PORT` nếu đã đổi), rồi vào `http://localhost:9101` trên máy của bạn.

Dừng stack, giữ dữ liệu: `docker compose down`. Thêm `-v` sẽ **xoá toàn bộ** database và ảnh.

## Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| 502 Bad Gateway | Container chưa chạy xong hoặc bị lỗi: `docker compose ps`, `docker compose logs backend frontend`. |
| Đăng nhập báo `Failed to fetch`, console trình duyệt ghi `127.0.0.1:8000` | Frontend được build với `NEXT_PUBLIC_API_URL` mặc định: `.env` thiếu dòng này hoặc có hai dòng. Sửa `.env` (bước 4) rồi `docker compose up -d --build`. |
| Đăng nhập báo `Failed to fetch`, console ghi `https://<domain>` | Chưa có HTTPS: làm bước 7. |
| Upload video báo 413 | File quá 200 MB, hoặc file nginx đang dùng không phải `factory-safety.conf`. |
| certbot báo lỗi challenge | DNS chưa trỏ về server, hoặc cổng 80 bị chặn ở firewall hay ở nhà cung cấp cloud. |
| Dashboard không cập nhật sự cố mới | Kiểm tra `location = /api/events/stream` còn trong file nginx và HTTP/2 đã bật. |
