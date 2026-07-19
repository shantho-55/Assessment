from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any

import yaml
import pandas as pd


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(config_path: str | Path = "config/pipeline_config.yaml") -> Dict[str, Any]:
    path = project_root() / config_path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs(config: Dict[str, Any]) -> None:
    for key in ["raw_dir", "cleaned_dir", "transformed_dir", "failed_dir", "hashed_dir", "outputs_dir"]:
        (project_root() / config[key]).mkdir(parents=True, exist_ok=True)


def normalise_column_name(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")


def standardise_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [normalise_column_name(c) for c in out.columns]
    return out


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def add_failure_reason(df: pd.DataFrame, reason: str) -> pd.DataFrame:
    out = df.copy()
    if "failure_reason" in out.columns:
        out["failure_reason"] = out["failure_reason"].fillna("")
        out["failure_reason"] = out["failure_reason"].where(out["failure_reason"].eq(""), out["failure_reason"] + "; ") + reason
    else:
        out["failure_reason"] = reason
    return out
