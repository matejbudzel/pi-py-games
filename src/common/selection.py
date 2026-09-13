"""Small, presentation-agnostic selection-list state helpers."""
from __future__ import annotations


def visible_window(first_visible: int, selected: int, item_count: int, rows: int) -> int:
    """Keep ``selected`` visible, returning the first row to render."""
    if item_count <= rows:
        return 0
    selected = max(0, min(selected, item_count - 1))
    maximum = item_count - rows
    if selected < first_visible:
        return selected
    if selected >= first_visible + rows:
        return min(maximum, selected - rows + 1)
    return max(0, min(first_visible, maximum))


def move_selection(selected: int, delta: int, item_count: int) -> int:
    """Move through a non-empty list with the wraparound used by game menus."""
    return (selected + delta) % item_count if item_count else 0
