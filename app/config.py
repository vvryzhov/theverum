from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "TheVerum"
    app_url: str = "http://localhost:8080"
    secret_key: str = "dev-secret-change-me"
    admin_email: str = "admin@theverum.ru"
    admin_password: str = "change-me-now"
    database_url: str = "sqlite:///./theverum.db"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "theverum-documents"
    public_minio_url: str = ""
    cookie_secure: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
