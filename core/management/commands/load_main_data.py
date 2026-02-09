from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction

import pandas as pd

from core.models import (
    Patient, Provider, Organization, Encounter, Claim,
    Observation, Immunization, Payer, PayerTransition, ClaimTransaction
)


def clean_record(d: dict) -> dict:
    # Convert NaN to None for JSONField
    out = {}
    for k, v in d.items():
        if pd.isna(v):
            out[k] = None
        else:
            out[k] = v
    return out


class Command(BaseCommand):
    help = "Load ALL main CSVs from Data/ into SQLite via Django models."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing data before loading.")
        parser.add_argument("--chunksize", type=int, default=5000, help="CSV chunk size (default 5000).")

    def handle(self, *args, **options):
        data_dir = settings.RAW_DATA_DIR
        chunksize = options["chunksize"]
        reset = options["reset"]

        files = {
            "patients": data_dir / "patients.csv",
            "organizations": data_dir / "organizations.csv",
            "providers": data_dir / "providers.csv",
            "encounters": data_dir / "encounters.csv",
            "payers": data_dir / "payers.csv",
            "payer_transitions": data_dir / "payer_transitions.csv",
            "claims": data_dir / "claims.csv",
            "observations": data_dir / "observations.csv",
            "immunizations": data_dir / "immunizations.csv",
            "claims_transactions": data_dir / "claims_transactions.csv",
        }

        for name, path in files.items():
            if not path.exists():
                raise FileNotFoundError(f"Missing {name} file: {path}")

        if reset:
            self.stdout.write(self.style.WARNING("Reset enabled: deleting existing rows..."))
            with transaction.atomic():
                ClaimTransaction.objects.all().delete()
                Observation.objects.all().delete()
                Immunization.objects.all().delete()
                Claim.objects.all().delete()
                PayerTransition.objects.all().delete()
                Encounter.objects.all().delete()
                Provider.objects.all().delete()
                Payer.objects.all().delete()
                Organization.objects.all().delete()
                Patient.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f"Loading from: {data_dir}"))

        # 1) Patients
        self._load_simple_pk_table(
            model=Patient,
            csv_path=files["patients"],
            id_col="Id",
            chunksize=chunksize
        )

        # 2) Organizations
        self._load_simple_pk_table(
            model=Organization,
            csv_path=files["organizations"],
            id_col="Id",
            chunksize=chunksize
        )

        # 3) Payers
        self._load_simple_pk_table(
            model=Payer,
            csv_path=files["payers"],
            id_col="Id",
            chunksize=chunksize
        )

        # 4) Providers (links to Organization if ORGANIZATION column exists)
        self._load_providers(files["providers"], chunksize)

        # 5) Encounters (links to Patient/Provider/Organization)
        self._load_encounters(files["encounters"], chunksize)

        # 6) Claims (links to Patient/Provider/Encounter via APPOINTMENTID)
        self._load_claims(files["claims"], chunksize)

        # 7) Observations (links to Patient/Encounter if ENCOUNTER exists)
        self._load_patient_encounter_table(
            model=Observation,
            csv_path=files["observations"],
            id_col="Id",
            patient_col="PATIENT",
            encounter_col="ENCOUNTER",
            chunksize=chunksize
        )

        # 8) Immunizations (links to Patient/Encounter)
        self._load_patient_encounter_table(
            model=Immunization,
            csv_path=files["immunizations"],
            id_col="Id",
            patient_col="PATIENT",
            encounter_col="ENCOUNTER",
            chunksize=chunksize
        )

        # 9) Payer transitions (links to Patient/Payer)
        self._load_payer_transitions(files["payer_transitions"], chunksize)

        # 10) Claim transactions (links to Claim + optional Patient/Provider/Encounter if present)
        self._load_claim_transactions(files["claims_transactions"], chunksize)

        self.stdout.write(self.style.SUCCESS("✅ All data loaded successfully."))

    # ---------- Helpers ----------

    def _load_simple_pk_table(self, model, csv_path, id_col, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                pk = row.get(id_col)
                if not pk:
                    continue
                objs.append(model(id=str(pk), raw=row))
            model.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"{model.__name__}: +{len(objs)} (total attempted: {total})")

    def _load_providers(self, csv_path, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            cols = set(chunk.columns)
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                pid = row.get("Id")
                if not pid:
                    continue
                org_id = str(row.get("ORGANIZATION")) if "ORGANIZATION" in cols and row.get("ORGANIZATION") else None
                objs.append(Provider(id=str(pid), organization_id=org_id, raw=row))
            Provider.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"Provider: +{len(objs)} (total attempted: {total})")

    def _load_encounters(self, csv_path, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                eid = row.get("Id")
                if not eid:
                    continue
                patient_id = str(row.get("PATIENT")) if row.get("PATIENT") else None
                provider_id = str(row.get("PROVIDER")) if row.get("PROVIDER") else None
                org_id = str(row.get("ORGANIZATION")) if row.get("ORGANIZATION") else None
                if not patient_id:
                    continue
                objs.append(
                    Encounter(
                        id=str(eid),
                        patient_id=patient_id,
                        provider_id=provider_id,
                        organization_id=org_id,
                        raw=row
                    )
                )
            Encounter.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"Encounter: +{len(objs)} (total attempted: {total})")

    def _load_claims(self, csv_path, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                cid = row.get("Id")
                if not cid:
                    continue
                patient_id = str(row.get("PATIENTID")) if row.get("PATIENTID") else None
                provider_id = str(row.get("PROVIDERID")) if row.get("PROVIDERID") else None
                encounter_id = str(row.get("APPOINTMENTID")) if row.get("APPOINTMENTID") else None
                if not patient_id:
                    continue
                objs.append(
                    Claim(
                        id=str(cid),
                        patient_id=patient_id,
                        provider_id=provider_id,
                        encounter_id=encounter_id,
                        raw=row
                    )
                )
            Claim.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"Claim: +{len(objs)} (total attempted: {total})")

    def _load_patient_encounter_table(self, model, csv_path, id_col, patient_col, encounter_col, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            cols = set(chunk.columns)
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                rid = row.get(id_col)
                if not rid:
                    continue
                patient_id = str(row.get(patient_col)) if row.get(patient_col) else None
                if not patient_id:
                    continue
                encounter_id = None
                if encounter_col in cols and row.get(encounter_col):
                    encounter_id = str(row.get(encounter_col))
                objs.append(model(id=str(rid), patient_id=patient_id, encounter_id=encounter_id, raw=row))
            model.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"{model.__name__}: +{len(objs)} (total attempted: {total})")

    def _load_payer_transitions(self, csv_path, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            cols = set(chunk.columns)
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                tid = row.get("Id")
                if not tid:
                    continue
                patient_id = str(row.get("PATIENT")) if row.get("PATIENT") else None
                payer_id = None
                # Synthea commonly uses "PAYER"
                if "PAYER" in cols and row.get("PAYER"):
                    payer_id = str(row.get("PAYER"))
                if not patient_id:
                    continue
                objs.append(PayerTransition(id=str(tid), patient_id=patient_id, payer_id=payer_id, raw=row))
            PayerTransition.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"PayerTransition: +{len(objs)} (total attempted: {total})")

    def _load_claim_transactions(self, csv_path, chunksize):
        total = 0
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            objs = []
            cols = set(chunk.columns)
            for row in chunk.to_dict(orient="records"):
                row = clean_record(row)
                tid = row.get("ID") or row.get("Id")  # your file uses "ID"
                if not tid:
                    continue
                claim_id = str(row.get("CLAIMID")) if row.get("CLAIMID") else None
                if not claim_id:
                    continue

                patient_id = str(row.get("PATIENTID")) if "PATIENTID" in cols and row.get("PATIENTID") else None
                provider_id = str(row.get("PROVIDERID")) if "PROVIDERID" in cols and row.get("PROVIDERID") else None

                # Some datasets store encounter/appointment id as APPOINTMENTID
                encounter_id = None
                if "APPOINTMENTID" in cols and row.get("APPOINTMENTID"):
                    encounter_id = str(row.get("APPOINTMENTID"))

                objs.append(
                    ClaimTransaction(
                        id=str(tid),
                        claim_id=claim_id,
                        patient_id=patient_id,
                        provider_id=provider_id,
                        encounter_id=encounter_id,
                        raw=row
                    )
                )
            ClaimTransaction.objects.bulk_create(objs, batch_size=chunksize, ignore_conflicts=True)
            total += len(objs)
            self.stdout.write(f"ClaimTransaction: +{len(objs)} (total attempted: {total})")
