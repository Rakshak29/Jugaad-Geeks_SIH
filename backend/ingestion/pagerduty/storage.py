"""
Raw PagerDuty Ingestion Storage Module.

Saves raw PagerDuty API responses as JSON to data/raw/pagerduty/incidents.json
using atomic file replacement and isolated per-request overwriting.
"""

import os
import json
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

RAW_PAGERDUTY_DIR = "data/raw/pagerduty"
RAW_PAGERDUTY_FILE = os.path.join(RAW_PAGERDUTY_DIR, "incidents.json")


def save_raw_pagerduty_incidents(
    service_id: str,
    pagerduty_url: str,
    incidents: List[Dict[str, Any]],
    output_filepath: str = RAW_PAGERDUTY_FILE
) -> str:
    """
    Save raw PagerDuty incidents to JSON file using atomic write.

    Overwrites existing raw file completely to maintain independent ingestion datasets per run.

    :param service_id: Extracted PagerDuty Service ID (e.g. 'PK9U7OK')
    :param pagerduty_url: Original submitted web URL
    :param incidents: Raw list of incident dictionaries from PagerDuty API
    :param output_filepath: Target raw JSON file path
    :return: Absolute path to written raw JSON file
    """
    target_dir = os.path.dirname(output_filepath)
    os.makedirs(target_dir, exist_ok=True)

    raw_payload = {
        "source_url": pagerduty_url,
        "service_id": service_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "total_incidents": len(incidents),
        "incidents": incidents
    }

    # Write atomically to temp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix="pagerduty_raw_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(raw_payload, f, indent=2)
        os.replace(tmp_path, output_filepath)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise RuntimeError(f"Failed to write raw PagerDuty storage file {output_filepath}: {e}") from e

    return os.path.abspath(output_filepath)


def get_raw_pagerduty_incidents(filepath: str = RAW_PAGERDUTY_FILE) -> Optional[Dict[str, Any]]:
    """
    Read the current raw PagerDuty ingestion JSON file if present.
    
    :param filepath: Path to raw JSON file.
    :return: Parsed JSON payload or None if file does not exist.
    """
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
