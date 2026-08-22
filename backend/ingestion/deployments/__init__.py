"""
Deployment raw telemetry extractor module.
"""
from backend.ingestion.deployments.deployment_extractor import (
    extract_deployment_event,
    extract_deployment_events,
)

__all__ = [
    "extract_deployment_event",
    "extract_deployment_events",
]
