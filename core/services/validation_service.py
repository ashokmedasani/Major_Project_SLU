import pandas as pd
from .constants import REQUIRED_FILES, CHOSEN_COLS


def find_csv_files(batch_dir):
    files = {}
    for file in batch_dir.rglob("*.csv"):
        files[file.name] = file
    return files


def validate_required_files(batch_dir):
    found_files = find_csv_files(batch_dir)
    missing = [f for f in REQUIRED_FILES if f not in found_files]
    extra = [f for f in found_files if f not in REQUIRED_FILES]
    return {
        "is_valid": len(missing) == 0,
        "found_files": found_files,
        "missing_files": missing,
        "extra_files": extra,
    }


def validate_required_columns(found_files):
    details = {}
    overall_ok = True

    for table_name, required_cols in CHOSEN_COLS.items():
        file_name = f"{table_name}.csv"
        if file_name not in found_files:
            details[table_name] = {"file_present": False, "missing_columns": required_cols}
            overall_ok = False
            continue

        df = pd.read_csv(found_files[file_name], nrows=5, low_memory=False)
        missing_cols = [c for c in required_cols if c not in df.columns]
        details[table_name] = {
            "file_present": True,
            "missing_columns": missing_cols,
            "available_columns": list(df.columns),
        }
        if missing_cols:
            overall_ok = False

    return {"is_valid": overall_ok, "details": details}