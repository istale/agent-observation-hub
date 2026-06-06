"""Helpers for the side-by-side payload diff view."""
from __future__ import annotations

import difflib
import json
from typing import Any


def _pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def diff_lines(ctx_obj: Any, pp_obj: Any) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return per-side line lists with css class hints.

    Uses difflib.SequenceMatcher to align lines. Each side gets a list of
    {text, cls} where cls is one of: equal, removed (left only), added
    (right only), changed (both differ).
    """
    a = _pretty(ctx_obj).splitlines()
    b = _pretty(pp_obj).splitlines()
    sm = difflib.SequenceMatcher(a=a, b=b)
    left: list[dict[str, str]] = []
    right: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in a[i1:i2]:
                left.append({"text": line, "cls": "equal"})
                right.append({"text": line, "cls": "equal"})
        elif tag == "replace":
            # pad to keep rows aligned
            la = a[i1:i2]
            lb = b[j1:j2]
            n = max(len(la), len(lb))
            for k in range(n):
                if k < len(la):
                    left.append({"text": la[k], "cls": "changed"})
                else:
                    left.append({"text": "", "cls": "empty"})
                if k < len(lb):
                    right.append({"text": lb[k], "cls": "changed"})
                else:
                    right.append({"text": "", "cls": "empty"})
        elif tag == "delete":
            for line in a[i1:i2]:
                left.append({"text": line, "cls": "removed"})
                right.append({"text": "", "cls": "empty"})
        elif tag == "insert":
            for line in b[j1:j2]:
                left.append({"text": "", "cls": "empty"})
                right.append({"text": line, "cls": "added"})
    return left, right
