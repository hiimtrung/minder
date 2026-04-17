from __future__ import annotations

import sys
import warnings

if sys.version_info >= (3, 14):
    warnings.filterwarnings(
        "ignore",
        message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
        category=UserWarning,
        module=r"langchain_core\._api\.deprecation",
    )
