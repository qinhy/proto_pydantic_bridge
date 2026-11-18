"""Domain validation and detection processing service."""
from .processing import InvalidDetection, process_detection

__all__ = ["InvalidDetection", "process_detection"]
