import zipfile
from datetime import datetime
from .constants import UPLOADS_DIR


def save_and_extract_zip(uploaded_file, batch_name=None):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{batch_name}_{ts}" if batch_name else f"batch_{ts}"
    batch_dir = UPLOADS_DIR / folder_name
    batch_dir.mkdir(parents=True, exist_ok=True)

    zip_path = batch_dir / uploaded_file.name
    with open(zip_path, "wb+") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(batch_dir)

    return {"batch_dir": batch_dir, "zip_path": zip_path}