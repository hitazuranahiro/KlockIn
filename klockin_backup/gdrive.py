import json
from datetime import UTC
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def authenticate(backup):
    if not backup.oauth_credentials_file or not (
        backup.access_token or backup.refresh_token
    ):
        raise ImproperlyConfigured("Connect Google Drive OAuth before running backups.")

    with backup.oauth_credentials_file.open("rb") as source:
        client = json.load(source)["web"]
    expiry = backup.token_expiry
    if expiry is not None and expiry.tzinfo is not None:
        expiry = expiry.astimezone(UTC).replace(tzinfo=None)
    return Credentials(
        token=backup.access_token,
        refresh_token=backup.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=SCOPES,
        expiry=expiry,
    )


def upload_file(file_path, credentials, parent_folder_id):
    file_metadata = {"name": Path(file_path).name, "parents": [parent_folder_id]}
    media = MediaFileUpload(str(file_path), resumable=True)
    with build("drive", "v3", credentials=credentials) as service:
        service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
