# Docker

The Compose file lives at the repository root so this command works from a fresh clone:

```text
docker compose up -d --build
```

`docker-compose.gpu.yml` is an optional overlay for a Linux host with the NVIDIA Container Toolkit. CPU mode does not use it.

`docker-compose.prod.yml` is the server overlay: it publishes every port on 127.0.0.1 only, for nginx on the host (`infrastructure/nginx/factory-safety.conf`). Steps in `docs/DEPLOY.md`.
