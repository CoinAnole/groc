from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from groc.errors import GrocError
from groc.models import DEFAULT_MODEL, DEFAULT_UPSTREAM_MODEL

DEFAULT_BACKEND_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_REFRESH_URL = "https://auth.openai.com/oauth/token"
DEFAULT_REASONING_EFFORT = "high"

LAUNCHER_CONFIG_TEMPLATE = """# Groc launcher settings. Uncomment only values you want to override.
# Environment variables such as GROC_BRIDGE_PORT take precedence over this file.

# bridge_host = "127.0.0.1"
# bridge_port = 11435
# bridge_log = "/tmp/groc-bridge.log"
# grok_bin = "grok"
# default_model = "gpt-5.6-sol"
# reasoning_effort = "high"
# auth_home = "~/.codex"
# codex_bin = "codex"
# repo_url = "https://github.com/matrixtsex/groc.git"
# update_dir = "~/.local/share/groc-src"
# upstream_model = "gpt-5.6-sol"
# backend_base_url = "https://chatgpt.com/backend-api/codex"
# refresh_url = "https://auth.openai.com/oauth/token"
# auto_login = true
# device_auth = false
# raw_stderr = false
# allow_untrusted_backend = false
"""


@dataclass(frozen=True)
class Settings:
    home: Path
    bridge_host: str
    bridge_port: int
    bridge_log: Path
    grok_bin: str
    default_model: str
    reasoning_effort: str
    auth_home: Path
    codex_bin: str
    repo_url: str
    update_dir: Path
    upstream_model: str
    backend_base_url: str
    refresh_url: str
    auto_login: bool
    device_auth: bool
    raw_stderr: bool
    allow_untrusted_backend: bool

    @property
    def auth_file(self) -> Path:
        return self.auth_home / "auth.json"

    @property
    def launcher_file(self) -> Path:
        return self.home / "groc.toml"

    @property
    def bridge_base_url(self) -> str:
        return f"http://{self.bridge_host}:{self.bridge_port}"

    @property
    def bridge_health_url(self) -> str:
        return f"{self.bridge_base_url}/health"

    @property
    def api_base_url(self) -> str:
        return f"{self.bridge_base_url}/v1"


DEFAULT_VALUES: dict[str, Any] = {
    "bridge_host": "127.0.0.1",
    "bridge_port": 11435,
    "bridge_log": "/tmp/groc-bridge.log",
    "grok_bin": "grok",
    "default_model": DEFAULT_MODEL,
    "reasoning_effort": DEFAULT_REASONING_EFFORT,
    "auth_home": "~/.codex",
    "codex_bin": "codex",
    "repo_url": "https://github.com/matrixtsex/groc.git",
    "update_dir": "~/.local/share/groc-src",
    "upstream_model": DEFAULT_UPSTREAM_MODEL,
    "backend_base_url": DEFAULT_BACKEND_BASE_URL,
    "refresh_url": DEFAULT_REFRESH_URL,
    "auto_login": True,
    "device_auth": False,
    "raw_stderr": False,
    "allow_untrusted_backend": False,
}

ENV_NAMES = {
    "bridge_host": "GROC_BRIDGE_HOST",
    "bridge_port": "GROC_BRIDGE_PORT",
    "bridge_log": "GROC_BRIDGE_LOG",
    "grok_bin": "GROC_GROK_BIN",
    "default_model": "GROC_MODEL",
    "reasoning_effort": "GROC_REASONING_EFFORT",
    "auth_home": "GROC_AUTH_HOME",
    "codex_bin": "GROC_CODEX_BIN",
    "repo_url": "GROC_REPO_URL",
    "update_dir": "GROC_UPDATE_DIR",
    "upstream_model": "GROC_UPSTREAM_MODEL",
    "backend_base_url": "GROC_BACKEND_BASE_URL",
    "refresh_url": "GROC_REFRESH_TOKEN_URL_OVERRIDE",
    "auto_login": "GROC_AUTO_LOGIN",
    "device_auth": "GROC_CODEX_DEVICE_AUTH",
    "raw_stderr": "GROC_RAW_STDERR",
    "allow_untrusted_backend": "GROC_ALLOW_UNTRUSTED_BACKEND",
}

