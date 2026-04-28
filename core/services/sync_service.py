# from django.db.models import Avg, Sum
# from django.utils import timezone
# from core.models import (
#     BatchSyncLog,
#     RawPatient, RawOrganization, RawEncounter,
#     MasterPatient, MasterHospital, MasterEncounter,
#     HospitalSummary, HospitalYearlySummary, HospitalMonthlySummary
# )


# def sync_batch_to_master(batch):
#     # -------------------------
#     # Patients
#     # -------------------------
#     raw_patients = RawPatient.objects.filter(batch=batch)
#     for row in raw_patients:
#         MasterPatient.objects.update_or_create(
#             patient_id=row.patient_id,
#             defaults={
#                 "birthdate": row.birthdate,
#                 "gender": row.gender,
#                 "race": row.race,
#                 "ethnicity": row.ethnicity,
#                 "city": row.city,
#                 "state": row.state,
#                 "zip_code": row.zip_code,
#                 "lat": row.lat,
#                 "lon": row.lon,
#                 "income": row.income,
#                 "healthcare_expenses": row.healthcare_expenses,
#                 "healthcare_coverage": row.healthcare_coverage,
#             }
#         )

#     BatchSyncLog.objects.create(
#         batch=batch,
#         action="sync_patients",
#         message="Patients synced"
#     )

#     # -------------------------
#     # Hospitals
#     # -------------------------
#     raw_orgs = RawOrganization.objects.filter(batch=batch)
#     for row in raw_orgs:
#         MasterHospital.objects.update_or_create(
#             hospital_id=row.organization_id,
#             defaults={
#                 "name": row.name,
#                 "city": row.city,
#                 "state": row.state,
#                 "zip_code": row.zip_code,
#                 "lat": row.lat,
#                 "lon": row.lon,
#                 "revenue": row.revenue,
#                 "utilization": row.utilization,
#             }
#         )

#     BatchSyncLog.objects.create(
#         batch=batch,
#         action="sync_hospitals",
#         message="Hospitals synced"
#     )

#     # -------------------------
#     # Encounters
#     # -------------------------
#     raw_encounters = RawEncounter.objects.filter(batch=batch)

#     for row in raw_encounters:
#         patient = MasterPatient.objects.filter(patient_id=row.patient_id).first()
#         hospital = MasterHospital.objects.filter(hospital_id=row.organization_id).first()

#         out_of_pocket = None
#         if row.total_claim_cost is not None and row.payer_coverage is not None:
#             out_of_pocket = row.total_claim_cost - row.payer_coverage

#         MasterEncounter.objects.update_or_create(
#             encounter_id=row.encounter_id,
#             defaults={
#                 "patient": patient,
#                 "hospital": hospital,
#                 "provider_id": row.provider_id,
#                 "payer_id": row.payer_id,
#                 "start": row.start,
#                 "stop": row.stop,
#                 "encounter_class": row.encounter_class,
#                 "code": row.code,
#                 "description": row.description,
#                 "base_encounter_cost": row.base_encounter_cost,
#                 "total_claim_cost": row.total_claim_cost,
#                 "payer_coverage": row.payer_coverage,
#                 "out_of_pocket": out_of_pocket,
#                 "source_batch": batch,
#             }
#         )

#     BatchSyncLog.objects.create(
#         batch=batch,
#         action="sync_encounters",
#         message="Encounters synced"
#     )

#     rebuild_hospital_summaries()

#     batch.status = "synced"
#     batch.synced_at = timezone.now()
#     batch.sync_message = "Batch synced successfully"
#     batch.save()


# def normalize_score(value, min_val, max_val):
#     if min_val == max_val:
#         return 0.5
#     return (value - min_val) / (max_val - min_val)


# def rebuild_hospital_summaries():
#     HospitalSummary.objects.all().delete()
#     HospitalYearlySummary.objects.all().delete()
#     HospitalMonthlySummary.objects.all().delete()

#     hospital_ids = (
#         MasterEncounter.objects
#         .exclude(hospital=None)
#         .values_list("hospital_id", flat=True)
#         .distinct()
#     )

#     base_stats = []
#     for hospital_id in hospital_ids:
#         qs = MasterEncounter.objects.filter(hospital_id=hospital_id)

#         total_visits = qs.count()
#         total_patients = qs.exclude(patient=None).values("patient_id").distinct().count()
#         avg_cost = qs.aggregate(v=Avg("total_claim_cost"))["v"] or 0
#         avg_coverage = qs.aggregate(v=Avg("payer_coverage"))["v"] or 0
#         avg_oop = qs.aggregate(v=Avg("out_of_pocket"))["v"] or 0
#         sum_cost = qs.aggregate(v=Sum("total_claim_cost"))["v"] or 0
#         sum_coverage = qs.aggregate(v=Sum("payer_coverage"))["v"] or 0
#         coverage_ratio = (sum_coverage / sum_cost) if sum_cost else 0

