"""
Módulo especializado para logging RAW de dados da API (Devices/Playlists).

Fornece funções para registrar dados brutos da API em formato JSON Lines.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from django.utils.timezone import localtime
from .logging_config import get_logger, BASE_LOG_DIR


class APIRawLogger:
    """Gerenciador de logs RAW da API com formato JSON Lines."""

    def __init__(self):
        self.logger = get_logger(
            name="APIRaw",
            log_file=BASE_LOG_DIR / "Reseller" / "devices_raw.log",
            console_level=logging.WARNING,
            file_level=logging.DEBUG,
        )

    def log_collection_start(
        self,
        user: str,
        app_name: str,
        total_devices: int = 0
    ) -> None:
        """Registra início da coleta de devices."""
        event = {
            "timestamp": localtime().isoformat(),
            "event": "collection_start",
            "user": user,
            "app": app_name,
            "total_devices": total_devices
        }
        self.logger.debug(json.dumps(event, ensure_ascii=False))

    def log_device_raw(
        self,
        device_id: int,
        device_mac: str,
        device_name: str,
        raw_data: Dict[str, Any]
    ) -> None:
        """Registra device com dados RAW completos."""
        event = {
            "timestamp": localtime().isoformat(),
            "type": "device",
            "device_id": device_id,
            "device_mac": device_mac,
            "device_name": device_name,
            "raw_data": raw_data
        }
        self.logger.debug(json.dumps(event, ensure_ascii=False))

    def log_playlist_raw(
        self,
        device_id: int,
        playlist_id: int,
        playlist_name: str,
        raw_data: Dict[str, Any]
    ) -> None:
        """Registra playlist com dados RAW completos."""
        event = {
            "timestamp": localtime().isoformat(),
            "type": "playlist",
            "device_id": device_id,
            "playlist_id": playlist_id,
            "playlist_name": playlist_name,
            "raw_data": raw_data
        }
        self.logger.debug(json.dumps(event, ensure_ascii=False))

    def log_collection_end(
        self,
        user: str,
        app_name: str,
        status: str,
        duration_seconds: float,
        devices_processed: int,
        playlists_total: int,
        error: Optional[str] = None
    ) -> None:
        """Registra fim da coleta com resumo."""
        event = {
            "timestamp": localtime().isoformat(),
            "event": "collection_end",
            "user": user,
            "app": app_name,
            "status": status,
            "duration_seconds": round(duration_seconds, 2),
            "devices_processed": devices_processed,
            "playlists_total": playlists_total,
        }
        if error:
            event["error"] = error

        self.logger.info(json.dumps(event, ensure_ascii=False))


# Instância global
_api_raw_logger = None


def get_api_raw_logger() -> APIRawLogger:
    """Retorna instância singleton do APIRawLogger."""
    global _api_raw_logger
    if _api_raw_logger is None:
        _api_raw_logger = APIRawLogger()
    return _api_raw_logger
