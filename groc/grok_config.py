from __future__ import annotations

import json
import os
import stat
import tempfile
import tomllib
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from groc.errors import GrocError
from groc.models import MODEL_CATALOG
from groc.settings import Settings

BEGIN_MANAGED_MODELS = "# BEGIN GROC-MANAGED MODELS"
END_MANAGED_MODELS = "# END GROC-MANAGED MODELS"
LEGACY_MODEL_IDS = {
    "gpt-5.2",
    "gpt-5.3",
    "gpt-5.3-spark",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "grok-build",
}


class _TomlStringState(Enum):
    NORMAL = auto()
    BASIC = auto()
    LITERAL = auto()
    MULTILINE_BASIC = auto()
    MULTILINE_LITERAL = auto()


class _TomlLineKind(Enum):
    BLANK = auto()
    COMMENT = auto()
    TABLE_HEADER = auto()
    CONTENT = auto()


@dataclass(frozen=True)
class _TomlLine:
    text: str
    start: int
    end: int
    kind: _TomlLineKind
    top_level: bool
    comment: str | None = None
    table_header: str | None = None


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_managed_models(settings: Settings) -> str:
    lines = [BEGIN_MANAGED_MODELS]
    for model in MODEL_CATALOG:
        configured_model = settings.upstream_model if model.id == "grok-build" else model.id
        lines.extend(
            [
                f"[model.{toml_string(model.id)}]",
                f"model = {toml_string(configured_model)}",
                f"base_url = {toml_string(settings.api_base_url)}",
                f"name = {toml_string(model.name + ' (ChatGPT OAuth)')}",
                'api_key = "local"',
                'api_backend = "responses"',
                f"supports_reasoning_effort = {str(model.supports_reasoning_effort).lower()}",
                f"context_window = {model.context_window}",
                "",
            ]
        )
    lines.append(END_MANAGED_MODELS)
    return "\n".join(lines)


def render_grok_config(settings: Settings) -> str:
    return "\n".join(
        [
            "[models]",
            f"default = {toml_string(settings.default_model)}",
            "",
            "[subagents]",
            "enabled = true",
            "",
            "[features]",
            "telemetry = false",
            "lsp_tools = false",
            "",
            "[memory]",
            "enabled = false",
            "",
            render_managed_models(settings),
            "",
            "[ui]",
            "max_thoughts_width = 120",
            f"fork_secondary_model = {toml_string(settings.default_model)}",
            "yolo = false",
            "compact_mode = false",
            "",
        ]
    )


def _line_body(line: str) -> str:
    if line.endswith("\n"):
        line = line[:-1]
        if line.endswith("\r"):
            line = line[:-1]
    return line


def _physical_lines(text: str) -> list[str]:
    lines: list[str] = []
    start = 0
    while start < len(text):
        newline = text.find("\n", start)
        if newline == -1:
            lines.append(text[start:])
            break
        lines.append(text[start : newline + 1])
        start = newline + 1
    return lines


def _scan_toml_lines(text: str) -> list[_TomlLine]:
    scanned: list[_TomlLine] = []
    state = _TomlStringState.NORMAL
    syntax_nesting = 0
    offset = 0

    for line in _physical_lines(text):
        body = _line_body(line)
        starts_outside_string = state is _TomlStringState.NORMAL
        starts_at_top_level = starts_outside_string and syntax_nesting == 0
        first_syntax_character: str | None = None
        comment_index: int | None = None
        index = 0

        while index < len(body):
            character = body[index]

            if state is _TomlStringState.NORMAL:
                if character in " \t":
                    index += 1
                    continue
                if character == "#":
                    comment_index = index
                    break
                if first_syntax_character is None:
                    first_syntax_character = character
                if character == '"':
                    if body.startswith('"""', index):
                        state = _TomlStringState.MULTILINE_BASIC
                        index += 3
                    else:
                        state = _TomlStringState.BASIC
                        index += 1
                    continue
                if character == "'":
                    if body.startswith("'''", index):
                        state = _TomlStringState.MULTILINE_LITERAL
                        index += 3
                    else:
                        state = _TomlStringState.LITERAL
                        index += 1
                    continue
                if character in "[{":
                    syntax_nesting += 1
                elif character in "]}":
                    syntax_nesting -= 1
                index += 1
                continue

            if state is _TomlStringState.BASIC:
                if character == "\\":
                    index += 2
                elif character == '"':
                    state = _TomlStringState.NORMAL
                    index += 1
                else:
                    index += 1
                continue

            if state is _TomlStringState.LITERAL:
                if character == "'":
                    state = _TomlStringState.NORMAL
                index += 1
                continue

            delimiter = '"' if state is _TomlStringState.MULTILINE_BASIC else "'"
            if state is _TomlStringState.MULTILINE_BASIC and character == "\\":
                index += 2
                continue
            if character != delimiter:
                index += 1
                continue

            quote_run_end = index
            while quote_run_end < len(body) and body[quote_run_end] == delimiter:
                quote_run_end += 1
            if quote_run_end - index >= 3:
                state = _TomlStringState.NORMAL
            index = quote_run_end

        if not starts_outside_string:
            kind = _TomlLineKind.CONTENT
        elif first_syntax_character is None:
            kind = _TomlLineKind.COMMENT if comment_index is not None else _TomlLineKind.BLANK
        elif starts_at_top_level and first_syntax_character == "[":
            kind = _TomlLineKind.TABLE_HEADER
        else:
            kind = _TomlLineKind.CONTENT

        comment = body[comment_index:] if kind is _TomlLineKind.COMMENT else None
        header_end = comment_index if comment_index is not None else len(body)
        table_header = body[:header_end].rstrip(" \t") if kind is _TomlLineKind.TABLE_HEADER else None
        scanned.append(
            _TomlLine(
                text=line,
                start=offset,
                end=offset + len(line),
                kind=kind,
                top_level=starts_at_top_level,
                comment=comment,
                table_header=table_header,
            )
        )
        offset += len(line)

    return scanned


