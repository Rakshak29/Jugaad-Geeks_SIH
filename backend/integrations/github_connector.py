from urllib.parse import urlparse

from backend.integrations.evidence_adapter import build_adapter


def parse_github_url(repository_url: str) -> str:

    parsed = urlparse(repository_url)

    if parsed.netloc.lower() != "github.com":
        raise ValueError(
            "Invalid GitHub repository URL"
        )

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) != 2:
        raise ValueError(
            "Repository URL must look like "
            "https://github.com/owner/repository"
        )

    return f"{parts[0]}/{parts[1]}"


def fetch_github(repository_url: str):

    repo = parse_github_url(
        repository_url
    )

    adapter = build_adapter(repo)

    return list(adapter.fetch())