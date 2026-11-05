"""Shared X/Y/Z axis definitions and value parsing.

Used by the Tkinter tool (validation and labels) and by the bridge (actual
generation).  No Tk or Pillow dependency.
"""

from __future__ import annotations

import csv
import math
import re
from io import StringIO
from typing import Any

AXIS_IDS = ("x", "y", "z")

AXIS_TYPES: list[dict[str, str]] = [
    {"id": "none", "label": "Aucun", "kind": "none"},
    {"id": "sampler", "label": "Sampler", "kind": "choice"},
    {"id": "scheduler", "label": "Scheduler", "kind": "choice"},
    {"id": "steps", "label": "Steps", "kind": "int"},
    {"id": "denoise", "label": "Denoise", "kind": "float"},
    {"id": "lora", "label": "LoRA", "kind": "float"},
    {"id": "cfg", "label": "CFG scale", "kind": "float"},
    {"id": "prompt_sr", "label": "Prompt S/R", "kind": "sr"},
    {"id": "negative_sr", "label": "Negative prompt S/R", "kind": "sr"},
]
AXIS_TYPE_BY_ID = {item["id"]: item for item in AXIS_TYPES}

RE_RANGE_INT = re.compile(
    r"\s*([+-]?\s*\d+)\s*-\s*([+-]?\s*\d+)(?:\s*\(([+-]\d+)\s*\))?\s*"
)
RE_RANGE_INT_COUNT = re.compile(
    r"\s*([+-]?\s*\d+)\s*-\s*([+-]?\s*\d+)(?:\s*\[(\d+)\s*])?\s*"
)
RE_RANGE_FLOAT = re.compile(
    r"\s*([+-]?\s*\d+(?:\.\d*)?)\s*-\s*([+-]?\s*\d+(?:\.\d*)?)"
    r"(?:\s*\(([+-]\d+(?:\.\d*)?)\s*\))?\s*"
)
RE_RANGE_FLOAT_COUNT = re.compile(
    r"\s*([+-]?\s*\d+(?:\.\d*)?)\s*-\s*([+-]?\s*\d+(?:\.\d*)?)"
    r"(?:\s*\[(\d+)\s*])?\s*"
)


def type_info(type_id: str) -> dict[str, str]:
    return AXIS_TYPE_BY_ID.get(str(type_id or "none"), AXIS_TYPE_BY_ID["none"])


def parse_csv_values(raw: str) -> list[str]:
    """Parse comma-separated values, supporting quoted fields with commas."""
    text = str(raw or "")
    if not text.strip():
        return []
    reader = csv.reader(StringIO(text), skipinitialspace=True)
    values: list[str] = []
    for row in reader:
        for item in row:
            values.append(str(item).strip())
    return values


def _int_range(value: str) -> list[int] | None:
    match = RE_RANGE_INT.fullmatch(value)
    if match:
        start = int(match.group(1).replace(" ", ""))
        end = int(match.group(2).replace(" ", ""))
        step = int(match.group(3)) if match.group(3) is not None else 1
        if step == 0:
            raise ValueError(f"pas nul dans la plage {value!r}")
        if step > 0:
            return list(range(start, end + 1, step))
        return list(range(start, end - 1, step))
    match = RE_RANGE_INT_COUNT.fullmatch(value)
    if match:
        start = int(match.group(1).replace(" ", ""))
        end = int(match.group(2).replace(" ", ""))
        count = int(match.group(3)) if match.group(3) is not None else 1
        if count <= 0:
            raise ValueError(f"nombre de valeurs invalide dans {value!r}")
        if count == 1:
            return [start]
        return [int(round(start + (end - start) * index / (count - 1))) for index in range(count)]
    return None


def _float_range(value: str) -> list[float] | None:
    match = RE_RANGE_FLOAT.fullmatch(value)
    if match:
        start = float(match.group(1).replace(" ", ""))
        end = float(match.group(2).replace(" ", ""))
        step = float(match.group(3)) if match.group(3) is not None else 1.0
        if step == 0:
            raise ValueError(f"pas nul dans la plage {value!r}")
        values: list[float] = []
        current = start
        if step > 0:
            while current <= end + 1e-9:
                values.append(round(current, 8))
                current += step
        else:
            while current >= end - 1e-9:
                values.append(round(current, 8))
                current += step
        return values
    match = RE_RANGE_FLOAT_COUNT.fullmatch(value)
    if match:
        start = float(match.group(1).replace(" ", ""))
        end = float(match.group(2).replace(" ", ""))
        count = int(match.group(3)) if match.group(3) is not None else 1
        if count <= 0:
            raise ValueError(f"nombre de valeurs invalide dans {value!r}")
        if count == 1:
            return [start]
        return [
            round(start + (end - start) * index / (count - 1), 8)
            for index in range(count)
        ]
    return None


def parse_values(raw: str, kind: str) -> list[Any]:
    """Parse an axis value string according to its kind."""
    if kind in {"int", "float"}:
        values: list[Any] = []
        for item in parse_csv_values(raw):
            if not item:
                continue
            if kind == "int":
                expanded = _int_range(item)
                if expanded is None:
                    expanded = [int(item.replace(" ", ""))]
            else:
                expanded = _float_range(item)
                if expanded is None:
                    expanded = [float(item.replace(" ", ""))]
            values.extend(expanded)
        return values
    # Strings (S/R).  Empty replacements are meaningful: they remove the token.
    return parse_csv_values(raw)


def format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isfinite(value):
            return f"{value:g}"
    return str(value)


def format_value(value: Any) -> str:
    return format_number(value)


def sr_search(values: list[Any]) -> str:
    return str(values[0]) if values else ""


def axis_label(type_id: str) -> str:
    return type_info(type_id)["label"]


def axis_kind(type_id: str) -> str:
    return type_info(type_id)["kind"]


def describe_axis(axis: dict[str, Any]) -> str:
    type_id = str(axis.get("type") or "none")
    info = type_info(type_id)
    if info["kind"] == "none":
        return ""
    values = [format_value(value) for value in axis.get("values") or []]
    label = info["label"]
    if type_id == "lora":
        name = str(axis.get("lora") or "")
        if name:
            label = f"LoRA {name}"
    if type_id in {"prompt_sr", "negative_sr"} and values:
        search = values[0]
        return f"{label} « {search} » = {', '.join(values)}"
    return f"{label} = {', '.join(values)}"
