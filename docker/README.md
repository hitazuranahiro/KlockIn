# KlockIN deployment

## Development

```sh
docker compose up --build
```

Open [localhost:8000](http://127.0.0.1:8000). Use **Initialize database** on first launch. The development stack uses PostgreSQL, Redis, a Django web process, and a single scheduler. `KLOCKIN_PORT` changes the local port. Set `KLOCKIN_BIND_ADDRESS`, `KLOCKIN_DEV_HOSTS`, and `KLOCKIN_DEV_ORIGINS` together when using a development server reachable from an emulator or a LAN device.

## Production

Copy `../.env.dist` to `../.env` and configure the HTTPS domain, allowed host, CSRF origin, database, Redis, and initialization credentials. Mount the certificate chain and key as `fullchain.pem` and `privkey.pem` under `KLOCKIN_TLS_DIR`.

From the repository root:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Nginx exposes HTTP and HTTPS, redirects HTTP to HTTPS, and proxies to Django. Only one scheduler should run against a database. The web container runs migrations before it starts and serves `klockin.wsgi:application`. The deployment settings module is `klockin.settings`. Check liveness at `/health/` and confirm database, Redis, and scheduler readiness at `/ready/`.

Back up the PostgreSQL, media, and private attendance volumes together. Keep the private attendance volume outside any public Nginx location. The system serves selfies through a signed-in reviewer view scoped to the employee’s company.

The optional Docker Publish workflow runs on manual dispatch. Set the repository variable `KLOCKIN_DOCKERHUB_IMAGE` to the Tomeku-owned image and configure its registry credentials before publishing.

See the [KlockIN setup guide](../README.md) and [source notices](../docs/klockin-source-notices.md).
