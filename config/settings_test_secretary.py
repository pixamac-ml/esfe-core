from .settings_test_local import *

# Use a separate throwaway SQLite file so the test DB is not the same as the
# default DB and avoids the lock/deletion issues on Windows.
DATABASES["default"]["NAME"] = BASE_DIR / "_test_default.sqlite3"
DATABASES["default"]["TEST"]["NAME"] = BASE_DIR / "_test_secretary.sqlite3"
