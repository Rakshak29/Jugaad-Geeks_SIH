import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


def get_database_url() -> str:
    """Build PostgreSQL database connection URL from environment variables."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "engineering_continuity")

    if host.startswith("/"):
        # Unix domain socket format
        return f"postgresql://{user}:{password}@/{db_name}?host={host}"
    
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"



DATABASE_URL = get_database_url()
