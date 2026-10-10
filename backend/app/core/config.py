import json
from pathlib import Path
from typing import List, Optional, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# .env is read from backend/ whatever directory the server is started from, and so are the database
# and the upload folder when they are given as relative paths.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"

DEFAULT_SECRET_KEY = "dev_secret_unleash_verification_key_change_in_prod"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Safe by default: forgetting to set these on a server must not leave the weak development key or
    # the unauthenticated /verify demo switched on. Local work sets ENVIRONMENT=development in backend/.env.
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    SESSION_EXPIRY_SECONDS: int = 120

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Storage
    DATABASE_URL: str = "sqlite:///./unleash.db"
    UPLOAD_TEMP_DIR: str = "./temp_uploads"
    # A 15 s browser recording at about 2.5 Mbps is about 5 MB; anything far above that is refused.
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    # A recording of the protocol takes about 13 s, and the browser starts it right after creating the
    # session, so an upload sooner than this after creation was not made for the session. 0 turns the check off.
    MIN_SUBMIT_SECONDS: float = 12.0

    # Deepfake model (environment names kept from before; also readable from backend/.env)
    XCEPTION_CHECKPOINT: Optional[str] = Field(default=None, validation_alias="UNLEASH_XCEPTION_CHECKPOINT")
    XCEPTION_MODEL_NAME: str = Field(default="xception", validation_alias="UNLEASH_XCEPTION_MODEL_NAME")
    FAKE_THRESHOLD: float = Field(default=0.5, validation_alias="UNLEASH_FAKE_THRESHOLD")
    IMAGE_SIZE: int = Field(default=299, validation_alias="UNLEASH_IMAGE_SIZE")
    FAKE_CLASS_INDEX: int = Field(default=1, validation_alias="UNLEASH_FAKE_CLASS_INDEX")

    @field_validator("UPLOAD_TEMP_DIR")
    @classmethod
    def anchor_upload_dir(cls, v: str) -> str:
        path = Path(v)
        return str(path if path.is_absolute() else (_BACKEND_DIR / path).resolve())

    @field_validator("DATABASE_URL")
    @classmethod
    def anchor_sqlite_path(cls, v: str) -> str:
        prefix = "sqlite:///"
        if not v.startswith(prefix):
            return v
        path = Path(v[len(prefix):])
        return prefix + (path if path.is_absolute() else (_BACKEND_DIR / path).resolve()).as_posix()

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v

    @model_validator(mode="after")
    def refuse_weak_secret_outside_development(self) -> "Settings":
        if self.ENVIRONMENT != "development" and (
            self.SECRET_KEY == DEFAULT_SECRET_KEY or len(self.SECRET_KEY) < MIN_SECRET_KEY_LENGTH
        ):
            raise ValueError(
                f"SECRET_KEY must be set to a private value of at least {MIN_SECRET_KEY_LENGTH} characters "
                f"when ENVIRONMENT is '{self.ENVIRONMENT}' (e.g. openssl rand -hex 32). "
                "For local work copy .env.example to .env, which sets ENVIRONMENT=development."
            )
        return self

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
