"""Read and write AI-client JSON config files without ever corrupting them."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal, Mapping

ValueStyle = Literal["env", "keep", "literal"]
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    pass


class MissingEnvVar(ConfigError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object at the top level")
    return data


def write_json_atomic(path: Path, data: Mapping[str, Any], *, backup: bool = True) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if backup and path.exists():
        backup_path = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup_path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return backup_path


def render_value(value: str, style: ValueStyle) -> tuple[str, bool]:
    """Render a header value containing ${VAR} references for a client's config syntax."""
    if style == "keep":
        return value, False
    if style == "env":
        return _VAR.sub(lambda m: "${env:" + m.group(1) + "}", value), False
    names = _VAR.findall(value)
    missing = [n for n in names if n not in os.environ]
    if missing:
        raise MissingEnvVar(f"environment variable(s) not set: {', '.join(missing)}")
    return _VAR.sub(lambda m: os.environ[m.group(1)], value), bool(names)
