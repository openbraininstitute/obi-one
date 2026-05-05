from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class CircuitExtractionSettings(BaseModel):
    benchmarking_enabled: bool = True
    run_validation: bool = False


class CaveClientConfig(BaseModel):
    microns_api_key: str = "CAVECLIENT_MICRONS_API_KEY"


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
