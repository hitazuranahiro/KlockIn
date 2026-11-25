# Uploaded-file storage

KlockIN stores uploads on local disk by default. Select S3 storage to put regular uploads such as employee documents, attachments, and profile photos in a private Cloudflare R2 or S3-compatible bucket. The same setting selects S3 for attendance selfies. KlockIN serves regular uploads through its own media routes and applies the usual permissions. Attendance selfies keep their separate encryption and reviewer access. PostgreSQL stores the file references and attendance records.

## Configure Cloudflare R2

Create a dedicated private bucket and generate an R2 token with **Object Read & Write** scoped to that bucket. Add the following settings to the server environment or production Compose `.env`. For a jurisdiction-specific bucket, use the endpoint shown by Cloudflare. With another S3-compatible provider, use its HTTPS endpoint and signing region. [Cloudflare R2 setup](https://developers.cloudflare.com/r2/get-started/s3/) · [R2 credentials](https://developers.cloudflare.com/r2/api/tokens/)

```dotenv
KLOCKIN_UPLOAD_STORAGE=s3
KLOCKIN_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
KLOCKIN_S3_BUCKET=klockin-uploads
KLOCKIN_S3_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
KLOCKIN_S3_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
KLOCKIN_S3_REGION=auto
```

Install the updated Python requirements or rebuild the production image. Keep the attendance evidence and backup keys in the server environment. Regular files use the `uploads/` object prefix, and encrypted attendance photos use `punches/`. Keep public bucket access disabled. [Attendance evidence keys](klockin-private-evidence.md)

## Move existing uploads

If the installation already has files, configure the S3 credentials and leave the existing storage selection in place until the copies are verified. Back up PostgreSQL and both file stores. For the final pass, pause uploads and punches until the services have switched to the new backend.

```sh
python manage.py migrate_uploaded_media
python manage.py migrate_uploaded_media --apply
```

The default source is `MEDIA_ROOT`. Use `--source /path/to/media` to copy from a different directory. The dry run checks destination files and reports what would be copied. Applying the migration preserves relative filenames and verifies bytes after upload. A rerun accepts matching objects and reports any different object at the same key. The command leaves local originals in place and skips hidden paths, symlinks, and other non-regular files. This keeps runtime-only files such as `media/.generated_secret_key` on the server.

For production Compose, use a one-off web container in the same Compose project while the database is available. Run a dry run first by omitting `--apply`.

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps \
  -e HORILLA_SKIP_RELEASE_TASKS=1 web python manage.py migrate_uploaded_media --apply
```

If attendance photos are still local, run their [separate encrypted import](klockin-private-evidence.md#move-existing-photos). If photos already use R2, keep the existing bucket and credentials when enabling the combined setting. After the copies are verified, set `KLOCKIN_UPLOAD_STORAGE=s3` and recreate the web and scheduler services together.

On staging, upload and reopen a representative document, an attachment, and a profile image. Open a migrated file and confirm a user without permission is denied. Clock in and out once and check both selfies in Timekeeping. Verify the backup against that deployment before opening access to users.

## Backup and rollback

Keep a matching PostgreSQL backup, a private export of the `uploads/` prefix, and a [verified attendance evidence archive](klockin-private-evidence.md#backup-and-restore). Pause writes while capturing the three parts when you need a single recovery point. Store the copies somewhere access-controlled and separate from the live bucket.

If Google Drive media backup is configured, its media ZIP reads from the selected upload store. The uploaded OAuth setup file is read by the server and excluded from the media ZIP and the export below. Keep it in a separate secrets backup or reconnect Google Drive after recovery.

To export regular files, configure a read-only R2 AWS CLI profile and sync the prefix to a new private directory. This copies the contents of `uploads/` without the prefix, so the export can be used as a local media root. [Cloudflare AWS CLI guide](https://developers.cloudflare.com/r2/examples/aws/aws-cli/) · [AWS CLI sync reference](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html)

```sh
aws s3 sync "s3://${KLOCKIN_S3_BUCKET}/uploads/" /secure/klockin-media-export/ \
  --profile klockin-r2 --region auto --endpoint-url "${KLOCKIN_S3_ENDPOINT_URL}" \
  --no-follow-symlinks --exclude '.*' --exclude '*/.*' \
  --exclude 'gdrive_oauth_credentials_file/*' --exclude 'gdrive_service_account_file/*'
```

For rollback after the bucket receives new files, pause writes and make a fresh three-part backup. Restore the regular file export into a clean media volume, restore the attendance archive into its private volume, and use the corresponding PostgreSQL backup. Set `KLOCKIN_UPLOAD_STORAGE=local` and verify file downloads and punch previews before resuming writes.
