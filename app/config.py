from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    cassandra_contact_points: tuple[str, ...]
    cassandra_port: int
    cassandra_keyspace: str
    cassandra_connect_retries: int
    cassandra_retry_delay_seconds: float
    cassandra_connect_timeout: float
    cassandra_request_timeout: float
    cassandra_trace_enabled: bool
    cassandra_trace_sample_rate: float
    cassandra_trace_log_events: bool
    cassandra_trace_max_wait_seconds: float


@lru_cache
def get_settings() -> Settings:
    contact_points = tuple(
        part.strip()
        for part in os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
        if part.strip()
    )
    return Settings(
        cassandra_contact_points=contact_points or ("127.0.0.1",),
        cassandra_port=int(os.getenv("CASSANDRA_PORT", "9042")),
        cassandra_keyspace=os.getenv("CASSANDRA_KEYSPACE", "social_feed"),
        cassandra_connect_retries=int(os.getenv("CASSANDRA_CONNECT_RETRIES", "45")),
        cassandra_retry_delay_seconds=float(
            os.getenv("CASSANDRA_RETRY_DELAY_SECONDS", "2")
        ),
        cassandra_connect_timeout=float(os.getenv("CASSANDRA_CONNECT_TIMEOUT", "5")),
        cassandra_request_timeout=float(os.getenv("CASSANDRA_REQUEST_TIMEOUT", "10")),
        cassandra_trace_enabled=os.getenv("CASSANDRA_TRACE_ENABLED", "false").lower()
        == "true",
        cassandra_trace_sample_rate=float(
            os.getenv("CASSANDRA_TRACE_SAMPLE_RATE", "1.0")
        ),
        cassandra_trace_log_events=os.getenv(
            "CASSANDRA_TRACE_LOG_EVENTS", "false"
        ).lower()
        == "true",
        cassandra_trace_max_wait_seconds=float(
            os.getenv("CASSANDRA_TRACE_MAX_WAIT_SECONDS", "5")
        ),
    )
