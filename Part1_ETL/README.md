# HDB Resale ETL Pipeline

## Project Goal
This project implements a Python ETL workflow for HDB resale flat transactions. The pipeline ingests records from data.gov.sg Collection 189, focuses on data from `2012-01` through `2016-12`, and produces cleaned, transformed, failed, and hashed outputs that support downstream analysis.

Core processing steps include:
- Data extraction and consolidation into a single master dataset.
- Profiling and rule-based validation.
- Remaining lease recalculation with a 99-year lease baseline.
- Composite-key duplicate resolution.
- Potential anomaly tagging for resale price.
- Resale identifier generation and SHA-256 hashing.

## Data Source
- Dataset: data.gov.sg, Collection 189 (HDB Resale Flat Prices).
- Raw files are downloaded by the pipeline and stored under `data/raw/` without manual edits.

## Deliverables Implemented
1. Merge source files into one master table.
2. Produce profile outputs for the master table.
3. Validate `month`, `town`, `flat_type`, `flat_model`, and `storey_range` using domain and distribution checks.
4. Recompute `remaining_lease`.
5. Resolve duplicates using a composite key of all columns except `resale_price`, keeping the higher price row.
6. Mark potential price anomalies using grouped IQR thresholds.
7. Build the required resale identifier.
8. Hash identifiers with SHA-256.
9. Write outputs to raw, cleaned, transformed, failed, and hashed layers.

## Repository Layout
```text
config/                  Pipeline settings
notebooks/               Notebook entry point
src/                     ETL modules
data/raw/                Unmodified downloaded data
data/cleaned/            Records that pass validation
data/transformed/        Cleaned records with derived fields
data/failed/             Rejected or filtered-out records
data/hashed/             Output with hashed identifier
outputs/                 Profiling, validation, and anomaly summaries
```

## Setup
```bash
pip install -r requirements.txt
```

## Run
Notebook entry:
```text
notebooks/hdb_resale_etl_pipeline.ipynb
```

Command-line entry:
```bash
python -m src.pipeline
```

## Expected Outputs
```text
data/cleaned/hdb_resale_cleaned.csv
data/transformed/hdb_resale_transformed.csv
data/failed/hdb_resale_failed.csv
data/hashed/hdb_resale_hashed.csv
outputs/data_profile_summary.csv
outputs/validation_summary.csv
outputs/anomaly_summary.csv
```

## Assumptions
- HDB lease duration is treated as 99 years.
- `remaining_lease` is recomputed as of `2026-07-18`, then expressed in years and months.
- Duplicate detection uses every field except `resale_price`.
- When duplicates are found, lower-priced rows are sent to the failed dataset.
- Price anomalies are tagged for review and are not auto-dropped unless another validation rule fails.
- SHA-256 is used as a deterministic one-way hash.

## Anomaly Rule
Potential resale price outliers are identified per `month`, `town`, and `flat_type` group using IQR limits:
- Lower bound: `Q1 - 1.5 * IQR`
- Upper bound: `Q3 + 1.5 * IQR`

Groups with fewer than 4 rows are skipped to avoid unstable thresholds.

## Integrity Note
The README content has been rewritten in original wording for this repository and reflects the implementation in this codebase.