PATH_KEYS = {"bridge_log", "auth_home", "update_dir"}
COMMAND_KEYS = {"grok_bin", "codex_bin"}
BOOL_KEYS = {"auto_login", "device_auth", "raw_stderr", "allow_untrusted_backend"}
STRING_KEYS = set(DEFAULT_VALUES) - PATH_KEYS - BOOL_KEYS - {"bridge_port"}


def env_flag_value(value: str) -> bool:
    return value not in {"", "0", "false", "False", "no", "NO"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else env_flag_value(value)


def _read_launcher_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GrocError(f"cannot read launcher config {path}: {exc}", 2) from exc
    unknown = sorted(set(values) - set(DEFAULT_VALUES))
    if unknown:
        raise GrocError(f"unknown setting(s) in {path}: {', '.join(unknown)}", 2)
    for key, value in values.items():
        if key in BOOL_KEYS and not isinstance(value, bool):
            raise GrocError(f"{path}: {key} must be a boolean", 2)
        if key == "bridge_port" and (isinstance(value, bool) or not isinstance(value, int)):
            raise GrocError(f"{path}: bridge_port must be an integer", 2)
        if key in STRING_KEYS | PATH_KEYS and not isinstance(value, str):
            raise GrocError(f"{path}: {key} must be a string", 2)
    return values


def _config_path(value: str, directory: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else directory / path


def _environment_value(key: str, raw: str) -> Any:
    if key in BOOL_KEYS:
        return env_flag_value(raw)
    if key == "bridge_port":
        try:
            return int(raw)
        except ValueError as exc:
            raise GrocError(f"{ENV_NAMES[key]} must be an integer", 2) from exc
    return raw


def settings_from_env() -> Settings:
    home = Path(os.environ.get("GROC_HOME", "~/.groc")).expanduser()
    launcher_file = home / "groc.toml"
    file_values = _read_launcher_file(launcher_file)
    values = {**DEFAULT_VALUES, **file_values}
    for key, env_name in ENV_NAMES.items():
        if env_name in os.environ:
            values[key] = _environment_value(key, os.environ[env_name])

    port = values["bridge_port"]
    if not 1 <= port <= 65535:
        port_source = ENV_NAMES["bridge_port"] if ENV_NAMES["bridge_port"] in os.environ else launcher_file
        raise GrocError(f"bridge_port must be between 1 and 65535 (from {port_source})", 2)

    for key in PATH_KEYS:
        raw = values[key]
        values[key] = _config_path(raw, home)

    for key in COMMAND_KEYS:
        raw = values[key]
        command_path = Path(raw).expanduser()
        if not command_path.is_absolute() and "/" in raw:
            command_path = home / command_path
        values[key] = str(command_path) if command_path != Path(raw) else raw

    backend_base_url = values["backend_base_url"].rstrip("/")
    return Settings(
        home=home,
        bridge_host=values["bridge_host"],
        bridge_port=port,
        bridge_log=values["bridge_log"],
        grok_bin=values["grok_bin"],
        default_model=values["default_model"],
        reasoning_effort=values["reasoning_effort"],
        auth_home=values["auth_home"],
        codex_bin=values["codex_bin"],
        repo_url=values["repo_url"],
        update_dir=values["update_dir"],
        upstream_model=values["upstream_model"],
        backend_base_url=backend_base_url,
        refresh_url=values["refresh_url"],
        auto_login=values["auto_login"],
        device_auth=values["device_auth"],
        raw_stderr=values["raw_stderr"],
        allow_untrusted_backend=values["allow_untrusted_backend"],
    )


def ensure_launcher_file(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(settings.launcher_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    except OSError as exc:
        raise GrocError(f"cannot create launcher config {settings.launcher_file}: {exc}", 2) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(LAUNCHER_CONFIG_TEMPLATE)


def validate_trusted_endpoints(settings: Settings) -> None:
    if settings.allow_untrusted_backend:
        return
    if settings.backend_base_url != DEFAULT_BACKEND_BASE_URL:
        raise ValueError(
            "GROC_BACKEND_BASE_URL is a dangerous override. "
            "Set GROC_ALLOW_UNTRUSTED_BACKEND=1 only if you trust the endpoint."
        )
    if settings.refresh_url != DEFAULT_REFRESH_URL:
        raise ValueError(
            "GROC_REFRESH_TOKEN_URL_OVERRIDE is a dangerous override. "
            "Set GROC_ALLOW_UNTRUSTED_BACKEND=1 only if you trust the endpoint."
        )
