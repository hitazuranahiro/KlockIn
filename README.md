# KlockIN by Tomeku

KlockIN is an electronic daily time record and attendance application for Philippine workplaces. The Django web application includes the Timekeeping workspace, employee attendance, corrections, and DTR exports. The Flutter app captures attendance with a front-camera selfie and GPS, queues punches on the device, and syncs them to the same server.

## Run locally

Use Python 3.12–3.14 with PostgreSQL, or start the development Compose stack with `docker compose up --build`. Compose publishes the development web service at [127.0.0.1:8000](http://127.0.0.1:8000).

For a native macOS or Linux setup with PostgreSQL already running:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
createdb klockin_local
export DATABASE_URL=postgresql:///klockin_local
export DEBUG=1
export ALLOWED_HOSTS=localhost,127.0.0.1
export DB_INIT_PASSWORD='<choose-your-local-setup-password>'
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8097
```

For the native setup, run `.venv/bin/python manage.py run_scheduler` in a second shell with the same environment.

On macOS, run the preview from a fully downloaded checkout. If iCloud has offloaded a project file, Django waits for macOS to retrieve it before it can serve that asset. A checkout outside iCloud avoids that delay.

On the first launch, choose **Initialize database** on the [sign-in page](http://127.0.0.1:8097/login/) and enter your setup password. The wizard creates the initial administrator and employee profile. Create your employees, work profiles, and shift schedules before enrolling phones. Open **Timekeeping** to filter attendance or export a monthly DTR. Reviewers need View attendance and Can view mobile punch evidence for company-scoped access to selfies, GPS, and device details. Grant Change attendance to staff who can make corrections.

Use **Guided tours** in the workspace header for help with the dashboard, Timekeeping, and Projects. See the [guided tour guide](docs/klockin-guided-tours.md) for tour administration and the `klockin/tours` source layout.

## Mobile

The Flutter source is under `mobile/app`. Run `flutter pub get`, then `flutter run` from that directory using the Flutter toolchain listed in the [mobile README](mobile/README.md). Enter the KlockIN server address and sign in with your Employee ID (badge ID) and password. KlockIN enrolls the phone on the first successful mobile sign-in. Choose a server address reachable from the phone or emulator and use HTTPS for remote environments.

The encrypted credentials belong to the selected account/server. KlockIN stages a punch in its private queue until the server acknowledges it, then removes the queued selfie. A punch awaiting HR review is already received by the server. It may have arrived before its matching punch or conflict with a protected historical record.

In **Timekeeping**, authorized HR staff can open **Punches awaiting review** and attach the evidence to an eligible daily record. The review records the staff member, timestamp, reason, and selected record. **Unsynced device queues** shows each linked device's last reported pending count and when it was observed. A disconnected device updates the count when it reconnects.

Timekeeping includes a date-range attendance summary and a paired monthly Civil Service Form 48 export with AM/PM and first-in/last-out options. Attendance corrections require a reason. The employee profile's **Attendance Audit** tab shows authorized reviewers the previous and new values, responsible user, correction reason, and timestamp.

Device resets in Django admin require a superuser and a separate reset PIN. Set `KLOCKIN_DEVICE_RESET_PIN_HASH` to a Django-encoded hash before using this action. KlockIN records the reset and its operator in the administration log.

GPS is stored with each punch. To display an address, set `KLOCKIN_REVERSE_GEOCODER_URL` to a company-approved HTTPS, Nominatim-compatible reverse lookup endpoint. KlockIN sends the coordinates only to the configured service. Punches still sync when the service is unavailable.

Every mobile Time In and Time Out requires a fresh front-camera selfie and GPS reading. Online punches use the server clock. Offline punches keep the original device capture time. KlockIN keeps the first server receipt time on the punch, and the mobile app records the latest successful sync acknowledgment.

In Django administration, open **Attendance policies** to choose **Paired Time In/Out** or **First In / Last Out** for a company. Enter both unpaid break times to deduct the portion of the break that overlaps recorded work. A change applies when a new mobile workday record is created. Previously recorded days retain their policy. Under **Attendance → Settings → Geofencing**, enable the primary location and add any alternate work locations. The server validates punches, including offline queue uploads, against the company's active sites.

The mobile server setting accepts a full HTTPS installation address with an optional port and path. For an installation mounted at `/edtr`, enter `https://example.org:8088/edtr` or `https://example.org:8088/edtr/api`. The reverse proxy for that installation must route `/edtr/health/` and `/edtr/api/` to this same KlockIN instance and remove the installation path before forwarding to Django.


## Production Compose

Use a running Docker Engine with Compose 2.24 or later and enough disk space for the images and database volumes. Supply a domain and its `fullchain.pem` and `privkey.pem`. Copy `.env.dist` to `.env`. Set the allowed host and HTTPS CSRF origin, replace the database, Redis, and Django secrets, and point `KLOCKIN_TLS_DIR` to the certificate directory. Keep the Redis and PostgreSQL credentials consistent with their connection URLs.

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Nginx redirects HTTP to HTTPS and proxies to Django over the private Compose network. Production requires an evidence encryption key. Set `KLOCKIN_UPLOAD_STORAGE=s3` to store ordinary uploads and encrypted attendance selfies in a private Cloudflare R2 or S3-compatible bucket. Local volumes are the default. Django applies the existing file permissions when serving uploads and selfies. Keep uploaded files, PostgreSQL, and a matching verified selfie archive in backups. See the [upload storage setup and migration guide](docs/klockin-upload-storage.md). Configure the Django background scheduler once per installation. Manila time is the default for shift attribution and reporting.

## Verification

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py test klockin_attendance --noinput
docker compose config --quiet
```

The [inherited LGPL 2.1 license](LICENSE) and [source notices](docs/klockin-source-notices.md) apply to the upstream components.
