from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    output_dir: Path = field(default_factory=lambda: Path("~/devel/libs/").expanduser())
    port: int = 7890
    host: str = "127.0.0.1"
    trusted_hosts: list[str] = field(
        default_factory=lambda: ["github.com", "gitlab.com"]
    )
    deps_dev_cache_ttl: int = 24


def load_config() -> Config:
    """Load configuration from ~/.config/libsrc/config.yml, merging with defaults.

    If the config file doesn't exist, returns defaults silently.
    """
    config_path = Path("~/.config/libsrc/config.yml").expanduser()
    config = Config()

    if not config_path.is_file():
        return config

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return config

    if "output_dir" in data:
        config.output_dir = Path(data["output_dir"]).expanduser()
    if "port" in data:
        config.port = int(data["port"])
    if "host" in data:
        config.host = str(data["host"])
    if "trusted_hosts" in data:
        config.trusted_hosts = list(data["trusted_hosts"])
    if "deps_dev_cache_ttl" in data:
        config.deps_dev_cache_ttl = int(data["deps_dev_cache_ttl"])

    return config
