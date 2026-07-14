"""Isolated full-site settings for the manual SYSTEM session recipe."""

from pathlib import Path
import os

from .settings_test_local import *  # noqa: F403


ROOT_URLCONF = "config.urls"

_default_db_path = Path(BASE_DIR) / "test_session_qa.sqlite3"  # noqa: F405
_db_path = Path(os.getenv("SESSION_QA_DB_PATH", str(_default_db_path)))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _db_path,
        "TEST": {"NAME": _db_path},
    }
}

