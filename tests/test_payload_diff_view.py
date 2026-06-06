"""Test the side-by-side diff line aligner."""
from __future__ import annotations

from app.payload_diff_view import diff_lines


def test_equal_objects_all_equal():
    obj = {"a": 1, "b": [1, 2, 3]}
    left, right = diff_lines(obj, obj)
    assert all(l["cls"] == "equal" for l in left)
    assert all(r["cls"] == "equal" for r in right)
    assert len(left) == len(right)


def test_added_field_marked_added_on_right():
    a = {"x": 1}
    b = {"x": 1, "y": 2}
    left, right = diff_lines(a, b)
    # The added field should be highlighted on the right (difflib may use
    # "added" for pure inserts or "changed" when surrounding lines also shift).
    classes_right = [r["cls"] for r in right]
    assert any(c in ("added", "changed") for c in classes_right)
    # And the left side should contain at least one non-equal row.
    classes_left = [l["cls"] for l in left]
    assert any(c in ("empty", "changed", "removed") for c in classes_left)


def test_removed_field_marked_removed_on_left():
    a = {"x": 1, "y": 2}
    b = {"x": 1}
    left, right = diff_lines(a, b)
    # Left should contain a removed line for y
    assert any(l["cls"] in ("removed", "changed") for l in left)


def test_columns_equal_length():
    """Side-by-side requires both columns to have the same number of rows."""
    a = {"a": 1}
    b = {"a": 1, "b": 2, "c": 3}
    left, right = diff_lines(a, b)
    assert len(left) == len(right)
