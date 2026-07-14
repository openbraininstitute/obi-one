from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class CircuitExtractionSettings(BaseModel):
    benchmarking_enabled: bool = True
    run_validation: bool = False


class CaveClientConfig(BaseModel):
    microns_api_key: str = "CAVECLIENT_MICRONS_API_KEY"
    # Retry behaviour for the CAVEClient materialization engine (urllib3 Retry).
    # The engine intermittently returns 503s; these widen caveclient's weak
    # built-in defaults so transient outages are ridden out before failing.
    max_retries: int = 8
    retry_backoff_factor: float = 0.5
    retry_backoff_max: float = 120.0
    retry_status_forcelist: tuple[int, ...] = (429, 502, 503, 504)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OBI_ONE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    circuit_extraction: CircuitExtractionSettings = CircuitExtractionSettings()

    cave_client_config: CaveClientConfig = CaveClientConfig()


settings = Settings()
