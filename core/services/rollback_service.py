import shutil
from pathlib import Path

from django.utils import timezone
from core.models import (
    BatchSyncLog,
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
    MasterEncounter,
    MasterHospital,
    MasterPatient,
    HospitalSummary,
    HospitalYearlySummary,
    HospitalMonthlySummary,
)
from core.services.sync_service import rebuild_hospital_summaries


def rollback_batch(batch, delete_storage=False, delete_raw_data=True):
    # 1. delete synced encounter rows for this batch
    deleted_encounters, _ = MasterEncounter.objects.filter(source_batch=batch).delete()

    # 2. remove orphan master patients and hospitals
    deleted_hospitals, _ = MasterHospital.objects.filter(masterencounter__isnull=True).delete()
    deleted_patients, _ = MasterPatient.objects.filter(masterencounter__isnull=True).delete()

    # 3. optionally delete raw batch data
    raw_deleted_counts = {}
    if delete_raw_data:
        raw_deleted_counts["patients"] = RawPatient.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["organizations"] = RawOrganization.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["providers"] = RawProvider.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["encounters"] = RawEncounter.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["observations"] = RawObservation.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["immunizations"] = RawImmunization.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["claims"] = RawClaim.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["claim_transactions"] = RawClaimTransaction.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["payers"] = RawPayer.objects.filter(batch=batch).delete()[0]
        raw_deleted_counts["payer_transitions"] = RawPayerTransition.objects.filter(batch=batch).delete()[0]

    # 4. rebuild summaries
    rebuild_hospital_summaries()

    # 5. optionally delete extracted storage folder
    storage_message = "Storage kept."
    if delete_storage and batch.extracted_path:
        batch_path = Path(batch.extracted_path)
        if batch_path.exists() and batch_path.is_dir():
            shutil.rmtree(batch_path, ignore_errors=True)
            storage_message = f"Deleted extracted folder: {batch.extracted_path}"
        else:
            storage_message = "Extracted folder not found."

    # 6. update batch status
    batch.status = "rolled_back"
    batch.synced_at = timezone.now()
    batch.sync_message = (
        f"Rollback complete. "
        f"Deleted master encounters: {deleted_encounters}, "
        f"deleted orphan patients: {deleted_patients}, "
        f"deleted orphan hospitals: {deleted_hospitals}. "
        f"{storage_message}"
    )
    batch.save()

    BatchSyncLog.objects.create(
        batch=batch,
        action="rollback_batch",
        message=batch.sync_message
    )