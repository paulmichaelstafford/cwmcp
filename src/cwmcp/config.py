# src/cwmcp/config.py
from dataclasses import dataclass
from pathlib import Path

CWBE_URL = "https://be.collapsingwave.com"
DEFAULT_CONFIG_PATH = str(Path.home() / ".cwmcp" / "config.properties")
REQUIRED_FIELDS = ["cwbe_user", "cwbe_password", "content_path"]


class ConfigError(Exception):
    pass


@dataclass
class Config:
    cwbe_user: str
    cwbe_password: str
    content_path: str
    elevenlabs_api_key: str = ""
    cwbe_url: str = CWBE_URL
    cwtts_url: str = "http://localhost:8100"


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    props = {}
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()

    for field in REQUIRED_FIELDS:
        if field not in props:
            raise ConfigError(f"Missing required config field: {field}")

    return Config(
        cwbe_user=props["cwbe_user"],
        cwbe_password=props["cwbe_password"],
        content_path=props["content_path"],
        elevenlabs_api_key=props.get("elevenlabs_api_key", ""),
        cwtts_url=props.get("cwtts_url", "http://localhost:8100"),
    )
