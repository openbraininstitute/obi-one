from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from obi_one_lazy.config import CaveClientConfig


class CircuitExtractionSettings(BaseModel):
    benchmarking_enabled: bool = True
    run_validation: bool = False


class SynapseParameterizationSettings(BaseModel):
    benchmarking_enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OBI_ONE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    circuit_extraction: CircuitExtractionSettings = CircuitExtractionSettings()

    synapse_parameterization: SynapseParameterizationSettings = SynapseParameterizationSettings()

    cave_client_config: CaveClientConfig = CaveClientConfig()


settings = Settings()
