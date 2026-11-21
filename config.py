import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    dotenv_path=BASE_DIR / ".env",
    override=False
)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    # Database configuration
    DATABASE_TYPE = os.getenv("DATABASE_TYPE", "mysql")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DB = os.getenv("MYSQL_DB")
    MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

    if not all([MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB]):
        raise ValueError("Missing MySQL configuration in .env")

    SQLALCHEMY_DATABASE_URI = URL.create(
        drivername="mysql+pymysql",
        username=MYSQL_USER,
        password=MYSQL_PASSWORD,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        database=MYSQL_DB,
        query={"charset": MYSQL_CHARSET}
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False