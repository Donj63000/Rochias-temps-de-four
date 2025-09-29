"""UI-specific helpers to mask unavailable oven cells."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

TAPIS_CELLS: Dict[int, Tuple[int, ...]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
}


@dataclass(frozen=True)
class CellUIState:
    """State mask applied on top of the engine structure."""

    visible: bool = True
    selectable: bool = True


_DEFAULT_STATE = CellUIState()
UI_CELL_MASK: Dict[int, CellUIState] = {
    1: CellUIState(),
    2: CellUIState(),
    3: CellUIState(),
    4: CellUIState(),
    5: CellUIState(),
    6: CellUIState(),
    7: CellUIState(),
    8: CellUIState(),
    9: CellUIState(visible=False, selectable=False),
}


def _state_for(cell_id: int) -> CellUIState:
    return UI_CELL_MASK.get(int(cell_id), _DEFAULT_STATE)


def is_cell_visible(cell_id: int) -> bool:
    return _state_for(int(cell_id)).visible


def is_cell_selectable(cell_id: int) -> bool:
    return _state_for(int(cell_id)).selectable


def _filter_cells(cells: Iterable[int], *, predicate) -> Tuple[int, ...]:
    filtered = []
    for cell in cells:
        try:
            cid = int(cell)
        except (TypeError, ValueError):
            continue
        if predicate(cid):
            filtered.append(cid)
    return tuple(filtered)


def visible_cells_for_tapis(numero: int) -> Tuple[int, ...]:
    base = TAPIS_CELLS.get(int(numero), ())
    return _filter_cells(base, predicate=is_cell_visible)


def selectable_cells_for_tapis(numero: int) -> Tuple[int, ...]:
    base = TAPIS_CELLS.get(int(numero), ())
    return _filter_cells(base, predicate=is_cell_selectable)


def assert_cell_selectable(cell_id: int) -> None:
    if not is_cell_selectable(cell_id):
        err = ValueError(f"CELL_NOT_SELECTABLE:{cell_id}")
        setattr(err, "code", "CELL_NOT_SELECTABLE")
        raise err


def sanitize_plan(plan: Mapping[int, Any]) -> Dict[int, Any]:
    cleaned: Dict[int, Any] = {}
    for key, value in plan.items():
        try:
            cell_id = int(key)
        except (TypeError, ValueError):
            continue
        if is_cell_selectable(cell_id):
            cleaned[cell_id] = value
    return cleaned


def to_engine_input(plan_ui: Mapping[int, Any], *, empty_value: Any = None) -> Dict[int, Any]:
    engine_cells: Tuple[int, ...] = tuple(sorted({cell for cells in TAPIS_CELLS.values() for cell in cells}))
    result: Dict[int, Any] = {}
    for key, value in plan_ui.items():
        try:
            cell_id = int(key)
        except (TypeError, ValueError):
            continue
        result[cell_id] = value
    for cell_id in engine_cells:
        result.setdefault(cell_id, empty_value)
    return result


__all__ = [
    "TAPIS_CELLS",
    "CellUIState",
    "UI_CELL_MASK",
    "visible_cells_for_tapis",
    "selectable_cells_for_tapis",
    "is_cell_visible",
    "is_cell_selectable",
    "assert_cell_selectable",
    "sanitize_plan",
    "to_engine_input",
]
