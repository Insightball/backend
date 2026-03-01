from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "INSIGHTBALL API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # JWT — variable Render : SECRET_KEY
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_PRICE_COACH:    str = ""
    STRIPE_PRICE_CLUB_99:  str = ""   # Plan Club  — 99€/10 matchs
    STRIPE_PRICE_CLUB_139: str = ""   # Plan Club Pro — 139€/15 matchs

    # AWS S3
    AWS_ACCESS_KEY_ID:     str
    AWS_SECRET_ACCESS_KEY: str
    AWS_BUCKET_NAME:       str
    AWS_REGION:            str = "eu-west-3"

    # Resend
    RESEND_API_KEY:  str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # CORS
    FRONTEND_URL: str = "https://insightball.com"

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
