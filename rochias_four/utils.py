"""Formatting and parsing helpers used by the UI."""

from __future__ import annotations

import math


def parse_hz(raw: str) -> float:
    """Accept either 40.00 (Hz) or 4000 (IHM). Values >200 are divided by 100."""
    text = (raw or "").strip().replace(",", ".")
    if not text:
        raise ValueError("Champ vide")
    value = float(text)
    return (value / 100.0) if value > 200.0 else value


def fmt_minutes(value: float) -> str:
    if value is None or not math.isfinite(value):
        return "?"
    if value < 0:
        value = 0.0
    total_seconds = int(round(value * 60))
    hours = total_seconds // 3600
    total_seconds %= 3600
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours}h {minutes:02d}min {seconds:02d}s"
    return f"{minutes}min {seconds:02d}s"


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds + 0.5))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
