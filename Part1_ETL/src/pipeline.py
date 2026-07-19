from __future__ import annotations

from typing import Dict, Any

from src.extract import load_raw_files
from src.profile import profile_dataset
from src.transform import transform_dataset
from src.hash_identifier import add_hashed_identifier
from src.utils import load_config, ensure_dirs, project_root, write_csv
from src.validate import validate_dataset, handle_duplicates, flag_price_anomalies


def run_pipeline(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    config = config or load_config()
    ensure_dirs(config)

    master = load_raw_files(config)
    profile = profile_dataset(master, config)

    cleaned, failed, validation_summary = validate_dataset(master, config)
    cleaned, failed = handle_duplicates(cleaned, failed, config)
    cleaned, anomaly_summary = flag_price_anomalies(cleaned, config)

    transformed = transform_dataset(cleaned, config)
    hashed = add_hashed_identifier(transformed)

    write_csv(cleaned, project_root() / config["cleaned_dir"] / "hdb_resale_cleaned.csv")
    write_csv(transformed, project_root() / config["transformed_dir"] / "hdb_resale_transformed.csv")
    write_csv(failed, project_root() / config["failed_dir"] / "hdb_resale_failed.csv")
    write_csv(hashed, project_root() / config["hashed_dir"] / "hdb_resale_hashed.csv")

    return {
        "master_records": len(master),
        "cleaned_records": len(cleaned),
        "failed_records": len(failed),
        "transformed_records": len(transformed),
        "hashed_records": len(hashed),
        "profile_rows": len(profile),
        "validation_rules": len(validation_summary),
        "potential_price_anomalies": int(cleaned["potential_price_anomaly"].sum()) if "potential_price_anomaly" in cleaned.columns else 0,
    }


if __name__ == "__main__":
    summary = run_pipeline()
    for key, value in summary.items():
        print(f"{key}: {value}")
