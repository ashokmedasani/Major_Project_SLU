from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta


class DeveloperProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="developer_profile")
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_developers",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    company_name = models.CharField(max_length=150, blank=True, null=True)
    role_name = models.CharField(max_length=150, blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} | approved={self.is_approved}"

class UploadBatch(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("validated", "Validated"),
        ("synced", "Synced"),
        ("unsynced", "Unsynced"),
        ("failed", "Failed"),
        ("recycle_bin", "Recycle Bin"),
        ("deleted", "Deleted"),
    ]

    name = models.CharField(max_length=150, blank=True, null=True)
    zip_file_name = models.CharField(max_length=255)
    extracted_path = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    validation_message = models.TextField(blank=True, null=True)
    sync_message = models.TextField(blank=True, null=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(blank=True, null=True)
    unsynced_at = models.DateTimeField(blank=True, null=True)
    moved_to_recycle_at = models.DateTimeField(blank=True, null=True)
    purge_after = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    sleep_protection_enabled = models.BooleanField(default=True)

    processing_started_at = models.DateTimeField(blank=True, null=True)
    processing_completed_at = models.DateTimeField(blank=True, null=True)
    estimated_processing_seconds = models.IntegerField(default=0)
    actual_processing_seconds = models.IntegerField(default=0)
    total_zip_size_mb = models.FloatField(default=0)

    def move_to_recycle_bin(self):
        now = timezone.now()
        self.status = "recycle_bin"
        self.is_active = False
        self.is_visible = False
        self.moved_to_recycle_at = now
        self.purge_after = now + timedelta(days=2)
        self.save(update_fields=[
            "status", "is_active", "is_visible", "moved_to_recycle_at", "purge_after"
        ])

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
    birthdate = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    race = models.CharField(max_length=100, blank=True, null=True)
    ethnicity = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    income = models.FloatField(blank=True, null=True)
    healthcare_expenses = models.FloatField(blank=True, null=True)
    healthcare_coverage = models.FloatField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["patient_id"]),
            models.Index(fields=["patient_id", "state", "city"]),
        ]


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
    patient_id = models.CharField(max_length=100, db_index=True)
    birthdate = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    race = models.CharField(max_length=100, blank=True, null=True)
    ethnicity = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    income = models.FloatField(blank=True, null=True)
    healthcare_expenses = models.FloatField(blank=True, null=True)
    healthcare_coverage = models.FloatField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient_id", "state", "city", "address", "county"],
                name="uniq_master_patient_identity"
            )
        ]
        indexes = [
            models.Index(fields=["patient_id", "state", "city"]),
        ]

    def __str__(self):
        return f"{self.patient_id} | {self.city}, {self.state}"


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
    age_at_visit = models.IntegerField(blank=True, null=True, db_index=True)
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


class ModelArtifact(models.Model):
    METRIC_CHOICES = [
        ("avg_cost", "Average Cost"),
        ("avg_oop", "Average Out Of Pocket"),
        ("avg_coverage", "Average Coverage"),
        ("visits", "Visits"),
        ("patients", "Patients"),
        ("hospitals", "Hospitals"),
    ]

    metric = models.CharField(max_length=50, choices=METRIC_CHOICES)
    model_name = models.CharField(max_length=50, default="random_forest")
    file_path = models.CharField(max_length=500)
    trained_from_months = models.IntegerField(default=36)
    forecast_months = models.IntegerField(default=18)
    source_note = models.CharField(max_length=255, default="master_data")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
