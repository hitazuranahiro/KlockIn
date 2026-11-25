"""Copy bundled demo media into the configured upload storage."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

DEMO_COMPANY_ICON = "base/icon/KlockIN.png"


def _copy_glob(src_dir: Path, dest_dir: Path, pattern: str) -> int:
    if not src_dir.exists():
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in src_dir.glob(pattern):
        if not src.is_file():
            continue
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        copied += 1
    return copied


def _seed_object_uploads(root):
    def copy(source, name):
        if default_storage.exists(name):
            return
        with source.open("rb") as content:
            try:
                default_storage.write_if_absent(name, content, source.stat().st_size)
            except FileExistsError:
                pass

    icons = [file for file in (root / "icons").glob("*.png") if file.is_file()]
    for file in icons:
        copy(file, f"base/icon/{file.name}")

    reference = root / "icons" / Path(DEMO_COMPANY_ICON).name
    if reference.is_file():
        for number in range(1, 4):
            copy(reference, f"base/icon/Horilla_{number}.png")

    avatars = [file for file in (root / "avatars").glob("avatar_*.jpg") if file.is_file()]
    if not avatars:
        avatars = [file for file in (root / "avatars").glob("*.jpg") if file.is_file()]
    for file in avatars:
        copy(file, f"employee/profile/{file.name}")
    return len(icons), len(avatars)


def copy_demo_media(load_dir: Path | None = None) -> dict[str, int]:
    """
    Copy company icons and employee avatars to their fixture paths.

    Fixture image fields point at ``base/icon/*.png`` and
    ``employee/profile/avatar_*.jpg`` — without this step those URLs 404.
    """
    root = Path(load_dir) if load_dir else Path(settings.BASE_DIR) / "load_data"
    if settings.KLOCKIN_UPLOAD_STORAGE == "s3":
        icons, avatars = _seed_object_uploads(root)
        logger.info("Demo media available: icons=%s avatars=%s", icons, avatars)
        return {"icons": icons, "avatars": avatars}

    media = Path(settings.MEDIA_ROOT)

    icon_directory = (media / DEMO_COMPANY_ICON).parent
    icons = _copy_glob(root / "icons", icon_directory, "*.png")
    reference_icon = media / DEMO_COMPANY_ICON
    if reference_icon.is_file():
        # Restored demo databases may still point at these filenames. Fill
        # any missing media without replacing files already on disk.
        for number in range(1, 4):
            previous_icon = icon_directory / f"Horilla_{number}.png"
            if not previous_icon.exists():
                shutil.copy2(reference_icon, previous_icon)

    avatars = _copy_glob(
        root / "avatars", media / "employee" / "profile", "avatar_*.jpg"
    )
    if avatars == 0:
        avatars = _copy_glob(root / "avatars", media / "employee" / "profile", "*.jpg")

    logger.info("Demo media copied: icons=%s avatars=%s", icons, avatars)
    return {"icons": icons, "avatars": avatars}
