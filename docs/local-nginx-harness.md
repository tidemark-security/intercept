# Local nginx harness

The development Compose stack includes an nginx harness that presents all
browser-required services on one origin:

- `/` proxies the Vite frontend and its hot-module-reload WebSocket.
- `/api/` proxies FastAPI and the realtime WebSocket at `/api/v1/ws`.
- `/storage/` proxies signed attachment uploads and downloads to MinIO.

PostgreSQL remains bound to loopback on port 5432 for host-run migrations and
tests. Backend, frontend, MinIO, Langflow, and worker ports are only exposed to
the Compose network.

## Local use

```bash
cd dev
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8080>. To use a different loopback port, set
`INTERCEPT_PORT` in `dev/.env` before starting the stack.

## Cloudflare Tunnel

Set the public HTTPS origin and secure-cookie flag in `dev/.env`:

```dotenv
INTERCEPT_PUBLIC_ORIGIN=https://intercept.example.com
SESSION_COOKIE_SECURE=true
```

Restart the backend after changing the origin:

```bash
docker compose up -d --force-recreate backend nginx
```

Configure the tunnel's single public hostname to use this origin service:

```text
http://127.0.0.1:8080
```

Only the harness port is needed by the tunnel. Do not publish PostgreSQL,
MinIO, Langflow, the worker, or the backend API separately.

The harness rewrites MinIO presigned URLs to relative `/storage/` URLs. Nginx
then restores the signed `Host` header and strips the prefix before forwarding
the request, so attachment upload, preview, and download remain same-origin.
