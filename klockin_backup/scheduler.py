from pathlib import Path
from tempfile import TemporaryDirectory

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.files.storage import default_storage

from .gdrive import authenticate, upload_file

# from klockin.settings import DBBACKUP_STORAGE_OPTIONS
from .models import GoogleDriveBackup
from .pgdump import dump_postgres_db
from .zip import zip_folder, zip_uploaded_files

# ponytail: still a per-process BackgroundScheduler, unlike the jobs moved to
# klockin.scheduling. This one is reconfigured at runtime from views.py (an
# admin editing the Google Drive backup config calls start/stop directly), so it
# needs a mutable live scheduler rather than a static registry. It therefore
# still runs one copy per gunicorn worker. Fix by moving job control behind the
# DjangoJobStore -- run_scheduler owns execution, views only write config rows.
scheduler = BackgroundScheduler()

# def backup_database():
#     folder_path = DBBACKUP_STORAGE_OPTIONS['location']
#     local_backup = LocalBackup.objects.first()
#     if folder_path and local_backup:
#         DBBACKUP_STORAGE_OPTIONS['location'] = local_backup.backup_path
#         folder_path = DBBACKUP_STORAGE_OPTIONS['location']
#         if local_backup.backup_db:
#             call_command('dbbackup')
#         if local_backup.backup_media:
#             call_command("mediabackup")
#         files = sorted(os.listdir(folder_path), key=lambda x: os.path.getctime(os.path.join(folder_path, x)))

#         # Remove all files except the last two
#         if len(files) > 2:
#             for file_name in files[:-2]:
#                 file_path = os.path.join(folder_path, file_name)
#                 if os.path.isfile(file_path):
#                     try:
#                         os.remove(file_path)
#                     except:
#                         pass


# def start_backup_job():
#     """
#     Start the backup job based on the LocalBackup configuration.
#     """
#     # Check if any LocalBackup object exists
#     if LocalBackup.objects.exists():
#         local_backup = LocalBackup.objects.first()

#             # Remove existing job if it exists
#         try:
#             scheduler.remove_job('backup_job')
#         except:
#             pass

#         # Add new job based on LocalBackup configuration
#         if local_backup.interval:
#             scheduler.add_job(backup_database, 'interval', seconds=local_backup.seconds, id='backup_job')
#         else:
#             scheduler.add_job(backup_database, trigger='cron', hour=local_backup.hour, minute=local_backup.minute, id='backup_job')
#         # Start the scheduler if it's not already running
#         if not scheduler.running:
#             scheduler.start()
#     else:
#         stop_backup_job()


# def stop_backup_job():
#     """
#     Stop the backup job if it exists.
#     """
#     try:
#         scheduler.remove_job('backup_job')
#     except:
#         pass


# def restart_backup_job():
#     """
#     Restart the backup job by stopping it and starting it again.
#     """
#     stop_backup_job()
#     start_backup_job()


def google_drive_backup():
    google_drive = GoogleDriveBackup.objects.first()
    if google_drive is None or not (google_drive.backup_db or google_drive.backup_media):
        return

    credentials = authenticate(google_drive)
    folder_id = google_drive.gdrive_folder_id
    with TemporaryDirectory(prefix="klockin-drive-backup-") as directory:
        if google_drive.backup_db:
            db = settings.DATABASES["default"]
            output_file = Path(directory) / "backupdb.dump"
            dump_postgres_db(
                db_name=db["NAME"],
                username=db["USER"],
                output_file=output_file,
                password=db["PASSWORD"],
                host=db.get("HOST") or "localhost",
                port=db.get("PORT") or 5432,
            )
            upload_file(output_file, credentials, folder_id)
        if google_drive.backup_media:
            output_file = Path(directory) / "media.zip"
            if hasattr(default_storage, "iter_upload_names"):
                zip_uploaded_files(default_storage, output_file)
            else:
                zip_folder(settings.MEDIA_ROOT, output_file)
            upload_file(output_file, credentials, folder_id)


def start_gdrive_backup_job():
    """
    Start the backup job based on the LocalBackup configuration.
    """
    # Check if any Gdrive Backup object exists
    if GoogleDriveBackup.objects.exists():
        gdrive_backup = GoogleDriveBackup.objects.first()

        # Remove existing job if it exists
        try:
            scheduler.remove_job("backup_job")
        except:
            pass
        # Add new job based on Gdrive Backup configuration
        if gdrive_backup.interval:
            scheduler.add_job(
                google_drive_backup,
                "interval",
                seconds=gdrive_backup.seconds,
                id="gdrive_backup_job",
            )
        else:
            scheduler.add_job(
                google_drive_backup,
                trigger="cron",
                hour=gdrive_backup.hour,
                minute=gdrive_backup.minute,
                id="gdrive_backup_job",
            )

        # Start the scheduler if it's not already running
        if not scheduler.running:
            scheduler.start()

    else:
        stop_gdrive_backup_job()


def stop_gdrive_backup_job():
    """
    Stop the backup job if it exists.
    """
    try:
        scheduler.remove_job("gdrive_backup_job")
    except:
        pass


# def restart_gdrive_backup_job():
#     """
#     Restart the backup job by stopping it and starting it again.
#     """
#     stop_gdrive_backup_job()
#     start_gdrive_backup_job()
