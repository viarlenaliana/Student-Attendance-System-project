import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # Flask configuration
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "group04-development-secret-key"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database configuration
    DATABASE_URL = os.getenv("DATABASE_URL")

    if DATABASE_URL:
        # Support TiDB Cloud / hosted MySQL
        database_url = DATABASE_URL.strip()

        if database_url.startswith("mysql://"):
            database_url = database_url.replace(
                "mysql://",
                "mysql+pymysql://",
                1
            )

        url = make_url(database_url)

        SQLALCHEMY_DATABASE_URI = url

        # TLS configuration for TiDB Cloud
        DATABASE_SSL_CA = os.getenv("DATABASE_SSL_CA")

        if DATABASE_SSL_CA:
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "ssl": {
                        "ca": DATABASE_SSL_CA
                    }
                },
                "pool_pre_ping": True
            }
        else:
            SQLALCHEMY_ENGINE_OPTIONS = {
                "pool_pre_ping": True
            }

    else:
        # Local MySQL Docker configuration
        MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
        MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
        MYSQL_USER = os.getenv("MYSQL_USER")
        MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
        MYSQL_DB = os.getenv("MYSQL_DB")
        MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

        if not all([
            MYSQL_USER,
            MYSQL_PASSWORD,
            MYSQL_DB
        ]):
            raise ValueError(
                "Missing MySQL configuration in .env"
            )

        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
            f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
            f"?charset={MYSQL_CHARSET}"
        )

        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True
        }