# Triển khai lên server Ubuntu

Cách chạy POC trên một server Ubuntu, trong thư mục `/opt/factory-safety`, sau nginx có HTTPS của Let's Encrypt.

```text
Internet ──443──> nginx trên server (HTTPS, HTTP/2)
                    ├── /api/*  → 127.0.0.1:8000  backend
                    └── /       → 127.0.0.1:3000  frontend (dashboard)

Docker Compose: backend, frontend, ai-worker, postgres, redis, minio
```

**Postgres, Redis và MinIO không cài riêng lên server.** Chúng nằm trong `docker-compose.yml`. Lệnh `docker compose up` tự tải image (Postgres 16, Redis 7, MinIO) và chạy chúng, dữ liệu nằm trong volume Docker, giống hệt trên máy dev. Postgres và Redis không mở cổng ra ngoài. MinIO, backend, frontend và worker chỉ mở trên `127.0.0.1` (`docker-compose.prod.yml`), nên từ Internet chỉ vào được qua nginx.

Trong tài liệu này, thay:
- `safety.example.com` bằng domain thật,
- `ubuntu` bằng user SSH,
- `SERVER` bằng IP của server.

## 0. Cần chuẩn bị

- Server Ubuntu 22.04 hoặc 24.04, user có quyền `sudo`. Cho 2–4 camera chạy AI bằng CPU: khoảng 4 vCPU, 8 GB RAM, 30 GB ổ trống.
- Domain có bản ghi A trỏ về IP server (thêm AAAA nếu server có IPv6). Kiểm tra từ máy bất kỳ: `dig +short safety.example.com`.
- Code đã push lên GitHub, branch `madison-factory-safety`.
- Thư mục `models/` trên máy dev có các file `.onnx`. Chúng không nằm trong git.

