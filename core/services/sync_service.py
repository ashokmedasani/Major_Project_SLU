from django.db.models import Avg, Sum
from django.utils import timezone
from core.models import (
    BatchSyncLog,
    RawPatient, RawOrganization, RawEncounter,
    MasterPatient, MasterHospital, MasterEncounter,
    HospitalSummary, HospitalYearlySummary, HospitalMonthlySummary
)


def sync_batch_to_master(batch):
    # -------------------------
    # TEMP LIMIT FOR TESTING
    # -------------------------
    raw_patients = RawPatient.objects.filter(batch=batch)[:100]
    raw_orgs = RawOrganization.objects.filter(batch=batch)[:100]
    raw_encounters = RawEncounter.objects.filter(batch=batch)[:100]

    # -------------------------
    # Patients
    # -------------------------
    for row in raw_patients:
        MasterPatient.objects.update_or_create(
            patient_id=row.patient_id,
            defaults={
                "birthdate": row.birthdate,
                "gender": row.gender,
                "race": row.race,
                "ethnicity": row.ethnicity,
                "city": row.city,
                "state": row.state,
                "zip_code": row.zip_code,
                "lat": row.lat,
                "lon": row.lon,
                "income": row.income,
                "healthcare_expenses": row.healthcare_expenses,
                "healthcare_coverage": row.healthcare_coverage,
            }
        )

    BatchSyncLog.objects.create(
        batch=batch,
        action="sync_patients",
        message="Patients synced (test mode: first 100 rows)"
    )

    # -------------------------
    # Hospitals
    # -------------------------
    for row in raw_orgs:
        MasterHospital.objects.update_or_create(
            hospital_id=row.organization_id,
            defaults={
                "name": row.name,
                "city": row.city,
                "state": row.state,
                "zip_code": row.zip_code,
                "lat": row.lat,
                "lon": row.lon,
                "revenue": row.revenue,
                "utilization": row.utilization,
            }
        )

    BatchSyncLog.objects.create(
        batch=batch,
        action="sync_hospitals",
        message="Hospitals synced (test mode: first 100 rows)"
    )

    # -------------------------
    # Encounters
    # -------------------------
    for row in raw_encounters:
        patient = MasterPatient.objects.filter(patient_id=row.patient_id).first()
        hospital = MasterHospital.objects.filter(hospital_id=row.organization_id).first()

        out_of_pocket = None
        if row.total_claim_cost is not None and row.payer_coverage is not None:
            out_of_pocket = row.total_claim_cost - row.payer_coverage

        MasterEncounter.objects.update_or_create(
            encounter_id=row.encounter_id,
            defaults={
                "patient": patient,
                "hospital": hospital,
                "provider_id": row.provider_id,
                "payer_id": row.payer_id,
                "start": row.start,
                "stop": row.stop,
                "encounter_class": row.encounter_class,
                "code": row.code,
                "description": row.description,
                "base_encounter_cost": row.base_encounter_cost,
                "total_claim_cost": row.total_claim_cost,
                "payer_coverage": row.payer_coverage,
                "out_of_pocket": out_of_pocket,
                "source_batch": batch,
            }
        )

    BatchSyncLog.objects.create(
        batch=batch,
        action="sync_encounters",
        message="Encounters synced (test mode: first 100 rows)"
    )

    rebuild_hospital_summaries()

    batch.status = "synced"
    batch.synced_at = timezone.now()
    batch.sync_message = "Batch synced successfully (test mode: first 100 rows)"
    batch.save()


def normalize_score(value, min_val, max_val):
    if min_val == max_val:
        return 0.5
    return (value - min_val) / (max_val - min_val)


