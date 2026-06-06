from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv

PAYLOAD_MODES = {"raw", "redacted"}


class Settings:
    def __init__(self) -> None:
        load_dotenv()
        raw_upstream = os.getenv("UPSTREAM_OPENAI_BASE_URL", "https://api.minimax.io").rstrip("/")
        # Accept either `https://host` or the more common `https://host/v1` form so users
        # can copy-paste the same base URL they use everywhere else without hitting /v1/v1.
        if raw_upstream.endswith("/v1"):
            raw_upstream = raw_upstream[:-3]
        self.upstream_openai_base_url = raw_upstream
        self.data_dir = Path(os.getenv("AOH_DATA_DIR", "data"))
        self.database_path = Path(os.getenv("AOH_DATABASE_PATH", str(self.data_dir / "hub.sqlite3")))
        self.allow_raw_view = os.getenv("ALLOW_RAW_VIEW", "false").lower() in {"1", "true", "yes", "on"}
        payload_mode = os.getenv("AOH_PAYLOAD_MODE", "raw").strip().lower()
        self.payload_mode = payload_mode if payload_mode in PAYLOAD_MODES else "redacted"
        self.request_timeout = float(os.getenv("UPSTREAM_REQUEST_TIMEOUT", "120"))
        default_observation_dir = Path.home() / ".pi" / "observation"
        self.observation_dir = Path(os.getenv("AOH_OBSERVATION_DIR", str(default_observation_dir)))
        self.observation_tail_interval = float(os.getenv("AOH_OBSERVATION_TAIL_INTERVAL", "1.0"))
        self.observation_tail_enabled = os.getenv("AOH_OBSERVATION_TAIL_DISABLE", "").lower() not in {"1", "true", "yes"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
