from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import math

C1 = 1330585.39
C2 = 916784.29
C3 = 6911721.07

Lconv1 = 11.485
Lconv2 = 11.685
Lconv3 = 6.980

def _to_ui(value: float, units: Literal["auto","hz","ui"]="auto") -> float:
    v = float(value)
    if units == "ui":
        ui = v
    elif units == "hz":
        ui = v * 100.0
    else:
        ui = v if v > 200.0 else v * 100.0
    if ui < 500.0:
        ui = 500.0
    if ui > 9999.0:
        ui = 9999.0
    return ui

def _fmt_hms_from_seconds(sec: float) -> str:
    s = math.floor(sec + 1e-12)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}min {s:02d}s"

@dataclass(frozen=True)
class MaintTimes:
    t1_s: float
    t2_s: float
    t3_s: float
    total_s: float
    t1_min: float
    t2_min: float
    t3_min: float
    total_min: float
    t1_hms: str
    t2_hms: str
    t3_hms: str
    total_hms: str
    f1_hz: float
    f2_hz: float
    f3_hz: float
    ui1: float
    ui2: float
    ui3: float

def compute_times_maintenance(f1_in: float, f2_in: float, f3_in: float, units: Literal["auto","hz","ui"]="auto") -> MaintTimes:
    ui1 = _to_ui(f1_in, units)
    ui2 = _to_ui(f2_in, units)
    ui3 = _to_ui(f3_in, units)
    t1_s = Lconv1 * C1 / ui1
    t2_s = Lconv2 * C2 / ui2
    t3_s = Lconv3 * C3 / ui3
    T_s = t1_s + t2_s + t3_s
    return MaintTimes(
        t1_s=t1_s,
        t2_s=t2_s,
        t3_s=t3_s,
        total_s=T_s,
        t1_min=t1_s/60.0,
        t2_min=t2_s/60.0,
        t3_min=t3_s/60.0,
        total_min=T_s/60.0,
        t1_hms=_fmt_hms_from_seconds(t1_s),
        t2_hms=_fmt_hms_from_seconds(t2_s),
        t3_hms=_fmt_hms_from_seconds(t3_s),
        total_hms=_fmt_hms_from_seconds(T_s),
        f1_hz=ui1/100.0,
        f2_hz=ui2/100.0,
        f3_hz=ui3/100.0,
        ui1=ui1,
        ui2=ui2,
        ui3=ui3
    )