def _managed_marker_lines(lines: list[_TomlLine]) -> tuple[list[_TomlLine], list[_TomlLine]]:
    begin_lines: list[_TomlLine] = []
    end_lines: list[_TomlLine] = []

    for line in lines:
        if line.comment is None:
            continue
        comment = line.comment.rstrip(" \t")
        for marker, matches in (
            (BEGIN_MANAGED_MODELS, begin_lines),
            (END_MANAGED_MODELS, end_lines),
        ):
            if comment == marker:
                matches.append(line)
            elif comment.startswith(marker):
                raise GrocError(
                    f"config.toml has malformed Groc managed-model marker: {comment}",
                    2,
                )

    return begin_lines, end_lines


def _replace_managed_block(
    text: str,
    settings: Settings,
    begin_lines: list[_TomlLine],
    end_lines: list[_TomlLine],
) -> str:
    if len(begin_lines) != 1 or len(end_lines) != 1:
        raise GrocError(
            "config.toml has missing or duplicate Groc managed-model markers; "
            "restore exactly one BEGIN and END marker before retrying",
            2,
        )
    begin_line = begin_lines[0]
    end_line = end_lines[0]
    if begin_line.start >= end_line.end:
        raise GrocError("config.toml has reversed Groc managed-model markers", 2)
    replacement = render_managed_models(settings) + "\n"
    return text[: begin_line.start] + replacement + text[end_line.end :]


def _parse_table_path(header: str) -> list[str]:
    stripped = header.strip()
    key_expression = stripped[2:-2] if stripped.startswith("[[") and stripped.endswith("]]") else stripped[1:-1]

    keys: list[str] = []
    index = 0
    while index < len(key_expression):
        while index < len(key_expression) and key_expression[index] in " \t":
            index += 1
        key_start = index
        if key_expression[index] in "\"'":
            quote = key_expression[index]
            index += 1
            while index < len(key_expression):
                if quote == '"' and key_expression[index] == "\\":
                    index += 2
                    continue
                if key_expression[index] == quote:
                    index += 1
                    break
                index += 1
            token = key_expression[key_start:index]
            keys.append(tomllib.loads(f"key = {token}")["key"])
        else:
            while index < len(key_expression) and key_expression[index] not in ". \t":
                index += 1
            keys.append(key_expression[key_start:index])
        while index < len(key_expression) and key_expression[index] in " \t":
            index += 1
        if index < len(key_expression):
            index += 1

    return keys


def _owned_model_header(header: str) -> bool:
    path = _parse_table_path(header)
    return len(path) >= 2 and path[0] == "model" and path[1] in LEGACY_MODEL_IDS


def _migrate_legacy_models(lines: list[_TomlLine], settings: Settings) -> str:
    preserved: list[str] = []
    insertion_index: int | None = None
    skipping_owned_table = False

    for line in lines:
        if line.table_header is not None:
            if _owned_model_header(line.table_header):
                if insertion_index is None:
                    insertion_index = len(preserved)
                skipping_owned_table = True
                continue
            skipping_owned_table = False
        if not skipping_owned_table or (line.top_level and line.kind in {_TomlLineKind.BLANK, _TomlLineKind.COMMENT}):
            preserved.append(line.text)

    block = render_managed_models(settings) + "\n"
    if insertion_index is not None:
        preserved.insert(insertion_index, block)
        return "".join(preserved)

    migrated = "".join(preserved)
    if migrated and not migrated.endswith("\n"):
        migrated += "\n"
    if migrated and not migrated.endswith("\n\n"):
        migrated += "\n"
    return migrated + block


def reconcile_grok_config(text: str, settings: Settings) -> str:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise GrocError(f"config.toml is not valid TOML; refusing to overwrite: {exc}", 2) from exc

    lines = _scan_toml_lines(text)
    begin_lines, end_lines = _managed_marker_lines(lines)
    if begin_lines or end_lines:
        candidate = _replace_managed_block(text, settings, begin_lines, end_lines)
    else:
        candidate = _migrate_legacy_models(lines, settings)

    try:
        tomllib.loads(candidate)
    except tomllib.TOMLDecodeError as exc:
        raise GrocError(f"generated config.toml is not valid TOML; original left unchanged: {exc}") from exc
    return candidate


def _atomic_write(path: Path, content: str, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        with suppress(FileNotFoundError):
            temporary_path.unlink()


def write_grok_config(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    configured_path = settings.home / "config.toml"
    path = configured_path.resolve(strict=False) if configured_path.is_symlink() else configured_path
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        rendered = render_grok_config(settings)
        try:
            tomllib.loads(rendered)
        except tomllib.TOMLDecodeError as exc:
            raise GrocError(f"generated config.toml is not valid TOML; file not created: {exc}") from exc
        _atomic_write(path, rendered, 0o600)
        return

    try:
        original = path.read_text(encoding="utf-8")
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise GrocError(f"cannot read Grok config {path}: {exc}", 2) from exc
    reconciled = reconcile_grok_config(original, settings)
    if reconciled != original:
        _atomic_write(path, reconciled, mode)
