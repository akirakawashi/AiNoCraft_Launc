"""
Configuration package — public API.

All symbols are re-exported here so that existing
``from config import X`` imports continue to work unchanged.

Internal structure:
  - :mod:`config.constants` — app metadata, runtime defaults, auth config
  - :mod:`config.paths`     — filesystem paths
  - :mod:`config.profiles`  — build profile dataclasses, loading, resolution
"""

# Constants
from config.constants import (  # noqa: F401
    APP_NAME,
    ASSETS_INDEX,
    AUTH_API_BASE_URL,
    AUTH_AUTHENTICATE_URL,
    AUTHLIB_INJECTOR_API_BASE_URL,
    AUTHLIB_INJECTOR_JAR_NAME,
    AUTHLIB_INJECTOR_JAR_PATH,
    AUTH_INVALIDATE_URL,
    AUTH_LOGIN_URL,
    AUTH_LOGOUT_URL,
    AUTH_SERVER_BASE_URL,
    AUTH_SERVER_PRESETS,
    AUTH_SERVER_PROFILE,
    AUTH_REFRESH_URL,
    AUTH_SIGNOUT_URL,
    LAUNCHER_UPDATE_URL,
    AUTH_TIMEOUT_SEC,
    AUTH_VALIDATE_URL,
    DEFAULT_ACCESS_TOKEN,
    DEFAULT_CLIENT_ID,
    DEFAULT_SETTINGS,
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_PROGRESS_INTERVAL_SEC,
    DOWNLOAD_TIMEOUT_SEC,
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
    LAUNCHER_WINDOW_TITLE,
    RAM_DEFAULT_GB,
    RAM_MAX_GB,
    RAM_MIN_GB,
    WINDOW_BACKGROUND_COLOR,
    WINDOW_HEIGHT,
    WINDOW_RESIZABLE,
    WINDOW_WIDTH,
)

# Paths
from config.paths import (  # noqa: F401
    APPDATA_DIR,
    BUILD_PROFILES_FILE,
    DOWNLOAD_TEMP_DIR,
    GAME_DIR,
    JAVA_BIN,
    LAUNCHER_DATA_DIR,
    LAUNCHER_DIR,
)

# Profiles (data classes, loaders, helpers)
from config.profiles import (  # noqa: F401
    BUILD_PROFILES,
    BuildPaths,
    BuildProfile,
    DEFAULT_BUILD_ID,
    DEFAULT_BUILD_PROFILES,
    get_available_builds,
    get_build_paths,
    get_runtime_config,
    resolve_client_files,
)

# ── Backward compatibility constants (default build) ────────────────────────

_DEFAULT = get_build_paths(DEFAULT_BUILD_ID)
VERSION_NAME = _DEFAULT.version_name
VERSION_DIR = _DEFAULT.version_dir
VERSION_JSON = _DEFAULT.version_json
CLIENT_JAR = _DEFAULT.client_jar
ASSETS_DIR = _DEFAULT.assets_dir
LIBRARIES_DIR = _DEFAULT.libraries_dir
NATIVES_DIR = _DEFAULT.natives_dir
SETTINGS_FILE = _DEFAULT.settings_file
DOWNLOAD_URL = _DEFAULT.download_url
