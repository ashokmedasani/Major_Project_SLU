from django.http import JsonResponse
from django.conf import settings
import pandas as pd

CSV_FILES = [
    "claims_transactions.csv",
    "claims.csv",
    "encounters.csv",
    "immunizations.csv",
    "observations.csv",
    "organizations.csv",
    "patients.csv",
    "payer_transitions.csv",
    "payers.csv",
    "providers.csv",
]

def data_health(request):
    data_dir = settings.RAW_DATA_DIR

    if not data_dir.exists():
        return JsonResponse({
            "status": "error",
            "message": "Data folder does not exist.",
            "expected_path": str(data_dir)
        }, status=500)

    results = []

    for file in CSV_FILES:
        file_path = data_dir / file

        if not file_path.exists():
            results.append({
                "file": file,
                "exists": False
            })
            continue

        try:
            df = pd.read_csv(file_path)
            results.append({
                "file": file,
                "exists": True,
                "rows": int(df.shape[0]),
                "columns_count": int(df.shape[1])
            })
        except Exception as e:
            results.append({
                "file": file,
                "exists": True,
                "error": str(e)
            })

    return JsonResponse({
        "status": "success",
        "data_path": str(data_dir),
        "files": results
    })



def data_schema(request):
    data_dir = settings.RAW_DATA_DIR

    schema = []
    for file in CSV_FILES:
        file_path = data_dir / file
        if not file_path.exists():
            schema.append({"file": file, "exists": False})
            continue

        try:
            df = pd.read_csv(file_path, nrows=5)  # small read
            schema.append({
                "file": file,
                "exists": True,
                "columns": list(df.columns),
                "sample_rows": df.head(2).to_dict(orient="records")  # tiny sample
            })
        except Exception as e:
            schema.append({"file": file, "exists": True, "error": str(e)})

    return JsonResponse({"status": "success", "schema": schema})


