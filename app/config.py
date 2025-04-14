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
    ]

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


settings = Settings()
