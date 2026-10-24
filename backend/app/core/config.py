from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    PROJECT_NAME: str = "GNK Algo"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    SECRET_KEY: str = "development-only-change-before-deployment"
    COOKIE_SECURE: bool = False
    SESSION_MINUTES: int = 60
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    APP_BASE_URL: str = "http://localhost:3000"

    @model_validator(mode="after")
    def validate_production(self):
        if self.ENVIRONMENT == "production":
            if len(self.SECRET_KEY) < 40 or self.SECRET_KEY.startswith("development"):
                raise ValueError("Production requires a random SECRET_KEY of at least 40 characters")
            if not self.COOKIE_SECURE or any(not o.startswith("https://") for o in self.origins):
                raise ValueError("Production requires secure cookies and HTTPS origins")
            if not self.SMTP_HOST or not (self.SMTP_FROM or self.SMTP_USER):
                raise ValueError("Production requires SMTP_HOST and SMTP_FROM (or SMTP_USER) for account emails")
            if not self.APP_BASE_URL.startswith("https://"):
                raise ValueError("Production requires an HTTPS APP_BASE_URL")
        return self

    @property
    def origins(self):
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return self.DATABASE_URL or URL.create("postgresql+psycopg", username=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_SERVER, database=self.POSTGRES_DB).render_as_string(hide_password=False)

settings = Settings()
