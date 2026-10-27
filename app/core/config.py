from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths
BACKEND_ROOT = Path(__file__).resolve().parents[2]   # .../backend
APP_ROOT = BACKEND_ROOT.parent                       # .../caregiver-system
DATA_DIR = (APP_ROOT / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = DATA_DIR / "caregiver.db"

def _norm_path(p: Path | str) -> str:
    return str(p).replace("\\", "/")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # ----- App -----
    APP_NAME: str = "Caregiver System"
    ENV: str = "local"
    APP_ENV: str | None = None

    # ----- Timezone -----
    TIMEZONE: str = "America/New_York"

    # ----- Database -----
    DATABASE_PATH: str | None = None
    SQLALCHEMY_DATABASE_URI: str | None = None
    DATABASE_URL: str | None = None

    # ----- Security (new names) -----
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720

    # ----- HTTP / API surface -----
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    CONTACT_INQUIRY_EMAIL: str = "angelsathomeal@gmail.com"
    ENABLE_DOCS: bool = True
    ENABLE_REDOC: bool = True
    ENABLE_OPENAPI: bool = True
    DOCS_ALLOWED_IPS: str = ""
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 10

    # ----- Compatibility aliases (legacy names some modules may use) -----
    SECRET_KEY: str | None = None
    ALGORITHM: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int | None = None

    @property
    def is_production(self) -> bool:
        return (self.ENV or "").strip().lower() in {"prod", "production"}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in (self.CORS_ALLOW_ORIGINS or "").split(",") if o.strip()]

    @property
    def docs_allowed_ips(self) -> set[str]:
        return {ip.strip() for ip in (self.DOCS_ALLOWED_IPS or "").split(",") if ip.strip()}

    def model_post_init(self, __context):
        if self.APP_ENV and not self.ENV:
            self.ENV = self.APP_ENV

        # Defaults for DB if not set by .env
        if not self.DATABASE_PATH:
            self.DATABASE_PATH = _norm_path(DEFAULT_DB_PATH)
        if self.DATABASE_URL and not self.SQLALCHEMY_DATABASE_URI:
            self.SQLALCHEMY_DATABASE_URI = self.DATABASE_URL
        if not self.SQLALCHEMY_DATABASE_URI:
            self.SQLALCHEMY_DATABASE_URI = f"sqlite:///{_norm_path(self.DATABASE_PATH)}"

        # Back-compat: if legacy names missing, mirror from JWT_* names
        if not self.SECRET_KEY:
            self.SECRET_KEY = self.JWT_SECRET
        if not self.ALGORITHM:
            self.ALGORITHM = self.JWT_ALG
        if self.ACCESS_TOKEN_EXPIRE_MINUTES is None:
            self.ACCESS_TOKEN_EXPIRE_MINUTES = self.JWT_EXPIRE_MINUTES

        # Also mirror the other way if someone sets only legacy names in .env
        # (keeps everything consistent)
        if self.SECRET_KEY and not self.JWT_SECRET:
            self.JWT_SECRET = self.SECRET_KEY
        if self.ALGORITHM and not self.JWT_ALG:
            self.JWT_ALG = self.ALGORITHM
        if self.ACCESS_TOKEN_EXPIRE_MINUTES is not None and not self.JWT_EXPIRE_MINUTES:
            self.JWT_EXPIRE_MINUTES = self.ACCESS_TOKEN_EXPIRE_MINUTES

        # Production safety defaults.
        if self.is_production:
            self.ENABLE_DOCS = False
            self.ENABLE_REDOC = False
            self.ENABLE_OPENAPI = False

            if self.JWT_SECRET == "dev-secret-change-me":
                raise ValueError("JWT_SECRET must be set to a strong value in production")

settings = Settings()
