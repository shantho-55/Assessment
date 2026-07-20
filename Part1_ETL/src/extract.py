from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
import requests

from src.utils import project_root, standardise_schema, write_csv

COLLECTION_METADATA_URL = "https://api-production.data.gov.sg/v2/public/api/collections/{collection_id}/metadata"
DATASTORE_SEARCH_URL = "https://data.gov.sg/api/action/datastore_search"


def get_collection_metadata(collection_id: int) -> Dict[str, Any]:
    response = requests.get(COLLECTION_METADATA_URL.format(collection_id=collection_id), timeout=60)
    response.raise_for_status()
    return response.json()

def get_dataset_metadata(dataset_id: str) -> Dict[str, Any]:
    response = requests.get(DATASET_METADATA_URL.format(dataset_id=dataset_id), timeout=60)
    response.raise_for_status()
    return response.json()

def _find_candidate_dataset_ids(metadata: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return candidate HDB resale dataset metadata from Collection 189.

    The v2 collection metadata endpoint only lists child dataset ids under
    ``data.collectionMetadata.childDatasets`` (plain id strings, no titles), so each
    id must be resolved individually via the per-dataset metadata endpoint to get a
    real name and coverage window before it can be filtered for relevance.
    """
    child_ids: List[str] = metadata.get("data", {}).get("collectionMetadata", {}).get("childDatasets", [])

    candidates = []
    for dataset_id in child_ids:
        try:
            dataset_meta = get_dataset_metadata(dataset_id).get("data", {})
        except requests.RequestException:
            continue
        name = dataset_meta.get("name", "")
        if not re.search(r"resale flat prices", name, re.I):
            continue
        candidates.append({
            "id": dataset_id,
            "title": name,
            "coverage_start": dataset_meta.get("coverageStart", ""),
            "coverage_end": dataset_meta.get("coverageEnd", ""),
        })
    return candidates


def fetch_dataset_records(resource_id: str) -> pd.DataFrame:
    records = []
    limit = 5000
    offset = 0
    while True:
        response = requests.get(DATASTORE_SEARCH_URL, params={"resource_id": resource_id, "limit": limit, "offset": offset}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result", {})
        batch = result.get("records", [])
        if not batch:
            break
        records.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return pd.DataFrame(records)


def extract_raw_datasets(config: Dict[str, Any]) -> List[Path]:
    raw_dir = project_root() / config["raw_dir"]
    metadata = get_collection_metadata(int(config["collection_id"]))
    candidates = _find_candidate_dataset_ids(metadata)

    if not candidates:
        raise ValueError("No resale flat price datasets found from collection metadata.")

    saved_paths = []
    for item in candidates:
        coverage_start = str(item.get("coverage_start", ""))[:7]
        coverage_end = str(item.get("coverage_end", ""))[:7]
        if coverage_start and coverage_end and (coverage_end < config["start_month"] or coverage_start > config["end_month"]):
            continue
        df = fetch_dataset_records(item["id"])
        if df.empty or "month" not in [c.lower() for c in df.columns]:
            continue
        df = standardise_schema(df)
        if "month" not in df.columns:
            continue
        df["month"] = df["month"].astype(str)
        min_month, max_month = df["month"].min(), df["month"].max()
        if max_month < config["start_month"] or min_month > config["end_month"]:
            continue
        safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", item["title"]).strip("_").lower()[:80]
        path = raw_dir / f"{safe_name or item['id']}.csv"
        write_csv(df, path)
        saved_paths.append(path)

    if not saved_paths:
        raise ValueError("No raw files overlapping configured date range were saved.")
    return saved_paths


def load_raw_files(config: Dict[str, Any]) -> pd.DataFrame:
    raw_dir = project_root() / config["raw_dir"]
    files = sorted(p for p in raw_dir.glob("*.csv") if p.is_file())
    if not files:
        files = extract_raw_datasets(config)

    frames = []
    for path in files:
        df = pd.read_csv(path, dtype=str)
        df = standardise_schema(df)
        df["_source_file"] = path.name
        frames.append(df)

    master = pd.concat(frames, ignore_index=True, sort=False)
    master["month"] = master["month"].astype(str)
    master = master[(master["month"] >= config["start_month"]) & (master["month"] <= config["end_month"])].copy()
    return master
