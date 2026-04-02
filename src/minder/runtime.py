from __future__ import annotations

import importlib.util
from typing import Any


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def load_attr(module_name: str, attr_name: str) -> Any | None:
    if not module_available(module_name):
        return None
    module = __import__(module_name, fromlist=[attr_name])
    return getattr(module, attr_name, None)
