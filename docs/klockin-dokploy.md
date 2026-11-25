# Deploy KlockIN on Dokploy

In the target Dokploy environment, create a **Docker Compose** service, select the GitHub repository and release branch, and set **Compose Path** to `./docker-compose.dokploy.yml`. Enable **Isolated Deployments**. This stack runs Django, one background scheduler, PostgreSQL, and Redis. Dokploy handles HTTPS through Traefik. The database and Redis are reachable only inside the deployment network.

## Environment

Add real values in the service's **Environment** tab. Use the public hostname without a scheme in `ALLOWED_HOSTS` and its HTTPS origin in `CSRF_TRUSTED_ORIGINS`. If you configure several hosts, put the primary hostname first so container health checks send a valid Host header.

```dotenv
ALLOWED_HOSTS=klockin.example.com
CSRF_TRUSTED_ORIGINS=https://klockin.example.com
SECRET_KEY=<unique-random-secret>
DB_INIT_PASSWORD=<unique-setup-password>
POSTGRES_PASSWORD=<unique-random-hex-password>
REDIS_PASSWORD=<unique-random-hex-password>
KLOCKIN_EVIDENCE_KEYS=<fernet-key>
KLOCKIN_EVIDENCE_BACKUP_KEY=<different-fernet-key>
KLOCKIN_UPLOAD_STORAGE=local
```

Use independently generated hexadecimal values for the PostgreSQL and Redis passwords because Compose interpolates them into connection URLs. Generate each Fernet key independently with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Keep these values out of Git and retain the evidence and backup keys for recovery.

The deployment uses persistent named volumes for the database, Redis, ordinary media, and private selfies. To use a private R2 bucket for both upload types, follow the [upload storage guide](klockin-upload-storage.md) and set its credentials in Dokploy.

## HTTPS and verification

1. Point DNS for the app hostname at the Dokploy server. In **Domains**, add the hostname, select service `web`, set the container port to `8000`, retain path `/`, and enable HTTPS.
2. Deploy. On the first boot, the web service applies database migrations and collects static assets before the scheduler starts.
3. Open `https://<public-host>/health/` and verify `product` is `klockin`. Open `/ready/` and verify the database, cache, and scheduler each report `ok`. Check that the scheduler container is running because its readiness field reflects registered jobs.
4. On the sign-in page, choose **Initialize Database** and use the configured setup password to create the first administrator. Store the password privately. Then verify sign-in and open Timekeeping.

The default trusted proxy hostname is `dokploy-traefik`. Verify the web service can resolve the actual ingress proxy on its Dokploy network if IP-based login lockouts or office-IP rules are required. Override `KLOCKIN_TRUSTED_PROXIES` with the actual proxy hostname or address for a custom Dokploy installation.

[Dokploy Compose](https://docs.dokploy.com/docs/core/docker-compose) · [Compose domains](https://docs.dokploy.com/docs/core/docker-compose/domains)
