from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv

PAYLOAD_MODES = {"raw", "redacted"}


class Settings:
    def __init__(self) -> None:
        load_dotenv()
        self.upstream_openai_base_url = os.getenv("UPSTREAM_OPENAI_BASE_URL", "https://api.minimax.io/v1").rstrip("/")
        self.data_dir = Path(os.getenv("AOH_DATA_DIR", "data"))
        self.database_path = Path(os.getenv("AOH_DATABASE_PATH", str(self.data_dir / "hub.sqlite3")))
        self.allow_raw_view = os.getenv("ALLOW_RAW_VIEW", "false").lower() in {"1", "true", "yes", "on"}
        payload_mode = os.getenv("AOH_PAYLOAD_MODE", "raw").strip().lower()
        self.payload_mode = payload_mode if payload_mode in PAYLOAD_MODES else "redacted"
        self.request_timeout = float(os.getenv("UPSTREAM_REQUEST_TIMEOUT", "120"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
