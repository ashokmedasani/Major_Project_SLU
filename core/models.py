from django.db import models


class UploadBatch(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("validated", "Validated"),
        ("synced", "Synced"),
        ("failed", "Failed"),
        ("rolled_back", "Rolled Back"),
    ]

    name = models.CharField(max_length=150, blank=True, null=True)
    zip_file_name = models.CharField(max_length=255)
    extracted_path = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    validation_message = models.TextField(blank=True, null=True)
    sync_message = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Batch {self.id} - {self.zip_file_name}"


class BatchFile(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name="files")
    file_name = models.CharField(max_length=255)
    row_count = models.IntegerField(default=0)
    is_valid = models.BooleanField(default=False)
    message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.batch_id} - {self.file_name}"


class BatchSyncLog(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name="sync_logs")
    action = models.CharField(max_length=100)
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ---------------------------
# RAW TABLES
# ---------------------------

class RawPatient(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    patient_id = models.CharField(max_length=100, db_index=True)
    birthdate = models.DateField(blank=True, null=True)   # changed
    gender = models.CharField(max_length=10, blank=True, null=True)
    race = models.CharField(max_length=100, blank=True, null=True)
    ethnicity = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    income = models.FloatField(blank=True, null=True)
    healthcare_expenses = models.FloatField(blank=True, null=True)
    healthcare_coverage = models.FloatField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["patient_id"])]


