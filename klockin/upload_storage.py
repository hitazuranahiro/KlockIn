"""Private regular uploads served through the application media route."""

from contextlib import ExitStack, closing
from shutil import copyfileobj
from tempfile import SpooledTemporaryFile
from urllib.parse import urljoin, urlsplit

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files import File
from django.utils.encoding import filepath_to_uri
from storages.backends.s3 import S3Storage


def _validate_name(name):
    if (
        not isinstance(name, str) or "\\" in name or "\0" in name
        or any(not part or part.startswith(".") for part in name.split("/"))
    ):
        raise SuspiciousFileOperation("Invalid upload filename.")


class PrivateUploadStorage(S3Storage):
    """Keep the bucket private and expose the same URL as local uploads."""

    def __init__(self):
        endpoint_url = settings.KLOCKIN_S3_ENDPOINT_URL
        bucket_name = settings.KLOCKIN_S3_BUCKET
        region_name = settings.KLOCKIN_S3_REGION
        access_key = settings.KLOCKIN_S3_ACCESS_KEY_ID
        secret_key = settings.KLOCKIN_S3_SECRET_ACCESS_KEY
        if not all((endpoint_url, bucket_name, region_name, access_key, secret_key)):
            raise ImproperlyConfigured("Configure the KLOCKIN_S3 endpoint, bucket, region, and credentials.")
        try:
            endpoint = urlsplit(endpoint_url)
            port = endpoint.port
        except ValueError:
            raise ImproperlyConfigured("Set a valid HTTPS KLOCKIN_S3_ENDPOINT_URL.") from None
        if (
            endpoint.scheme != "https" or not endpoint.hostname or port == 0
            or endpoint.username is not None or endpoint.password is not None
            or endpoint.path not in ("", "/") or endpoint.query or endpoint.fragment
        ):
            raise ImproperlyConfigured("Set an HTTPS KLOCKIN_S3_ENDPOINT_URL with only a host and optional port.")
        super().__init__(
            endpoint_url=endpoint_url,
            bucket_name=bucket_name,
            region_name=region_name,
            access_key=access_key,
            secret_key=secret_key,
            security_token=None,
            session_profile=None,
            location="uploads",
            default_acl=None,
            custom_domain=None,
            cloudfront_key_id=None,
            cloudfront_key=None,
            object_parameters={},
            file_overwrite=False,
            gzip=False,
            use_ssl=True,
            verify=True,
            client_config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=3,
                read_timeout=30,
                retries={"mode": "standard", "total_max_attempts": 2},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def url(self, name, *args, **kwargs):
        _validate_name(name)
        return urljoin(settings.MEDIA_URL, filepath_to_uri(name))

    def _normalize_name(self, name):
        _validate_name(name)
        return super()._normalize_name(name)

    def exists(self, name):
        try:
            return super().exists(name)
        except (BotoCoreError, ClientError) as exc:
            raise OSError("Upload availability could not be checked in object storage.") from exc

    def delete(self, name):
        try:
            return super().delete(name)
        except (BotoCoreError, ClientError) as exc:
            raise OSError("Upload could not be deleted from object storage.") from exc

    def _open(self, name, mode="rb"):
        if mode not in ("r", "rb"):
            raise ValueError("Use the storage save method to write uploads.")
        key = self._normalize_name(name)
        with ExitStack() as cleanup:
            temporary = cleanup.enter_context(SpooledTemporaryFile(max_size=8 * 1024 * 1024))
            try:
                result = self.connection.meta.client.get_object(Bucket=self.bucket_name, Key=key)
                with closing(result["Body"]) as body:
                    copyfileobj(body, temporary)
                temporary.seek(0)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "NotFound", "404"):
                    raise FileNotFoundError("Upload does not exist.") from exc
                raise OSError("Upload could not be read from object storage.") from exc
            except BotoCoreError as exc:
                raise OSError("Upload could not be read from object storage.") from exc
            cleanup.pop_all()
        return File(temporary, name=name)

    def iter_upload_names(self):
        prefix = self.location + "/"
        client = self.connection.meta.client
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket_name, Prefix=prefix
        ):
            for item in page.get("Contents", ()):
                name = item["Key"].removeprefix(prefix)
                try:
                    _validate_name(name)
                except SuspiciousFileOperation:
                    continue
                yield name

    def write_if_absent(self, name, source, size):
        key = self._normalize_name(name)
        parameters = self._get_write_parameters(key)
        try:
            self.connection.meta.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=source,
                ContentLength=size,
                IfNoneMatch="*",
                **parameters,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
                raise FileExistsError("An upload already exists under this name.") from exc
            raise OSError("Upload could not be saved to object storage.") from exc
        except BotoCoreError as exc:
            raise OSError("Upload could not be saved to object storage.") from exc

    def _save(self, name, content):
        content.seek(0)
        self.write_if_absent(name, content, content.size)
        return name


def s3_upload_storage():
    return PrivateUploadStorage()
