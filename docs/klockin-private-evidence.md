# Private attendance evidence

KlockIN encrypts new punch selfies, latitude, longitude, and populated addresses when `KLOCKIN_EVIDENCE_KEYS` is configured. Production startup requires at least one key. Use separately generated secrets for the comma-separated `KLOCKIN_EVIDENCE_KEYS` and `KLOCKIN_EVIDENCE_BACKUP_KEY` settings. A key can be generated locally with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Store the keys separately from the database dumps and archive files. The first evidence key encrypts new data. Keep older keys in the list while you still need to read evidence or backups made with them.

## Cloudflare R2 or S3-compatible storage

KlockIN defaults to local private selfie storage. Use `KLOCKIN_UPLOAD_STORAGE=s3` to use a private bucket for both attendance photos and regular uploads. Existing `KLOCKIN_SELFIE_STORAGE` deployments can continue using the attendance-only configuration until you set the combined switch. See the [uploaded-file storage guide](klockin-upload-storage.md) for credentials and deployment settings.

The S3 backend requires `KLOCKIN_EVIDENCE_KEYS` so KlockIN can encrypt and authenticate photo objects. PostgreSQL keeps punch records, coordinates, and photo names. KlockIN's server uploads and decrypts the objects and checks reviewer permissions before serving previews.

### Move existing photos

For a fresh installation with no selfie records, select `s3` at deployment. For an existing local installation, supply the S3 credentials and keep local storage active during the copy. Take a verified evidence archive and a corresponding PostgreSQL backup. Pause punch writes before the final verified import and keep them paused until the backend has switched. Retain the local volume and archive after cutover. If legacy GPS and address values need encryption, run the legacy encryption command while local storage is active.

Use the current private volume as the source. For production Compose, its path inside the container is `/app/private-media/attendance`. The first command checks the source and bucket. `--apply` copies and verifies encrypted objects with their original names. A rerun accepts matching objects, and the source files stay available for recovery.

```sh
python manage.py import_private_evidence_to_s3 --source /app/private-media/attendance
python manage.py import_private_evidence_to_s3 --source /app/private-media/attendance --apply
```

With production Compose and the web service stopped, run each command in a one-off web container on the same Compose project.

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps \
  -e KLOCKIN_SKIP_RELEASE_TASKS=1 web python manage.py import_private_evidence_to_s3 \
  --source /app/private-media/attendance --apply
```

After [migrating any regular uploads](klockin-upload-storage.md#move-existing-uploads), set `KLOCKIN_UPLOAD_STORAGE=s3` and recreate the web and scheduler services together. On staging, confirm a new Clock In and Clock Out create encrypted objects and their selfies open in **Timekeeping** for an authorized reviewer. Also open a migrated selfie, test denied access for a user without permission, and verify a new evidence archive. If R2 already has new punches when you need to roll back, include a fresh evidence archive and matching PostgreSQL backup in the [rollback](klockin-upload-storage.md#backup-and-rollback).

## Backup and restore

The archive command reads the active backend. With local storage it covers the private selfie volume. With S3 it covers the photo keys referenced by attendance records. Capture a matching PostgreSQL backup and protect the database dump separately. Pause punch writes while taking both backups so they represent the same point in time. Legacy punches and older PostgreSQL dumps may still contain unencrypted location values until migrated or replaced.

```sh
python manage.py backup_private_evidence create /secure/backups/klockin-evidence.kb
python manage.py backup_private_evidence verify /secure/backups/klockin-evidence.kb
```

For a legacy local photo volume, use the encryption command after verifying the archive.

```sh
python manage.py encrypt_attendance_evidence
python manage.py encrypt_attendance_evidence --apply --backup /secure/backups/klockin-evidence.kb
```

The legacy scan defaults to a dry run. Applying it verifies the archive and checks each legacy photo against its recoverable backup before replacing it atomically. A matching encrypted record is safe to read and a rerun leaves already encrypted data alone. A missing or changed legacy photo stops the command. Refresh the backup and rerun after resolving the discrepancy.

```sh
python manage.py backup_private_evidence restore /secure/backups/klockin-evidence.kb --destination /secure/klockin-restore
python manage.py backup_private_evidence restore /secure/backups/klockin-evidence.kb --destination /secure/klockin-restore --apply
```

Restore first verifies without writing. With `--apply`, it creates a new staging directory containing authenticated encrypted photos. It rejects an existing destination and any destination inside the live local evidence or public media/static roots. Verify the restored photos with the matching database on an isolated instance. For local storage, use the restored directory as `KLOCKIN_SELFIE_ROOT` or move it into place. For S3, point the import command's `--source` at this staging directory and use a private recovery bucket.

Mobile audit entries are read-only through Django administration and `GET /api/v2/attendance/mobile-audit/`. The endpoint requires `klockin_attendance.view_mobileactivity` and scopes company records to the viewer. Only superusers can view events without an identified company, such as failed anonymous sign-ins. The audit stores actor and company IDs, a punch UUID or batch correlation ID when available, timestamps, outcomes, and counts.
