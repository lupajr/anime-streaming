"""Configuração da aplicação (lida de variáveis de ambiente / .env)."""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Credencial da Service Account (montada como Docker secret, somente leitura)
    google_credentials_file: str = "/run/secrets/gdrive_sa"

    # Pasta raiz da biblioteca. Se DRIVE_FOLDER_ID estiver vazio, procura pelo nome.
    drive_folder_id: str = ""
    drive_folder_name: str = "Animes"

    data_dir: str = "/data"
    static_dir: str = "/app/static"

    # Por quanto tempo a listagem do Drive fica em cache antes de ser renovada
    library_ttl_seconds: int = Field(1800, ge=60)

    # Limites de processos FFmpeg simultâneos (proteção contra sobrecarga)
    max_transcodes: int = Field(2, ge=1, le=8)
    max_subtitle_jobs: int = Field(2, ge=1, le=8)

    transcode_preset: Literal[
        "ultrafast", "superfast", "veryfast", "faster", "fast", "medium"
    ] = "veryfast"
    transcode_crf: int = Field(23, ge=15, le=35)
    transcode_max_height: int = Field(1080, ge=360, le=2160)

    enable_docs: bool = False
    log_level: Literal["debug", "info", "warning", "error"] = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
