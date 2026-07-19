from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from src.utils import project_root, write_csv


def profile_dataset(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        rows.append({
            "column": col,
            "dtype": str(df[col].dtype),
            "record_count": len(df),
            "non_null_count": int(df[col].notna().sum()),
            "null_count": int(df[col].isna().sum()),
            "null_pct": round(float(df[col].isna().mean() * 100), 4),
            "distinct_count": int(df[col].nunique(dropna=True)),
            "sample_values": ", ".join(df[col].dropna().astype(str).unique()[:5]),
        })
    profile = pd.DataFrame(rows)
    write_csv(profile, project_root() / config["outputs_dir"] / "data_profile_summary.csv")
    return profile
