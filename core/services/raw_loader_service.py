import pandas as pd
from django.utils.dateparse import parse_datetime
from core.models import (
    BatchFile, RawPatient, RawEncounter, RawObservation, RawImmunization,
    RawProvider, RawOrganization, RawClaim, RawClaimTransaction,
    RawPayer, RawPayerTransition
)
from .constants import CHOSEN_COLS


def to_dt(value):
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(value, errors="coerce").to_pydatetime()
    except Exception:
        return None


def to_num(value):
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def load_csv(path):
    return pd.read_csv(path, low_memory=False)


def filter_columns(df, table_name):
    keep = [c for c in CHOSEN_COLS[table_name] if c in df.columns]
    return df[keep].copy()


def store_raw_batch(batch, found_files):
    for table_name in CHOSEN_COLS.keys():
        file_name = f"{table_name}.csv"
        path = found_files[file_name]
        df = load_csv(path)
        df = filter_columns(df, table_name)

        BatchFile.objects.update_or_create(
            batch=batch,
            file_name=file_name,
            defaults={
                "row_count": len(df),
                "is_valid": True,
                "message": "Loaded into raw table"
            }
        )

        if table_name == "patients":
            objs = [
                RawPatient(
                    batch=batch,
                    patient_id=row.get("Id"),
                    birthdate=to_dt(row.get("BIRTHDATE")),
                    gender=row.get("GENDER"),
                    race=row.get("RACE"),
                    ethnicity=row.get("ETHNICITY"),
                    city=row.get("CITY"),
                    state=row.get("STATE"),
                    zip_code=row.get("ZIP"),
                    lat=to_num(row.get("LAT")),
                    lon=to_num(row.get("LON")),
                    income=to_num(row.get("INCOME")),
                    healthcare_expenses=to_num(row.get("HEALTHCARE_EXPENSES")),
                    healthcare_coverage=to_num(row.get("HEALTHCARE_COVERAGE")),
                )
                for _, row in df.iterrows()
            ]
            RawPatient.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "organizations":
            objs = [
                RawOrganization(
                    batch=batch,
                    organization_id=row.get("Id"),
                    name=row.get("NAME"),
                    city=row.get("CITY"),
                    state=row.get("STATE"),
                    zip_code=row.get("ZIP"),
                    lat=to_num(row.get("LAT")),
                    lon=to_num(row.get("LON")),
                    revenue=to_num(row.get("REVENUE")),
                    utilization=to_num(row.get("UTILIZATION")),
                )
                for _, row in df.iterrows()
            ]
            RawOrganization.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "providers":
            objs = [
                RawProvider(
                    batch=batch,
                    provider_id=row.get("Id"),
                    organization_id=row.get("ORGANIZATION"),
                    speciality=row.get("SPECIALITY"),
                    city=row.get("CITY"),
                    state=row.get("STATE"),
                    zip_code=row.get("ZIP"),
                    lat=to_num(row.get("LAT")),
                    lon=to_num(row.get("LON")),
                    encounters=to_num(row.get("ENCOUNTERS")),
                    procedures=to_num(row.get("PROCEDURES")),
                )
                for _, row in df.iterrows()
            ]
            RawProvider.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "encounters":
            objs = [
                RawEncounter(
                    batch=batch,
                    encounter_id=row.get("Id"),
                    start=to_dt(row.get("START")),
                    stop=to_dt(row.get("STOP")),
                    patient_id=row.get("PATIENT"),
                    organization_id=row.get("ORGANIZATION"),
                    provider_id=row.get("PROVIDER"),
                    payer_id=row.get("PAYER"),
                    encounter_class=row.get("ENCOUNTERCLASS"),
                    code=row.get("CODE"),
                    description=row.get("DESCRIPTION"),
                    base_encounter_cost=to_num(row.get("BASE_ENCOUNTER_COST")),
                    total_claim_cost=to_num(row.get("TOTAL_CLAIM_COST")),
                    payer_coverage=to_num(row.get("PAYER_COVERAGE")),
                )
                for _, row in df.iterrows()
            ]
            RawEncounter.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "observations":
            objs = [
                RawObservation(
                    batch=batch,
                    patient_id=row.get("PATIENT"),
                    date=to_dt(row.get("DATE")),
                    code=row.get("CODE"),
                    description=row.get("DESCRIPTION"),
                    value=str(row.get("VALUE")) if row.get("VALUE") is not None else None,
                    units=row.get("UNITS"),
                    obs_type=row.get("TYPE"),
                )
                for _, row in df.iterrows()
            ]
            RawObservation.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "immunizations":
            objs = [
                RawImmunization(
                    batch=batch,
                    patient_id=row.get("PATIENT"),
                    encounter_id=row.get("ENCOUNTER"),
                    date=to_dt(row.get("DATE")),
                    code=row.get("CODE"),
                    description=row.get("DESCRIPTION"),
                    base_cost=to_num(row.get("BASE_COST")),
                )
                for _, row in df.iterrows()
            ]
            RawImmunization.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "claims":
            objs = [
                RawClaim(
                    batch=batch,
                    claim_id=row.get("Id"),
                    patient_id=row.get("PATIENTID"),
                    provider_id=row.get("PROVIDERID"),
                    primary_insurance_id=row.get("PRIMARYPATIENTINSURANCEID"),
                    secondary_insurance_id=row.get("SECONDARYPATIENTINSURANCEID"),
                    service_date=to_dt(row.get("SERVICEDATE")),
                    status1=row.get("STATUS1"),
                    status2=row.get("STATUS2"),
                    statusp=row.get("STATUSP"),
                    outstanding1=to_num(row.get("OUTSTANDING1")),
                    outstanding2=to_num(row.get("OUTSTANDING2")),
                    outstandingp=to_num(row.get("OUTSTANDINGP")),
                )
                for _, row in df.iterrows()
            ]
            RawClaim.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "claims_transactions":
            objs = [
                RawClaimTransaction(
                    batch=batch,
                    tx_id=row.get("ID"),
                    claim_id=row.get("CLAIMID"),
                    patient_id=row.get("PATIENTID"),
                    provider_id=row.get("PROVIDERID"),
                    supervising_provider_id=row.get("SUPERVISINGPROVIDERID"),
                    tx_type=row.get("TYPE"),
                    amount=to_num(row.get("AMOUNT")),
                    method=row.get("METHOD"),
                    from_date=to_dt(row.get("FROMDATE")),
                    to_date=to_dt(row.get("TODATE")),
                    place_of_service=row.get("PLACEOFSERVICE"),
                    procedure_code=row.get("PROCEDURECODE"),
                    units=to_num(row.get("UNITS")),
                    unit_amount=to_num(row.get("UNITAMOUNT")),
                    payments=to_num(row.get("PAYMENTS")),
                    adjustments=to_num(row.get("ADJUSTMENTS")),
                    transfers=to_num(row.get("TRANSFERS")),
                    outstanding=to_num(row.get("OUTSTANDING")),
                    patient_insurance_id=row.get("PATIENTINSURANCEID"),
                )
                for _, row in df.iterrows()
            ]
            RawClaimTransaction.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "payers":
            objs = [
                RawPayer(
                    batch=batch,
                    payer_id=row.get("Id"),
                    name=row.get("NAME"),
                    ownership=row.get("OWNERSHIP"),
                    amount_covered=to_num(row.get("AMOUNT_COVERED")),
                    amount_uncovered=to_num(row.get("AMOUNT_UNCOVERED")),
                    revenue=to_num(row.get("REVENUE")),
                    covered_encounters=to_num(row.get("COVERED_ENCOUNTERS")),
                    uncovered_encounters=to_num(row.get("UNCOVERED_ENCOUNTERS")),
                    covered_immunizations=to_num(row.get("COVERED_IMMUNIZATIONS")),
                    uncovered_immunizations=to_num(row.get("UNCOVERED_IMMUNIZATIONS")),
                    unique_customers=to_num(row.get("UNIQUE_CUSTOMERS")),
                    qols_avg=to_num(row.get("QOLS_AVG")),
                    member_months=to_num(row.get("MEMBER_MONTHS")),
                )
                for _, row in df.iterrows()
            ]
            RawPayer.objects.bulk_create(objs, batch_size=1000)

        elif table_name == "payer_transitions":
            objs = [
                RawPayerTransition(
                    batch=batch,
                    patient_id=row.get("PATIENT"),
                    payer_id=row.get("PAYER"),
                    secondary_payer=row.get("SECONDARY_PAYER"),
                    start_date=to_dt(row.get("START_DATE")),
                    end_date=to_dt(row.get("END_DATE")),
                    member_id=row.get("MEMBERID"),
                    plan_ownership=row.get("PLAN_OWNERSHIP"),
                    owner_name=row.get("OWNER_NAME"),
                )
                for _, row in df.iterrows()
            ]
            RawPayerTransition.objects.bulk_create(objs, batch_size=1000)