## 1. Cài Docker, nginx, certbot

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y nginx certbot python3-certbot-nginx git
```

Thoát SSH rồi đăng nhập lại để quyền nhóm `docker` có hiệu lực. Kiểm tra:

```bash
docker compose version   # cần 2.24.4 trở lên
```

Firewall: chỉ mở SSH, 80 và 443.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 2. Tạo thư mục và lấy code

```bash
sudo mkdir -p /opt/factory-safety
sudo chown $USER:$USER /opt/factory-safety
git clone -b madison-factory-safety https://github.com/thap-nv/SC-AI.git /opt/factory-safety
cd /opt/factory-safety
```

Repo private thì dùng deploy key hoặc personal access token khi clone.

## 3. Chép model lên server

Trên máy dev, trong thư mục dự án (PowerShell hoặc Git Bash):

```bash
scp -r models ubuntu@SERVER:/opt/factory-safety/
```

Kiểm tra trên server: `ls -lh /opt/factory-safety/models/*.onnx`.

## 4. Tạo `.env`

```bash
cd /opt/factory-safety
cp .env.example .env
openssl rand -hex 32   # chạy 4 lần: JWT_SECRET, INTERNAL_API_TOKEN, POSTGRES_PASSWORD, MINIO_SECRET_KEY
nano .env
```

Sửa hoặc thêm các dòng sau:

```env
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml

NEXT_PUBLIC_API_URL=https://safety.example.com
CORS_ORIGINS=https://safety.example.com

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

Lưu ý:

- `COMPOSE_FILE` làm mọi lệnh `docker compose` trong thư mục này tự dùng thêm `docker-compose.prod.yml`, không cần gõ `-f`.
- `NEXT_PUBLIC_API_URL` được build cứng vào frontend. Đổi domain sau này thì chạy lại `docker compose up -d --build frontend`.
- **Đặt mật khẩu trước lần chạy đầu tiên.** Mật khẩu Postgres và MinIO chỉ được dùng khi volume được tạo. Ba tài khoản `admin`, `safety`, `viewer` chỉ được tạo một lần với các mật khẩu `DEMO_*`; sửa `.env` sau đó không đổi được mật khẩu.
- Dùng chuỗi hex cho mật khẩu Postgres: nó nằm trong URL kết nối database, nên ký tự như `@ : /` sẽ làm hỏng URL.

## 5. Chạy stack

```bash
docker compose up -d --build
docker compose ps
```

Lần đầu mất vài phút để tải image và build. Đợi đến khi `postgres`, `redis`, `minio`, `backend`, `ai-worker` đều `healthy` và `frontend` `running`. Kiểm tra:

```bash
curl -s http://127.0.0.1:8000/ready                                   # {"status": "ok", "database": "up", "redis": "up"}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/login  # 200
docker compose exec postgres psql -U safety -d safety -c '\dt'        # các bảng đã tạo
docker compose exec minio mc ready local                              # MinIO sẵn sàng
```

Container tự khởi động lại khi server reboot (`restart: unless-stopped`).

## 6. Cấu hình nginx cho domain

```bash
sudo cp infrastructure/nginx/factory-safety.conf /etc/nginx/sites-available/factory-safety
sudo sed -i 's/safety\.example\.com/<domain thật>/' /etc/nginx/sites-available/factory-safety
sudo ln -s /etc/nginx/sites-available/factory-safety /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

File cấu hình đã có sẵn:

- `/api/*` vào backend, phần còn lại vào dashboard;
- luồng sự kiện SSE không bị đệm;
- upload video tới 200 MB;
- chặn `/api/internal/*`, phần API chỉ dành cho worker.

Mở `http://safety.example.com` sẽ thấy trang đăng nhập. Chưa đăng nhập được cho đến bước 7, vì dashboard gọi API qua `https://`.

## 7. HTTPS với Let's Encrypt

```bash
sudo certbot --nginx -d safety.example.com --redirect -m you@example.com --agree-tos --no-eff-email
```

certbot lấy chứng chỉ, thêm cổng 443 vào file `factory-safety`, và chuyển hướng HTTP sang HTTPS.

Bật HTTP/2. Không có HTTP/2, trình duyệt chỉ mở 6 kết nối tới một domain, và mỗi tab dashboard giữ một kết nối SSE; mở khoảng 6 tab là API treo.

```bash
sudo sed -i -e 's/listen 443 ssl;/listen 443 ssl http2;/' \
            -e 's/listen \[::\]:443 ssl ipv6only=on;/listen [::]:443 ssl http2 ipv6only=on;/' \
            /etc/nginx/sites-available/factory-safety
sudo nginx -t && sudo systemctl reload nginx
curl -sI --http2 https://safety.example.com/login | head -1   # HTTP/2 200
```

Lệnh trên dành cho nginx của Ubuntu 22.04 (1.18) và 24.04 (1.24). Với nginx 1.25.1 trở lên, dùng dòng `http2 on;` trong block server thay cho chữ `http2` sau `listen`.

Chứng chỉ tự gia hạn qua systemd timer của certbot. Thử trước một lần:

```bash
sudo certbot renew --dry-run
```

## 8. Dùng lần đầu

1. Mở `https://safety.example.com`, đăng nhập `admin` với mật khẩu đã đặt.
2. Camera trong dữ liệu khởi tạo chưa có nguồn hình. Vào từng camera:
   - bấm **Upload MP4** (tối đa 200 MB; video mẫu ở `sample-data/videos` trên máy dev không nằm trong git), hoặc
   - nhập địa chỉ RTSP ở **Camera settings**. Server phải kết nối được tới camera.
3. Bật **Enable camera**.

## Vận hành

Cập nhật code:

```bash
cd /opt/factory-safety
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

MinIO console: mở SSH tunnel `ssh -L 9101:127.0.0.1:9101 ubuntu@SERVER`, rồi vào `http://localhost:9101` trên máy của bạn.

Dừng stack, giữ dữ liệu: `docker compose down`. Thêm `-v` sẽ **xoá toàn bộ** database và ảnh.

## Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| 502 Bad Gateway | Container chưa chạy xong hoặc bị lỗi: `docker compose ps`, `docker compose logs backend frontend`. |
| Trang mở được nhưng đăng nhập báo lỗi mạng | `NEXT_PUBLIC_API_URL` sai, hoặc chưa có HTTPS. Sửa `.env` rồi `docker compose up -d --build frontend`. |
| Upload video báo 413 | File quá 200 MB, hoặc file nginx đang dùng không phải `factory-safety.conf`. |
| certbot báo lỗi challenge | DNS chưa trỏ về server, hoặc cổng 80 bị chặn ở firewall hay ở nhà cung cấp cloud. |
| Dashboard không cập nhật sự cố mới | Kiểm tra `location = /api/events/stream` còn trong file nginx và HTTP/2 đã bật. |