#         base_stats.append({
#             "hospital_id": hospital_id,
#             "total_visits": total_visits,
#             "total_patients": total_patients,
#             "avg_cost": avg_cost,
#             "avg_coverage": avg_coverage,
#             "avg_out_of_pocket": avg_oop,
#             "coverage_ratio": coverage_ratio,
#         })

#     if not base_stats:
#         return

#     visit_vals = [x["total_visits"] for x in base_stats]
#     cov_vals = [x["coverage_ratio"] for x in base_stats]
#     oop_vals = [x["avg_out_of_pocket"] for x in base_stats]
#     cost_vals = [x["avg_cost"] for x in base_stats]

#     min_visit, max_visit = min(visit_vals), max(visit_vals)
#     min_cov, max_cov = min(cov_vals), max(cov_vals)
#     min_oop, max_oop = min(oop_vals), max(oop_vals)
#     min_cost, max_cost = min(cost_vals), max(cost_vals)

#     for item in base_stats:
#         visit_score = normalize_score(item["total_visits"], min_visit, max_visit)
#         cov_score = normalize_score(item["coverage_ratio"], min_cov, max_cov)
#         oop_score = 1 - normalize_score(item["avg_out_of_pocket"], min_oop, max_oop)
#         cost_score = 1 - normalize_score(item["avg_cost"], min_cost, max_cost)

#         weighted_score = (
#             0.35 * visit_score +
#             0.30 * cov_score +
#             0.20 * oop_score +
#             0.15 * cost_score
#         )

#         HospitalSummary.objects.update_or_create(
#             hospital_id=item["hospital_id"],
#             defaults={
#                 "total_visits": item["total_visits"],
#                 "total_patients": item["total_patients"],
#                 "avg_cost": item["avg_cost"],
#                 "avg_coverage": item["avg_coverage"],
#                 "avg_out_of_pocket": item["avg_out_of_pocket"],
#                 "coverage_ratio": item["coverage_ratio"],
#                 "weighted_score": weighted_score,
#             }
#         )

#     encounter_rows = MasterEncounter.objects.exclude(hospital=None).exclude(start=None)

#     for enc in encounter_rows:
#         HospitalYearlySummary.objects.update_or_create(
#             hospital=enc.hospital,
#             year=enc.start.year,
#             defaults={}
#         )

#         HospitalMonthlySummary.objects.update_or_create(
#             hospital=enc.hospital,
#             year=enc.start.year,
#             month=enc.start.month,
#             defaults={}
#         )

#     for row in HospitalYearlySummary.objects.all():
#         qs = MasterEncounter.objects.filter(
#             hospital=row.hospital,
#             start__year=row.year
#         )
#         row.total_visits = qs.count()
#         row.avg_cost = qs.aggregate(v=Avg("total_claim_cost"))["v"] or 0
#         row.avg_coverage = qs.aggregate(v=Avg("payer_coverage"))["v"] or 0
#         row.avg_out_of_pocket = qs.aggregate(v=Avg("out_of_pocket"))["v"] or 0
#         row.save()

#     for row in HospitalMonthlySummary.objects.all():
#         qs = MasterEncounter.objects.filter(
#             hospital=row.hospital,
#             start__year=row.year,
#             start__month=row.month
#         )
#         row.total_visits = qs.count()
#         row.avg_cost = qs.aggregate(v=Avg("total_claim_cost"))["v"] or 0
#         row.avg_coverage = qs.aggregate(v=Avg("payer_coverage"))["v"] or 0
#         row.avg_out_of_pocket = qs.aggregate(v=Avg("out_of_pocket"))["v"] or 0
#         row.save()



