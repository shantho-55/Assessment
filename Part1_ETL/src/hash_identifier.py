from __future__ import annotations

import hashlib
import pandas as pd


def sha256_hash(value) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def add_hashed_identifier(transformed: pd.DataFrame) -> pd.DataFrame:
    out = transformed.copy()
    out["hashed_resale_identifier"] = out["resale_identifier"].apply(sha256_hash)
    return out
