"""
Confluence Cloud REST API v2 client.

Only the read endpoints the sync needs:
    GET /wiki/api/v2/spaces            -- space key, name, description
    GET /wiki/api/v2/pages             -- page bodies in storage format
    GET /wiki/api/v2/pages/{id}/labels -- labels, the primary mapping signal

Auth is HTTP Basic with an Atlassian account email and an API token
(id.atlassian.com -> Security -> API tokens). Nothing here reads or writes
anything outside the RAG subsystem.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterator

import httpx

from backend.rag import config as cfg

logger = logging.getLogger("rag.confluence.client")

# Confluence returns 429 with a Retry-After header under load.
_MAX_RETRIES = 4
_DEFAULT_BACKOFF = 2.0


class ConfluenceError(RuntimeError):
    """Any non-recoverable failure talking to Confluence."""


class ConfluenceNotConfigured(ConfluenceError):
    """Credentials or base URL are missing."""


@dataclass
class ConfluenceSpace:
    id: str
    key: str
    name: str
    description: str = ""


@dataclass
class ConfluencePageData:
    id: str
    title: str
    space_id: str
    parent_id: str | None
    version: int
    body_storage: str
    webui_path: str
    created_at: str | None = None
    labels: list[str] = field(default_factory=list)


class ConfluenceClient:
    """Thin, synchronous, read-only Confluence Cloud client."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (base_url if base_url is not None else cfg.CONFLUENCE_BASE_URL).rstrip("/")
        self.email = email if email is not None else cfg.CONFLUENCE_EMAIL
        self.api_token = api_token if api_token is not None else cfg.CONFLUENCE_API_TOKEN
        self.timeout = timeout if timeout is not None else cfg.CONFLUENCE_TIMEOUT

        # Refuse before making any request. A placeholder value looks
        # configured and produces an HTTP 401, which reads as "bad token" and
        # sends the reader looking in the wrong place.
        problem = cfg.confluence_config_problem()
        if problem:
            raise ConfluenceNotConfigured(problem)

        if not (self.base_url and self.email and self.api_token):
            raise ConfluenceNotConfigured(
                "Confluence is not configured. Set CONFLUENCE_BASE_URL, "
                "CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN in your .env file."
            )

        # `_links.next` is site-root-relative and already carries the /wiki
        # prefix, so joins are done against the site root, not the wiki root.
        if self.base_url.endswith("/wiki"):
            self.site_root = self.base_url[: -len("/wiki")]
        else:
            self.site_root = self.base_url

        self._client = httpx.Client(
            auth=(self.email, self.api_token),
            timeout=self.timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ConfluenceClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- HTTP ---------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> dict:
        """GET with retry on 429 / 5xx. `url` may be absolute or site-relative."""
        full = url if url.startswith("http") else self.site_root + url

        last_error = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.get(full, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                delay = _DEFAULT_BACKOFF * (2 ** attempt)
                logger.warning("confluence request failed (%s), retrying in %.1fs", exc, delay)
                time.sleep(delay)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in (401, 403):
                hints = [
                    "Confluence rejected the request (HTTP %s) for %s." % (resp.status_code, full),
                    "  - 401 usually means CONFLUENCE_EMAIL or CONFLUENCE_API_TOKEN is wrong,",
                    "    or CONFLUENCE_BASE_URL points at a site that is not yours.",
                    "  - 403 usually means the credentials are valid but the account cannot",
                    "    read that space.",
                    "Confirm the base URL opens in a browser while signed in as that account,",
                    "and that the token has not been revoked.",
                ]
                raise ConfluenceError("\n".join(hints))

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = _DEFAULT_BACKOFF * (2 ** attempt)
                logger.warning("confluence %s on %s, retrying in %.1fs", resp.status_code, full, delay)
                time.sleep(delay)
                last_error = ConfluenceError("HTTP %s from %s" % (resp.status_code, full))
                continue

            raise ConfluenceError("HTTP %s from %s: %s" % (resp.status_code, full, resp.text[:300]))

        raise ConfluenceError("Gave up on %s after %s attempts: %s" % (full, _MAX_RETRIES, last_error))

    def _paginate(self, path: str, params: dict) -> Iterator[dict]:
        """Walk a cursor-paginated v2 collection, yielding each result object."""
        url = self.base_url + path
        next_params = dict(params)

        while url:
            payload = self._get(url, params=next_params)
            for item in payload.get("results", []):
                yield item

            links = payload.get("_links") or {}
            next_link = links.get("next")
            if not next_link:
                break
            # The next link already carries the cursor in its query string.
            url = next_link
            next_params = None

    # -- endpoints ----------------------------------------------------------

    def iter_spaces(self) -> Iterator[ConfluenceSpace]:
        """All spaces the token can read."""
        params = {"limit": cfg.CONFLUENCE_PAGE_LIMIT, "description-format": "plain"}
        for raw in self._paginate("/api/v2/spaces", params):
            description = ""
            desc_obj = raw.get("description") or {}
            plain = desc_obj.get("plain") or {}
            if isinstance(plain, dict):
                description = plain.get("value") or ""
            yield ConfluenceSpace(
                id=str(raw.get("id", "")),
                key=raw.get("key", ""),
                name=raw.get("name", ""),
                description=description,
            )

    def iter_pages(self, space_ids: list[str] | None = None) -> Iterator[ConfluencePageData]:
        """
        All current pages, with bodies in storage format.

        Labels are fetched per page (one extra request each) -- v2 has no bulk
        page->label endpoint. On a wiki large enough for that to hurt, narrow
        the sync with CONFLUENCE_SPACE_KEYS.
        """
        params = {
            "limit": cfg.CONFLUENCE_PAGE_LIMIT,
            "body-format": "storage",
            "status": "current",
        }
        wanted = {str(s) for s in space_ids} if space_ids else None
        if wanted:
            params["space-id"] = ",".join(sorted(wanted))

        for raw in self._paginate("/api/v2/pages", params):
            page_id = str(raw.get("id", ""))
            if not page_id:
                continue

            # Belt and braces on the server-side space filter. If a deployment
            # ignores or differently serializes `space-id`, filtering here means
            # the sync still honours CONFLUENCE_SPACE_KEYS rather than silently
            # indexing the entire wiki.
            if wanted and str(raw.get("spaceId", "")) not in wanted:
                continue

            body_obj = (raw.get("body") or {}).get("storage") or {}
            body = body_obj.get("value") or ""

            version_obj = raw.get("version") or {}
            version = version_obj.get("number") or 1

            links = raw.get("_links") or {}
            webui = links.get("webui") or ""

            parent_id = raw.get("parentId")

            yield ConfluencePageData(
                id=page_id,
                title=raw.get("title") or "(untitled)",
                space_id=str(raw.get("spaceId", "")),
                parent_id=str(parent_id) if parent_id else None,
                version=int(version),
                body_storage=body,
                webui_path=webui,
                created_at=raw.get("createdAt"),
                labels=self.get_page_labels(page_id),
            )

    def get_page_labels(self, page_id: str) -> list[str]:
        """Label names for one page. A label failure never aborts a sync."""
        try:
            params = {"limit": 100}
            path = "/api/v2/pages/%s/labels" % page_id
            return [
                raw.get("name", "")
                for raw in self._paginate(path, params)
                if raw.get("name")
            ]
        except ConfluenceError as exc:
            logger.warning("could not read labels for page %s: %s", page_id, exc)
            return []

    def page_url(self, webui_path: str) -> str:
        """
        Absolute browser URL for a page, from its `_links.webui` path.

        webui is relative to the wiki root, so it joins to base_url (which
        ends in /wiki) -- not to site_root, which is only correct for the
        `_links.next` pagination URLs.
        """
        if not webui_path:
            return self.base_url
        if webui_path.startswith("http"):
            return webui_path
        base = self.base_url if self.base_url.endswith("/wiki") else self.base_url + "/wiki"
        return base + webui_path
