"""Application settings loaded from environment variables (.env in local dev)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Brightloop Subscriptions"
    environment: str = "development"

    # Database
    database_url: str = "sqlite:///./dev.db"

    # Auth
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 60
    admin_email: str | None = None
    admin_password: str | None = None

    # App / CORS
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    default_currency: str = "INR"
    billing_tz: str = "Asia/Kolkata"

    # Mailer: "log" prints reset links to logs (demo mode), "smtp" sends real email
    mailer_mode: str = "log"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "no-reply@brightloop.local"

    # Billing engine
    stale_run_minutes: int = 15
    max_catchup_periods: int = 366
    allow_overpayment: bool = False

    # Odoo — disabled until organizers confirm access (#15)
    odoo_enabled: bool = False
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_user: str = ""
    odoo_api_key: str = ""
    odoo_protocol: str = "auto"  # auto | json2 | jsonrpc | xmlrpc

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
