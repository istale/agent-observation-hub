from typing import Any


def extract_usage(response_json: dict[str, Any]) -> dict[str, int | None]:
    usage = response_json.get("usage") or {}
    return {
        "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