def rebuild_hospital_summaries():
    HospitalSummary.objects.all().delete()
    HospitalYearlySummary.objects.all().delete()
    HospitalMonthlySummary.objects.all().delete()

    hospital_ids = (
        MasterEncounter.objects
        .exclude(hospital=None)
        .values_list("hospital_id", flat=True)
        .distinct()
    )

    base_stats = []
    for hospital_id in hospital_ids:
        qs = MasterEncounter.objects.filter(hospital_id=hospital_id)

        total_visits = qs.count()
        total_patients = qs.exclude(patient=None).values("patient_id").distinct().count()
        avg_cost = qs.aggregate(v=Avg("total_claim_cost"))["v"] or 0
        avg_coverage = qs.aggregate(v=Avg("payer_coverage"))["v"] or 0
        avg_oop = qs.aggregate(v=Avg("out_of_pocket"))["v"] or 0
        sum_cost = qs.aggregate(v=Sum("total_claim_cost"))["v"] or 0
        sum_coverage = qs.aggregate(v=Sum("payer_coverage"))["v"] or 0
        coverage_ratio = (sum_coverage / sum_cost) if sum_cost else 0

        base_stats.append({
            "hospital_id": hospital_id,
            "total_visits": total_visits,
            "total_patients": total_patients,
            "avg_cost": avg_cost,
            "avg_coverage": avg_coverage,
            "avg_out_of_pocket": avg_oop,
            "coverage_ratio": coverage_ratio,
        })

    if not base_stats:
        return

    visit_vals = [x["total_visits"] for x in base_stats]
    cov_vals = [x["coverage_ratio"] for x in base_stats]
    oop_vals = [x["avg_out_of_pocket"] for x in base_stats]
    cost_vals = [x["avg_cost"] for x in base_stats]

    min_visit, max_visit = min(visit_vals), max(visit_vals)
    min_cov, max_cov = min(cov_vals), max(cov_vals)
    min_oop, max_oop = min(oop_vals), max(oop_vals)
    min_cost, max_cost = min(cost_vals), max(cost_vals)

    for item in base_stats:
        visit_score = normalize_score(item["total_visits"], min_visit, max_visit)
        cov_score = normalize_score(item["coverage_ratio"], min_cov, max_cov)
        oop_score = 1 - normalize_score(item["avg_out_of_pocket"], min_oop, max_oop)
        cost_score = 1 - normalize_score(item["avg_cost"], min_cost, max_cost)

        weighted_score = (
            0.35 * visit_score +
            0.30 * cov_score +
            0.20 * oop_score +
            0.15 * cost_score
        )

        HospitalSummary.objects.update_or_create(
            hospital_id=item["hospital_id"],
            defaults={
                "total_visits": item["total_visits"],
                "total_patients": item["total_patients"],
                "avg_cost": item["avg_cost"],
                "avg_coverage": item["avg_coverage"],
                "avg_out_of_pocket": item["avg_out_of_pocket"],
                "coverage_ratio": item["coverage_ratio"],
                "weighted_score": weighted_score,
            }
        )

    encounter_rows = MasterEncounter.objects.exclude(hospital=None).exclude(start=None)

    for enc in encounter_rows:
        HospitalYearlySummary.objects.update_or_create(
            hospital=enc.hospital,
            year=enc.start.year,
            defaults={}
        )

        HospitalMonthlySummary.objects.update_or_create(
            hospital=enc.hospital,
            year=enc.start.year,
            month=enc.start.month,
            defaults={}
        )

    for row in HospitalYearlySummary.objects.all():
        qs = MasterEncounter.objects.filter(
            hospital=row.hospital,
            start__year=row.year
        )
        row.total_visits = qs.count()
        row.avg_cost = qs.aggregate(v=Avg("total_claim_cost"))["v"] or 0
        row.avg_coverage = qs.aggregate(v=Avg("payer_coverage"))["v"] or 0
        row.avg_out_of_pocket = qs.aggregate(v=Avg("out_of_pocket"))["v"] or 0
        row.save()

    for row in HospitalMonthlySummary.objects.all():
        qs = MasterEncounter.objects.filter(
            hospital=row.hospital,
            start__year=row.year,
            start__month=row.month
        )
        row.total_visits = qs.count()
        row.avg_cost = qs.aggregate(v=Avg("total_claim_cost"))["v"] or 0
        row.avg_coverage = qs.aggregate(v=Avg("payer_coverage"))["v"] or 0
        row.avg_out_of_pocket = qs.aggregate(v=Avg("out_of_pocket"))["v"] or 0
        row.save()
