from __future__ import annotations

import re
from datetime import date
from typing import Dict, Any, Tuple, List

import numpy as np
import pandas as pd
import logging
from src.utils import add_failure_reason, project_root, write_csv

STOREY_PATTERN = re.compile(r"^\d{2}\s+TO\s+\d{2}$")
logger = logging.getLogger(__name__)

def _parse_year_month(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str) + "-01", errors="coerce")


def recompute_remaining_lease(lease_commence_year, as_of_date: date) -> str:
    try:
        y = int(float(lease_commence_year))
        lease_end = date(y + 99, 1, 1)
        if lease_end <= as_of_date:
            return "0 years 0 months"
        months_remaining = (lease_end.year - as_of_date.year) * 12 + (lease_end.month - as_of_date.month)
        if lease_end.day < as_of_date.day:
            months_remaining -= 1
        years = max(months_remaining, 0) // 12
        months = max(months_remaining, 0) % 12
        return f"{years} years {months} months"
    except Exception:
        logger.warning(
            "recompute_remaining_lease: could not parse lease_commence_date=%r; returning NaN",
            lease_commence_year,
        )
        return np.nan

def apply_core_type_casts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["floor_area_sqm", "resale_price", "lease_commence_date"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ["town", "flat_type", "flat_model", "storey_range", "block", "street_name"]:
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
    return out


def validate_dataset(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = apply_core_type_casts(df)
    failed_parts: List[pd.DataFrame] = []
    valid_mask = pd.Series(True, index=work.index)

    required_cols = config["expected_columns"]
    missing_cols = [c for c in required_cols if c not in work.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    checks = []

    def register_failure(mask: pd.Series, reason: str):
        nonlocal valid_mask
        idx = mask.fillna(False)
        checks.append({"rule": reason, "failed_records": int(idx.sum())})
        if idx.any():
            failed_parts.append(add_failure_reason(work.loc[idx], reason))
        valid_mask = valid_mask & ~idx

    month_parsed = _parse_year_month(work["month"])
    register_failure(month_parsed.isna(), "Invalid month format")
    register_failure((work["month"] < config["start_month"]) | (work["month"] > config["end_month"]), "Month outside required assignment period")

    for col in ["town", "flat_type", "flat_model"]:
        allowed = set(work.loc[valid_mask, col].dropna().astype(str).str.strip().unique())
        register_failure(~work[col].astype(str).str.strip().isin(allowed), f"Invalid {col} outside observed master domain")

    register_failure(~work["storey_range"].astype(str).str.upper().str.match(STOREY_PATTERN), "Invalid storey_range pattern")
    register_failure(work["resale_price"].isna() | (work["resale_price"] <= 0), "Invalid resale_price")
    register_failure(work["floor_area_sqm"].isna() | (work["floor_area_sqm"] <= 0), "Invalid floor_area_sqm")
    register_failure(work["lease_commence_date"].isna() | (work["lease_commence_date"] < 1900), "Invalid lease_commence_date")

    resale_year = month_parsed.dt.year
    register_failure(work["lease_commence_date"] > resale_year, "Lease commencement year is after resale year")
    register_failure(work["block"].isna() | work["block"].astype(str).str.strip().eq(""), "Missing block")
    register_failure(work["street_name"].isna() | work["street_name"].astype(str).str.strip().eq(""), "Missing street_name")

    cleaned = work.loc[valid_mask].copy()
    failed = pd.concat(failed_parts, ignore_index=True) if failed_parts else pd.DataFrame(columns=list(work.columns) + ["failure_reason"])
    validation_summary = pd.DataFrame(checks)
    write_csv(validation_summary, project_root() / config["outputs_dir"] / "validation_summary.csv")
    return cleaned, failed, validation_summary


def handle_duplicates(cleaned: pd.DataFrame, failed: pd.DataFrame, config: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # Exclude resale_price (per the documented composite-key rule) and internal
    # pipeline bookkeeping columns such as _source_file, which are not business
    # fields and would otherwise prevent a genuine duplicate transaction that
    # happens to appear in two different downloaded source files from being
    # detected as a duplicate at all.
    non_key_cols = {"resale_price", "_source_file"}
    key_cols = [c for c in cleaned.columns if c not in non_key_cols]
    sorted_df = cleaned.sort_values("resale_price", ascending=False).copy()
    kept = sorted_df.drop_duplicates(subset=key_cols, keep="first").copy()
    dup_failed = sorted_df[sorted_df.duplicated(subset=key_cols, keep="first")].copy()
    if not dup_failed.empty:
        dup_failed = add_failure_reason(dup_failed, "Duplicate composite key with lower resale price")
        failed = pd.concat([failed, dup_failed], ignore_index=True, sort=False)
    return kept, failed


def flag_price_anomalies(cleaned: pd.DataFrame, config: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    out = cleaned.copy()
    group_cols = config["anomaly"]["group_by"]
    multiplier = float(config["anomaly"].get("iqr_multiplier", 1.5))

    stats = out.groupby(group_cols)["resale_price"].agg(q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75), count="count").reset_index()
    stats["iqr"] = stats["q3"] - stats["q1"]
    stats["lower_bound"] = stats["q1"] - multiplier * stats["iqr"]
    stats["upper_bound"] = stats["q3"] + multiplier * stats["iqr"]

    out = out.merge(stats[group_cols + ["lower_bound", "upper_bound", "count"]], on=group_cols, how="left")
    out["potential_price_anomaly"] = np.where(
        (out["count"] >= 4) & ((out["resale_price"] < out["lower_bound"]) | (out["resale_price"] > out["upper_bound"])),
        True,
        False,
    )
    anomaly_summary = pd.DataFrame([{
        "heuristic": "IQR by month, town and flat_type",
        "iqr_multiplier": multiplier,
        "minimum_group_size": 4,
        "potential_anomaly_records": int(out["potential_price_anomaly"].sum()),
    }])
    write_csv(anomaly_summary, project_root() / config["outputs_dir"] / "anomaly_summary.csv")
    return out.drop(columns=["lower_bound", "upper_bound", "count"]), anomaly_summary