## Below code for no loop

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
    # Patients - direct bulk insert
    # duplicates skipped by DB constraints
    # -------------------------
    raw_patients = list(
        RawPatient.objects.filter(batch=batch).only(
            "patient_id", "birthdate", "gender", "race", "ethnicity",
            "address", "county", "city", "state", "zip_code",
            "lat", "lon", "income", "healthcare_expenses", "healthcare_coverage"
        )
    )

    patient_objs = [
        MasterPatient(
            patient_id=row.patient_id,
            birthdate=row.birthdate,
            gender=row.gender,
            race=row.race,
            ethnicity=row.ethnicity,
            address=row.address,
            county=row.county,
            city=row.city,
            state=row.state,
            zip_code=row.zip_code,
            lat=row.lat,
            lon=row.lon,
            income=row.income,
            healthcare_expenses=row.healthcare_expenses,
            healthcare_coverage=row.healthcare_coverage,
        )
        for row in raw_patients
        if row.patient_id
    ]

    if patient_objs:
        MasterPatient.objects.bulk_create(
            patient_objs,
            batch_size=2000,
            ignore_conflicts=True
        )

    BatchSyncLog.objects.create(
        batch=batch,
        action="sync_patients",
        message=f"Patients sync completed. Raw rows processed: {len(raw_patients)}"
    )

    # -------------------------
    # Hospitals - direct bulk insert
    # duplicates skipped by DB constraints
    # -------------------------
    raw_orgs = list(
        RawOrganization.objects.filter(batch=batch).only(
            "organization_id", "name", "city", "state",
            "zip_code", "lat", "lon", "revenue", "utilization"
        )
    )

    hospital_objs = [
        MasterHospital(
            hospital_id=row.organization_id,
            name=row.name,
            city=row.city,
            state=row.state,
            zip_code=row.zip_code,
            lat=row.lat,
            lon=row.lon,
            revenue=row.revenue,
            utilization=row.utilization,
        )
        for row in raw_orgs
        if row.organization_id
    ]

    if hospital_objs:
        MasterHospital.objects.bulk_create(
            hospital_objs,
            batch_size=2000,
            ignore_conflicts=True
        )

    BatchSyncLog.objects.create(
        batch=batch,
        action="sync_hospitals",
        message=f"Hospitals sync completed. Raw rows processed: {len(raw_orgs)}"
    )

    # -------------------------
    # Build lookup maps once
    # -------------------------
    patient_map = {}
    for p in MasterPatient.objects.only("id", "patient_id", "state", "city", "address", "county"):
        key = (
            p.patient_id or "",
            p.state or "",
            p.city or "",
            p.address or "",
            p.county or "",
        )
        if key not in patient_map:
            patient_map[key] = p.id

    hospital_map = {
        h.hospital_id: h.id
        for h in MasterHospital.objects.only("id", "hospital_id")
        if h.hospital_id
    }

    # -------------------------
    # Encounters - direct bulk insert
    # duplicates skipped by DB constraints
    # -------------------------
    raw_encounters = list(
        RawEncounter.objects.filter(batch=batch).only(
            "encounter_id", "patient_id", "organization_id", "provider_id",
            "payer_id", "start", "stop", "encounter_class", "code",
            "description", "base_encounter_cost", "total_claim_cost", "payer_coverage"
        )
    )

    # Need patient identity from RawPatient for correct matching
    raw_patient_identity_map = {}
    for rp in RawPatient.objects.filter(batch=batch).only("patient_id", "state", "city", "address", "county"):
        raw_patient_identity_map[rp.patient_id] = (
            rp.patient_id or "",
            rp.state or "",
            rp.city or "",
            rp.address or "",
            rp.county or "",
        )

    encounter_objs = []
    for row in raw_encounters:
        patient_id_fk = None
        hospital_id_fk = None

        patient_identity_key = raw_patient_identity_map.get(
            row.patient_id,
            (row.patient_id or "", "", "", "", "")
        )
        patient_id_fk = patient_map.get(patient_identity_key)

        if row.organization_id:
            hospital_id_fk = hospital_map.get(row.organization_id)

        out_of_pocket = None
        if row.total_claim_cost is not None and row.payer_coverage is not None:
            out_of_pocket = row.total_claim_cost - row.payer_coverage

        if row.encounter_id:
            encounter_objs.append(
                MasterEncounter(
                    encounter_id=row.encounter_id,
                    patient_id=patient_id_fk,
                    hospital_id=hospital_id_fk,
                    provider_id=row.provider_id,
                    payer_id=row.payer_id,
                    start=row.start,
                    stop=row.stop,
                    encounter_class=row.encounter_class,
                    code=row.code,
                    description=row.description,
                    base_encounter_cost=row.base_encounter_cost,
                    total_claim_cost=row.total_claim_cost,
                    payer_coverage=row.payer_coverage,
                    out_of_pocket=out_of_pocket,
                    source_batch=batch,
                )
            )

    if encounter_objs:
        MasterEncounter.objects.bulk_create(
            encounter_objs,
            batch_size=2000,
            ignore_conflicts=True
        )

    BatchSyncLog.objects.create(
        batch=batch,
        action="sync_encounters",
        message=f"Encounters sync completed. Raw rows processed: {len(raw_encounters)}"
    )

    rebuild_hospital_summaries()

    batch.status = "synced"
    batch.synced_at = timezone.now()
    batch.sync_message = "Batch synced successfully using bulk insert mode"
    batch.save(update_fields=["status", "synced_at", "sync_message"])


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
