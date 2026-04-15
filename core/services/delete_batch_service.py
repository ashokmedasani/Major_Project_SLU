import shutil
from pathlib import Path

from core.models import (
    RawPatient,
    RawOrganization,
    RawProvider,
    RawEncounter,
    RawObservation,
    RawImmunization,
    RawClaim,
    RawClaimTransaction,
    RawPayer,
    RawPayerTransition,
)


def delete_batch_data(batch, delete_batch_record=False):
    RawPatient.objects.filter(batch=batch).delete()
    RawOrganization.objects.filter(batch=batch).delete()
    RawProvider.objects.filter(batch=batch).delete()
    RawEncounter.objects.filter(batch=batch).delete()
    RawObservation.objects.filter(batch=batch).delete()
    RawImmunization.objects.filter(batch=batch).delete()
    RawClaim.objects.filter(batch=batch).delete()
    RawClaimTransaction.objects.filter(batch=batch).delete()
    RawPayer.objects.filter(batch=batch).delete()
    RawPayerTransition.objects.filter(batch=batch).delete()

    if batch.extracted_path:
        batch_path = Path(batch.extracted_path)
        if batch_path.exists() and batch_path.is_dir():
            shutil.rmtree(batch_path, ignore_errors=True)

    if delete_batch_record:
        batch.delete()