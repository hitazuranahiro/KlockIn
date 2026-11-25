import os
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from shutil import copyfileobj


def _is_backup_upload(name):
    path = PurePosixPath(name)
    return (
        bool(path.parts)
        and path.as_posix() == name
        and not path.is_absolute()
        and not PureWindowsPath(name).drive
        and "\x00" not in name
        and "\\" not in name
        and not any(part.startswith(".") for part in path.parts)
        and path.parts[0] not in (
            "gdrive_oauth_credentials_file",
            "gdrive_service_account_file",
        )
    )


def zip_folder(folder_path, output_zip_path):
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [name for name in dirs if not name.startswith(".")]
            for filename in files:
                path = Path(root) / filename
                name = path.relative_to(folder_path).as_posix()
                if _is_backup_upload(name) and not path.is_symlink():
                    zipf.write(path, name)


def zip_uploaded_files(storage, output_zip_path):
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for name in storage.iter_upload_names():
            if _is_backup_upload(name):
                with storage.open(name, "rb") as source, zipf.open(
                    name, "w", force_zip64=True
                ) as target:
                    copyfileobj(source, target)
