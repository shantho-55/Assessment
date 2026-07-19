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


def _find_candidate_dataset_ids(metadata: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return candidate HDB resale dataset metadata from Collection 189.

    data.gov.sg metadata structures can change, so this parser searches recursively
    for dictionaries containing an id and a name/title with resale flat price language.
    """
    candidates = []

    def walk(obj):
        if isinstance(obj, dict):
            values = " ".join(str(v) for v in obj.values() if isinstance(v, (str, int, float)))
            item_id = obj.get("datasetId") or obj.get("id") or obj.get("resource_id") or obj.get("resourceId")
            title = obj.get("name") or obj.get("title") or obj.get("datasetName") or values[:120]
            if item_id and re.search(r"resale flat prices", values, re.I):
                candidates.append({"id": str(item_id), "title": str(title)})
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(metadata)
    deduped = []
    seen = set()
    for c in candidates:
        key = c["id"]
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    return deduped


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
