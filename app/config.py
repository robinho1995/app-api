from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "MBA DevOps SRE API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    DATABASE_URL: Optional[str] = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "mbauser"
    POSTGRES_PASSWORD: str = "mbapass"
    POSTGRES_DB: str = "mbaapi"

    REDIS_URL: Optional[str] = None
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    LOG_LEVEL: str = "INFO"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if "+asyncpg" not in url:
                url = url.replace("postgresql://", "postgresql+asyncpg://")
            return url
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            url = url.replace("+asyncpg", "")
            return url
        return (
            f"postgresql://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL_COMPUTED(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()