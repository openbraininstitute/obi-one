from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=True,
    )

    APP_NAME: str = "obi-one"
    APP_VERSION: str | None = None
    APP_DEBUG: bool = False
    APP_DISABLE_AUTH: bool = False

    COMMIT_SHA: str | None = None

    ENVIRONMENT: str | None = None
    ROOT_PATH: str = ""
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",  # for local tests
        "http://127.0.0.1:3000",  # for local tests
        "https://openbraininstitute.org",
        "https://www.openbraininstitute.org",
        "https://staging.openbraininstitute.org",
        "https://next.staging.openbraininstitute.org",
    ]
    CORS_ORIGIN_REGEX: str | None = None

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    LOG_SERIALIZE: bool = True
    LOG_BACKTRACE: bool = False
    LOG_DIAGNOSE: bool = False
    LOG_ENQUEUE: bool = False
    LOG_CATCH: bool = True
    LOG_STANDARD_LOGGER: dict[str, str] = {"root": "INFO"}

    KEYCLOAK_URL: str = "https://example.openbluebrain.com/auth/realms/SBO"
    AUTH_CACHE_MAXSIZE: int = 128  # items
    AUTH_CACHE_MAX_TTL: int = 300  # seconds
    AUTH_CACHE_INFO: bool = False

    OUTPUT_DIR: Path = Path("../obi-output")
    ENTITYCORE_URL: str = "http://127.0.0.1:8000"
    LAUNCH_SYSTEM_URL: str = "http://127.0.0.1:8001"
    LAUNCH_SYSTEM_OUTPUT_DIR: str = "./obi-output"
    ACCOUNTING_BASE_URL: str = "http://127.0.0.1:8002"
    ACCOUNTING_DISABLED: bool = False

    # Path to the obi-one repository
    OBI_ONE_REPO: str = "https://github.com/openbraininstitute/obi-one.git"

    # Path to launch script within the repository. Must contain code.py and requirements.txt.
    OBI_ONE_LAUNCH_PATH: str = "launch_scripts/launch_task_for_single_config_asset"


settings = Settings()