class RawOrganization(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    organization_id = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    revenue = models.FloatField(blank=True, null=True)
    utilization = models.FloatField(blank=True, null=True)


class RawProvider(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    provider_id = models.CharField(max_length=100, db_index=True)
    organization_id = models.CharField(max_length=100, blank=True, null=True)
    speciality = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    encounters = models.FloatField(blank=True, null=True)
    procedures = models.FloatField(blank=True, null=True)


class RawEncounter(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    encounter_id = models.CharField(max_length=100, db_index=True)
    start = models.DateTimeField(blank=True, null=True)
    stop = models.DateTimeField(blank=True, null=True)
    patient_id = models.CharField(max_length=100, blank=True, null=True)
    organization_id = models.CharField(max_length=100, blank=True, null=True)
    provider_id = models.CharField(max_length=100, blank=True, null=True)
    payer_id = models.CharField(max_length=100, blank=True, null=True)
    encounter_class = models.CharField(max_length=100, blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    base_encounter_cost = models.FloatField(blank=True, null=True)
    total_claim_cost = models.FloatField(blank=True, null=True)
    payer_coverage = models.FloatField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["encounter_id"])]


class RawObservation(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    patient_id = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    value = models.TextField(blank=True, null=True)
    units = models.CharField(max_length=100, blank=True, null=True)
    obs_type = models.CharField(max_length=100, blank=True, null=True)


class RawImmunization(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    patient_id = models.CharField(max_length=100, blank=True, null=True)
    encounter_id = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    base_cost = models.FloatField(blank=True, null=True)


class RawClaim(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    claim_id = models.CharField(max_length=100, db_index=True)
    patient_id = models.CharField(max_length=100, blank=True, null=True)
    provider_id = models.CharField(max_length=100, blank=True, null=True)
    primary_insurance_id = models.CharField(max_length=100, blank=True, null=True)
    secondary_insurance_id = models.CharField(max_length=100, blank=True, null=True)
    service_date = models.DateTimeField(blank=True, null=True)
    status1 = models.CharField(max_length=100, blank=True, null=True)
    status2 = models.CharField(max_length=100, blank=True, null=True)
    statusp = models.CharField(max_length=100, blank=True, null=True)
    outstanding1 = models.FloatField(blank=True, null=True)
    outstanding2 = models.FloatField(blank=True, null=True)
    outstandingp = models.FloatField(blank=True, null=True)


class RawClaimTransaction(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    tx_id = models.CharField(max_length=100, db_index=True)
    claim_id = models.CharField(max_length=100, blank=True, null=True)
    patient_id = models.CharField(max_length=100, blank=True, null=True)
    provider_id = models.CharField(max_length=100, blank=True, null=True)
    supervising_provider_id = models.CharField(max_length=100, blank=True, null=True)
    tx_type = models.CharField(max_length=100, blank=True, null=True)
    amount = models.FloatField(blank=True, null=True)
    method = models.CharField(max_length=100, blank=True, null=True)
    from_date = models.DateTimeField(blank=True, null=True)
    to_date = models.DateTimeField(blank=True, null=True)
    place_of_service = models.CharField(max_length=100, blank=True, null=True)
    procedure_code = models.CharField(max_length=100, blank=True, null=True)
    units = models.FloatField(blank=True, null=True)
    unit_amount = models.FloatField(blank=True, null=True)
    payments = models.FloatField(blank=True, null=True)
    adjustments = models.FloatField(blank=True, null=True)
    transfers = models.FloatField(blank=True, null=True)
    outstanding = models.FloatField(blank=True, null=True)
    patient_insurance_id = models.CharField(max_length=100, blank=True, null=True)


class RawPayer(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    payer_id = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    ownership = models.CharField(max_length=100, blank=True, null=True)
    amount_covered = models.FloatField(blank=True, null=True)
    amount_uncovered = models.FloatField(blank=True, null=True)
    revenue = models.FloatField(blank=True, null=True)
    covered_encounters = models.FloatField(blank=True, null=True)
    uncovered_encounters = models.FloatField(blank=True, null=True)
    covered_immunizations = models.FloatField(blank=True, null=True)
    uncovered_immunizations = models.FloatField(blank=True, null=True)
    unique_customers = models.FloatField(blank=True, null=True)
    qols_avg = models.FloatField(blank=True, null=True)
    member_months = models.FloatField(blank=True, null=True)


class RawPayerTransition(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    patient_id = models.CharField(max_length=100, blank=True, null=True)
    payer_id = models.CharField(max_length=100, blank=True, null=True)
    secondary_payer = models.CharField(max_length=100, blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    member_id = models.CharField(max_length=100, blank=True, null=True)
    plan_ownership = models.CharField(max_length=100, blank=True, null=True)
    owner_name = models.CharField(max_length=255, blank=True, null=True)


# ---------------------------
# MASTER TABLES
# ---------------------------

class MasterPatient(models.Model):
    patient_id = models.CharField(max_length=100, unique=True)
    birthdate = models.DateField(blank=True, null=True)   # changed
    gender = models.CharField(max_length=10, blank=True, null=True)
    race = models.CharField(max_length=100, blank=True, null=True)
    ethnicity = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    income = models.FloatField(blank=True, null=True)
    healthcare_expenses = models.FloatField(blank=True, null=True)
    healthcare_coverage = models.FloatField(blank=True, null=True)


class MasterHospital(models.Model):
    hospital_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    revenue = models.FloatField(blank=True, null=True)
    utilization = models.FloatField(blank=True, null=True)


class MasterEncounter(models.Model):
    encounter_id = models.CharField(max_length=100, unique=True)
    patient = models.ForeignKey(MasterPatient, on_delete=models.SET_NULL, null=True, blank=True)
    hospital = models.ForeignKey(MasterHospital, on_delete=models.SET_NULL, null=True, blank=True)
    provider_id = models.CharField(max_length=100, blank=True, null=True)
    payer_id = models.CharField(max_length=100, blank=True, null=True)
    start = models.DateTimeField(blank=True, null=True)
    stop = models.DateTimeField(blank=True, null=True)
    age_at_visit = models.IntegerField(blank=True, null=True, db_index=True)  # added
    encounter_class = models.CharField(max_length=100, blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    base_encounter_cost = models.FloatField(blank=True, null=True)
    total_claim_cost = models.FloatField(blank=True, null=True)
    payer_coverage = models.FloatField(blank=True, null=True)
    out_of_pocket = models.FloatField(blank=True, null=True)
    source_batch = models.ForeignKey(UploadBatch, on_delete=models.SET_NULL, null=True, blank=True)


class HospitalSummary(models.Model):
    hospital = models.OneToOneField(MasterHospital, on_delete=models.CASCADE)
    total_visits = models.IntegerField(default=0)
    total_patients = models.IntegerField(default=0)
    avg_cost = models.FloatField(default=0)
    avg_coverage = models.FloatField(default=0)
    avg_out_of_pocket = models.FloatField(default=0)
    coverage_ratio = models.FloatField(default=0)
    weighted_score = models.FloatField(default=0)
    last_updated = models.DateTimeField(auto_now=True)


class HospitalYearlySummary(models.Model):
    hospital = models.ForeignKey(MasterHospital, on_delete=models.CASCADE)
    year = models.IntegerField()
    total_visits = models.IntegerField(default=0)
    avg_cost = models.FloatField(default=0)
    avg_coverage = models.FloatField(default=0)
    avg_out_of_pocket = models.FloatField(default=0)

    class Meta:
        unique_together = ("hospital", "year")


class HospitalMonthlySummary(models.Model):
    hospital = models.ForeignKey(MasterHospital, on_delete=models.CASCADE)
    year = models.IntegerField()
    month = models.IntegerField()
    total_visits = models.IntegerField(default=0)
    avg_cost = models.FloatField(default=0)
    avg_coverage = models.FloatField(default=0)
    avg_out_of_pocket = models.FloatField(default=0)

    class Meta:
        unique_together = ("hospital", "year", "month")