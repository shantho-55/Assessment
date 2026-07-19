from __future__ import annotations

import re
from datetime import date
from typing import Dict, Any

import pandas as pd

from src.validate import recompute_remaining_lease


def _block_3_digits(block) -> str:
    digits = re.sub(r"\D", "", str(block))
    return digits.zfill(3)[:3]


def _price_prefix(avg_price) -> str:
    try:
        digits = re.sub(r"\D", "", str(int(float(avg_price))))
        return digits[:2].zfill(2)
    except Exception:
        return "00"


def transform_dataset(cleaned: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    out = cleaned.copy()
    as_of = date.fromisoformat(config["as_of_date"])

    out["remaining_lease_recomputed"] = out["lease_commence_date"].apply(lambda x: recompute_remaining_lease(x, as_of))

    out["avg_resale_price_group"] = out.groupby(["month", "town", "flat_type"])["resale_price"].transform("mean")
    out["resale_identifier"] = (
        "S"
        + out["block"].apply(_block_3_digits)
        + out["avg_resale_price_group"].apply(_price_prefix)
        + pd.to_datetime(out["month"] + "-01").dt.month.astype(str).str.zfill(2)
        + out["town"].astype(str).str.strip().str[0].str.upper()
    )

    # Preserve core transformed output while retaining supporting columns for traceability.
    return out
