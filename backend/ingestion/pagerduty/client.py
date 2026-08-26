"""
PagerDuty REST API Client for Engineering Continuity.

Provides a clean, reusable client for interacting with the PagerDuty REST API v2
(https://api.pagerduty.com/) to retrieve services, incidents, custom details, and log entries.
"""

import os
import re
import json
import ssl
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


class PagerDutyClientError(Exception):
    """Base exception for PagerDuty REST API errors."""
    pass


class PagerDutyClient:
    """
    Reusable REST API client for PagerDuty Cloud v2 REST API.
    
    Uses REST API read tokens (Authorization: Token token=<TOKEN>) to query
    services, incidents, custom details, and activity logs with offset pagination.
    """

    def __init__(self, api_token: Optional[str] = None, base_url: str = "https://api.pagerduty.com"):
        """
        Initialize PagerDuty REST API Client.

        :param api_token: PagerDuty REST API User or Account API Token.
                          If None, reads from PAGERDUTY_REST_API_TOKEN or PAGERDUTY_API_KEY env vars.
        :param base_url: PagerDuty REST API base URL (default: https://api.pagerduty.com).
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token or os.environ.get("PAGERDUTY_REST_API_TOKEN") or os.environ.get("PAGERDUTY_API_KEY")
        
        # Note: Do not raise error in __init__ if token is missing so client can be instantiated in dry-run/mock contexts

    def _get_headers(self) -> Dict[str, str]:
        """Construct standard PagerDuty REST API v2 headers."""
        if not self.api_token:
            raise PagerDutyClientError(
                "Missing PagerDuty REST API Token. Set PAGERDUTY_REST_API_TOKEN or PAGERDUTY_API_KEY in environment."
            )
        return {
            "Authorization": f"Token token={self.api_token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json"
        }

    def _request(self, method: str, path: str, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute an authenticated HTTP request to PagerDuty REST API with certificate verification.

        :param method: HTTP method (GET, POST, etc.)
        :param path: API endpoint path (e.g. '/incidents')
        :param query_params: Optional dict of query parameters.
        :return: Parsed JSON response dictionary.
        """
        url = f"{self.base_url}{path}"
        if query_params:
            encoded_params = []
            for key, val in query_params.items():
                if isinstance(val, list):
                    for item in val:
                        encoded_params.append((f"{key}[]", str(item)))
                elif val is not None:
                    encoded_params.append((key, str(val)))
            if encoded_params:
                url = f"{url}?{urllib.parse.urlencode(encoded_params)}"

        headers = self._get_headers()
        req = urllib.request.Request(url, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, context=SSL_CONTEXT) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            raise PagerDutyClientError(
                f"PagerDuty REST API error (HTTP {e.code}) for {url}: {err_body or e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise PagerDutyClientError(f"Network error connecting to PagerDuty API ({url}): {e.reason}") from e

    @staticmethod
    def extract_service_id_from_url(url: str) -> Optional[str]:
        """
        Extract the PagerDuty Service ID (e.g. PK9U7OK) from a PagerDuty service URL.

        Supports formats like:
        - https://acmepay.pagerduty.com/service-directory/PK9U7OK/activity
        - https://acmepay.pagerduty.com/services/PK9U7OK
        - https://app.pagerduty.com/services/PK9U7OK
        """
        match = re.search(r"/(?:service-directory|services)/([A-Z0-9]+)", url)
        if match:
            return match.group(1)
        return None

    def get_service(self, service_id: str) -> Dict[str, Any]:
        """
        Retrieve details for a specific PagerDuty service by ID.

        :param service_id: PagerDuty Service ID (e.g. 'PK9U7OK')
        :return: Service object dictionary.
        """
        res = self._request("GET", f"/services/{service_id}")
        return res.get("service", {})

    def get_incidents(
        self,
        service_ids: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        urgencies: Optional[List[str]] = None,
        date_range: str = "all",
        include: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve incidents for given service IDs with automatic pagination support.

        :param service_ids: List of PagerDuty Service IDs (e.g. ['PK9U7OK'])
        :param statuses: Optional filter by status ['triggered', 'acknowledged', 'resolved']
        :param urgencies: Optional filter by urgency ['high', 'low']
        :param date_range: Date range filter (default: 'all')
        :param include: Optional include array (e.g. ['first_trigger_log_entries', 'services', 'assignees'])
        :param limit: Page size per request (max: 100).
        :return: Consolidated list of all incident dictionaries.
        """
        incidents = []
        offset = 0
        more = True

        if include is None:
            include = ["first_trigger_log_entries", "services", "assignees"]

        while more:
            params: Dict[str, Any] = {
                "limit": limit,
                "offset": offset,
                "date_range": date_range,
            }
            if service_ids:
                params["service_ids"] = service_ids
            if statuses:
                params["statuses"] = statuses
            if urgencies:
                params["urgencies"] = urgencies
            if include:
                params["include"] = include

            res = self._request("GET", "/incidents", query_params=params)
            page_incidents = res.get("incidents", [])
            incidents.extend(page_incidents)

            more = res.get("more", False)
            offset += len(page_incidents)

            # Safety breakout if limit returned zero records
            if not page_incidents:
                break

        return incidents

    def get_incident_details(self, incident_id: str) -> Dict[str, Any]:
        """
        Retrieve a single incident by ID.

        :param incident_id: PagerDuty Incident ID
        :return: Incident dictionary.
        """
        res = self._request("GET", f"/incidents/{incident_id}")
        return res.get("incident", {})

    def get_incident_log_entries(self, incident_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve log entries (audit activity stream) for a specific incident.

        :param incident_id: PagerDuty Incident ID
        :return: List of log entry dictionaries.
        """
        res = self._request("GET", f"/incidents/{incident_id}/log_entries")
        return res.get("log_entries", [])
