from urllib.parse import urlparse
from backend.integrations.github_adapter import GitHubAdapter


def parse_github_url(repository_url: str) -> str:
    cleaned = repository_url.strip()
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        cleaned = f"https://github.com/{cleaned}"

    parsed = urlparse(cleaned)

    if parsed.netloc.lower() not in ("github.com", "www.github.com"):
        raise ValueError(
            "Invalid GitHub repository URL"
        )

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) < 2:
        raise ValueError(
            "Repository URL must look like "
            "https://github.com/owner/repository"
        )

    return f"{parts[0]}/{parts[1]}"


def fetch_github(repository_url: str, token: str = None):
    repo = parse_github_url(repository_url)
    adapter = GitHubAdapter(repo=repo, token=token)
    return list(adapter.fetch())


fetch_github_raw_data = fetch_github