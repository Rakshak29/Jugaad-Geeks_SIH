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

# GitHub Integration Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Rakshak29/Jugaad-Geeks_SIH")

# Jira Integration Configuration
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://acmepay-engineering.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
