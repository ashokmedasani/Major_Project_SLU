from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Avg, Count
from django.contrib import messages

from django.db.models import Count, Avg, OuterRef, Subquery, Case, When, Value, CharField, IntegerField, F

from .forms import BatchUploadForm
from .models import UploadBatch, HospitalSummary, MasterHospital, MasterEncounter
from .services.zip_service import save_and_extract_zip
from .services.validation_service import validate_required_files, validate_required_columns
from .services.raw_loader_service import store_raw_batch
from .services.sync_service import sync_batch_to_master
from .services.rollback_service import rollback_batch
from .services.rebuild_service import rebuild_all_master_summaries
from .services.metrics_service import get_home_kpis

from django.shortcuts import render
from django.db.models import Count, Avg, OuterRef, Subquery
from django.db.models.functions import ExtractYear


from django.urls import reverse
from statistics import mean

import plotly.express as px
from plotly.offline import plot

import json
from django.utils.safestring import mark_safe
import pandas as pd
import plotly.express as px
from plotly.offline import plot
import plotly.graph_objects as go
from .services.forecasting import TimeSeriesForecaster

from collections import defaultdict

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .services.chatbot import get_initial_state, process_chat_message

import platform

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import BatchUploadForm, DeveloperLoginForm, DeveloperRequestAccessForm
from .models import (
    BatchFile,
    BatchSyncLog,
    DeveloperProfile,
    HospitalSummary,
    MasterEncounter,
    MasterHospital,
    MasterPatient,
    ModelArtifact,
    RawEncounter,
    RawOrganization,
    RawPatient,
    UploadBatch,
)

# keep these imports only if these files really exist in your project
from .services.decorators import developer_approved_required
from .services.raw_loader_service import store_raw_batch
from .services.rebuild_service import rebuild_all_master_summaries
from .services.sync_service import sync_batch_to_master
from .services.validation_service import validate_required_columns, validate_required_files
from .services.zip_service import save_and_extract_zip


# =========================================================
# HELPERS
# =========================================================

def normalize_text(value):
    return (value or "").strip().lower()


def get_or_create_master_patient_from_raw(raw_patient):
    identity = {
        "patient_id": raw_patient.patient_id,
        "state": normalize_text(getattr(raw_patient, "state", "")),
        "city": normalize_text(getattr(raw_patient, "city", "")),
        "address": normalize_text(getattr(raw_patient, "address", "")),
        "county": normalize_text(getattr(raw_patient, "county", "")),
    }

    patient, created = MasterPatient.objects.get_or_create(
        patient_id=identity["patient_id"],
        state=identity["state"],
        city=identity["city"],
        address=identity["address"],
        county=identity["county"],
        defaults={
            "birthdate": raw_patient.birthdate,
            "gender": raw_patient.gender,
            "race": raw_patient.race,
            "ethnicity": raw_patient.ethnicity,
            "zip_code": raw_patient.zip_code,
            "lat": raw_patient.lat,
            "lon": raw_patient.lon,
            "income": raw_patient.income,
            "healthcare_expenses": raw_patient.healthcare_expenses,
            "healthcare_coverage": raw_patient.healthcare_coverage,
        },
    )

    if not created:
        patient.birthdate = patient.birthdate or raw_patient.birthdate
        patient.gender = patient.gender or raw_patient.gender
        patient.race = patient.race or raw_patient.race
        patient.ethnicity = patient.ethnicity or raw_patient.ethnicity
        patient.zip_code = patient.zip_code or raw_patient.zip_code
        patient.lat = patient.lat or raw_patient.lat
        patient.lon = patient.lon or raw_patient.lon
        patient.income = patient.income or raw_patient.income
        patient.healthcare_expenses = patient.healthcare_expenses or raw_patient.healthcare_expenses
        patient.healthcare_coverage = patient.healthcare_coverage or raw_patient.healthcare_coverage
        patient.save()

    return patient


def keep_system_awake_start():
    if platform.system().lower() == "windows":
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_AWAYMODE_REQUIRED = 0x00000040
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
        except Exception:
            pass


def keep_system_awake_stop():
    if platform.system().lower() == "windows":
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass


# =========================================================
# DEVELOPER AUTH
# =========================================================

@require_http_methods(["GET", "POST"])
def developer_login(request):
    if request.user.is_authenticated:
        profile = getattr(request.user, "developer_profile", None)
        if request.user.is_superuser or (profile and profile.is_approved):
            return redirect("developer_dashboard")

    form = DeveloperLoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )

        if user is None:
            messages.error(request, "Invalid username or password.")
        else:
            profile = getattr(user, "developer_profile", None)
            if user.is_superuser or (profile and profile.is_approved):
                login(request, user)
                messages.success(request, "Logged in successfully.")
                return redirect("developer_dashboard")
            messages.warning(request, "Your developer access is not approved yet.")

    return render(request, "core/developer/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def developer_request_access(request):
    form = DeveloperRequestAccessForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()

            DeveloperProfile.objects.get_or_create(
                user=user,
                defaults={"is_approved": False},
            )

        messages.success(request, "Access request submitted. Wait for approval.")
        return redirect("developer_login")

    return render(request, "core/developer/request_access.html", {"form": form})


@login_required
def developer_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("developer_login")


# =========================================================
# DEVELOPER DASHBOARDS
# =========================================================

@login_required
@developer_approved_required
def developer_dashboard(request):
    context = {
        "total_batches": UploadBatch.objects.exclude(status="deleted").count(),
        "synced_batches": UploadBatch.objects.filter(status="synced").count(),
        "unsynced_batches": UploadBatch.objects.filter(status="unsynced").count(),
        "recycle_batches": UploadBatch.objects.filter(status="recycle_bin").count(),
        "total_patients": MasterPatient.objects.count(),
        "total_hospitals": MasterHospital.objects.count(),
        "total_encounters": MasterEncounter.objects.count(),
        "artifacts": ModelArtifact.objects.filter(is_active=True)[:10],
        "recent_batches": UploadBatch.objects.exclude(status="deleted").order_by("-uploaded_at")[:10],
    }
    return render(request, "core/developer/dashboard.html", context)


@login_required
@developer_approved_required
def developer_data_dashboard(request):
    batches = UploadBatch.objects.exclude(status="deleted").order_by("-uploaded_at")
    hospitals = HospitalSummary.objects.select_related("hospital").order_by("-weighted_score")[:20]

    context = {
        "batches": batches,
        "hospitals": hospitals,
    }
    return render(request, "core/developer/data_dashboard.html", context)


# =========================================================
# BATCH UPLOAD / HISTORY / DETAIL
# =========================================================

@login_required
@developer_approved_required
@require_http_methods(["GET", "POST"])
def batch_upload_view(request):
    form = BatchUploadForm(request.POST or None, request.FILES or None)

    def format_seconds(seconds):
        seconds = int(seconds or 0)
        mins, secs = divmod(seconds, 60)
        if mins > 0:
            return f"{mins} min {secs} sec"
        return f"{secs} sec"

    def estimate_processing_seconds(zip_size_mb):
        """
        Simple estimate logic:
        - base time
        - plus additional time per MB
        You can tune this later based on real batch history.
        """
        base_seconds = 20
        per_mb_seconds = 4
        estimated = base_seconds + int(zip_size_mb * per_mb_seconds)

        if estimated < 20:
            estimated = 20
        return estimated

    if request.method == "POST" and form.is_valid():
        zip_file = form.cleaned_data["zip_file"]
        batch_name = form.cleaned_data.get("batch_name") or zip_file.name

        zip_size_mb = round(zip_file.size / (1024 * 1024), 2)
        estimated_seconds = estimate_processing_seconds(zip_size_mb)

        keep_system_awake_start()
        batch = None

        try:
            batch = UploadBatch.objects.create(
                name=batch_name,
                zip_file_name=zip_file.name,
                status="uploaded",
                is_active=True,
                is_visible=True,
                total_zip_size_mb=zip_size_mb,
                estimated_processing_seconds=estimated_seconds,
                processing_started_at=timezone.now(),
            )

            BatchSyncLog.objects.create(
                batch=batch,
                action="upload",
                message=(
                    f"ZIP uploaded. Extraction started. "
                    f"Estimated processing time: {format_seconds(estimated_seconds)}. "
                    f"ZIP size: {zip_size_mb} MB."
                ),
            )

            extracted = save_and_extract_zip(zip_file, batch_name=batch_name)
            batch.extracted_path = str(extracted["batch_dir"])
            batch.save(update_fields=["extracted_path"])

            file_validation = validate_required_files(extracted["batch_dir"])
            if not file_validation["is_valid"]:
                batch.status = "failed"
                batch.validation_message = f"Missing files: {file_validation.get('missing_files', [])}"
                batch.processing_completed_at = timezone.now()
                if batch.processing_started_at and batch.processing_completed_at:
                    batch.actual_processing_seconds = int(
                        (batch.processing_completed_at - batch.processing_started_at).total_seconds()
                    )
                batch.save(update_fields=[
                    "status",
                    "validation_message",
                    "processing_completed_at",
                    "actual_processing_seconds",
                ])

                BatchSyncLog.objects.create(
                    batch=batch,
                    action="validation_failed",
                    message=batch.validation_message,
                )
                messages.error(request, batch.validation_message)
                return redirect("batch_history")

            column_validation = validate_required_columns(file_validation["found_files"])
            if not column_validation["is_valid"]:
                batch.status = "failed"
                batch.validation_message = "Required columns missing."
                batch.processing_completed_at = timezone.now()
                if batch.processing_started_at and batch.processing_completed_at:
                    batch.actual_processing_seconds = int(
                        (batch.processing_completed_at - batch.processing_started_at).total_seconds()
                    )
                batch.save(update_fields=[
                    "status",
                    "validation_message",
                    "processing_completed_at",
                    "actual_processing_seconds",
                ])

                BatchSyncLog.objects.create(
                    batch=batch,
                    action="validation_failed",
                    message="Required columns missing.",
                )
                messages.error(request, batch.validation_message)
                return redirect("batch_history")

            store_raw_batch(batch, file_validation["found_files"])

            batch.status = "validated"
            batch.validation_message = "Batch validated and raw data stored."
            batch.processing_completed_at = timezone.now()
            if batch.processing_started_at and batch.processing_completed_at:
                batch.actual_processing_seconds = int(
                    (batch.processing_completed_at - batch.processing_started_at).total_seconds()
                )

            batch.save(update_fields=[
                "status",
                "validation_message",
                "processing_completed_at",
                "actual_processing_seconds",
            ])

            BatchSyncLog.objects.create(
                batch=batch,
                action="validated",
                message=(
                    "Batch validated successfully and raw data stored. "
                    f"Actual processing time: {format_seconds(batch.actual_processing_seconds)}."
                ),
            )

            messages.success(
                request,
                f"Batch uploaded and validated successfully. Estimated time was {format_seconds(estimated_seconds)}."
            )
            return redirect("batch_detail", batch_id=batch.id)

        except Exception as e:
            if batch:
                batch.status = "failed"
                batch.validation_message = str(e)
                batch.processing_completed_at = timezone.now()
                if batch.processing_started_at and batch.processing_completed_at:
                    batch.actual_processing_seconds = int(
                        (batch.processing_completed_at - batch.processing_started_at).total_seconds()
                    )
                batch.save(update_fields=[
                    "status",
                    "validation_message",
                    "processing_completed_at",
                    "actual_processing_seconds",
                ])

                BatchSyncLog.objects.create(
                    batch=batch,
                    action="upload_failed",
                    message=str(e),
                )
            messages.error(request, f"Upload failed: {e}")

        finally:
            keep_system_awake_stop()

    recent_avg_seconds = (
        UploadBatch.objects.filter(actual_processing_seconds__gt=0)
        .order_by("-uploaded_at")
        .values_list("actual_processing_seconds", flat=True)[:5]
    )

    recent_avg_seconds = list(recent_avg_seconds)
    avg_processing_seconds = int(sum(recent_avg_seconds) / len(recent_avg_seconds)) if recent_avg_seconds else 45

    context = {
        "form": form,
        "avg_processing_seconds": avg_processing_seconds,
    }
    return render(request, "core/developer/batch_upload.html", context)


@login_required
@developer_approved_required
def batch_history_view(request):
    batches = UploadBatch.objects.exclude(status="deleted").order_by("-uploaded_at")
    return render(request, "core/developer/batch_history.html", {"batches": batches})


@login_required
@developer_approved_required
def batch_detail_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)
    context = {
        "batch": batch,
        "files": batch.files.all(),
        "logs": batch.sync_logs.order_by("-created_at"),
    }
    return render(request, "core/developer/batch_detail.html", context)


# =========================================================
# BATCH ACTIONS
# =========================================================

@login_required
@developer_approved_required
@require_http_methods(["POST"])
def sync_batch_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)

    if batch.status in ["recycle_bin", "deleted"]:
        messages.error(request, "This batch cannot be synced.")
        return redirect("batch_detail", batch_id=batch.id)

    if batch.status == "synced":
        messages.info(request, "This batch is already synced.")
        return redirect("batch_detail", batch_id=batch.id)

    keep_system_awake_start()
    try:
        sync_batch_to_master(batch)

        batch.status = "synced"
        batch.synced_at = timezone.now()
        batch.is_active = True
        batch.is_visible = True
        batch.sync_message = "Batch synced into master data and published to user-facing layer."
        batch.save(
            update_fields=[
                "status",
                "synced_at",
                "is_active",
                "is_visible",
                "sync_message",
            ]
        )

        BatchSyncLog.objects.create(
            batch=batch,
            action="sync",
            message="Batch synced to master/user layer.",
        )

        messages.success(request, "Batch synced successfully.")

    except Exception as e:
        batch.status = "failed"
        batch.sync_message = str(e)
        batch.save(update_fields=["status", "sync_message"])

        BatchSyncLog.objects.create(
            batch=batch,
            action="sync_failed",
            message=str(e),
        )

        messages.error(request, f"Sync failed: {e}")

    finally:
        keep_system_awake_stop()

    return redirect("batch_detail", batch_id=batch.id)


@login_required
@developer_approved_required
@require_http_methods(["POST"])
def unsync_batch_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)

    if batch.status != "synced":
        messages.info(request, "This batch is not currently synced.")
        return redirect("batch_detail", batch_id=batch.id)

    keep_system_awake_start()
    try:
        MasterEncounter.objects.filter(source_batch=batch).delete()
        rebuild_all_master_summaries()

        batch.status = "unsynced"
        batch.unsynced_at = timezone.now()
        batch.sync_message = "Batch removed from user-facing layer. Raw data preserved."
        batch.save(update_fields=["status", "unsynced_at", "sync_message"])

        BatchSyncLog.objects.create(
            batch=batch,
            action="unsync",
            message="Batch removed from user-facing layer. Raw data preserved.",
        )

        messages.success(request, "Batch unsynced. Raw data still exists in backend.")

    except Exception as e:
        BatchSyncLog.objects.create(
            batch=batch,
            action="unsync_failed",
            message=str(e),
        )
        messages.error(request, f"Unsync failed: {e}")

    finally:
        keep_system_awake_stop()

    return redirect("batch_detail", batch_id=batch.id)


@login_required
@developer_approved_required
@require_http_methods(["POST"])
def recycle_batch_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)

    batch.move_to_recycle_bin()

    BatchSyncLog.objects.create(
        batch=batch,
        action="recycle",
        message="Batch moved to recycle bin for 2 days.",
    )

    messages.success(request, "Batch moved to recycle bin.")
    return redirect("batch_history")


@login_required
@developer_approved_required
@require_http_methods(["POST"])
def restore_batch_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)

    if batch.status == "recycle_bin":
        batch.status = "unsynced"
        batch.is_active = True
        batch.is_visible = True
        batch.moved_to_recycle_at = None
        batch.purge_after = None
        batch.save(
            update_fields=[
                "status",
                "is_active",
                "is_visible",
                "moved_to_recycle_at",
                "purge_after",
            ]
        )

        BatchSyncLog.objects.create(
            batch=batch,
            action="restore",
            message="Batch restored from recycle bin.",
        )

        messages.success(request, "Batch restored.")
    else:
        messages.info(request, "Only recycle bin batches can be restored.")

    return redirect("batch_detail", batch_id=batch.id)


@login_required
@developer_approved_required
@require_http_methods(["POST"])
def delete_batch_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)

    keep_system_awake_start()
    try:
        MasterEncounter.objects.filter(source_batch=batch).delete()

        RawPatient.objects.filter(batch=batch).delete()
        RawEncounter.objects.filter(batch=batch).delete()
        RawOrganization.objects.filter(batch=batch).delete()

        BatchFile.objects.filter(batch=batch).delete()

        batch.status = "deleted"
        batch.is_active = False
        batch.is_visible = False
        batch.save(update_fields=["status", "is_active", "is_visible"])

        BatchSyncLog.objects.create(
            batch=batch,
            action="delete",
            message="Batch permanently deleted.",
        )

        rebuild_all_master_summaries()
        messages.success(request, "Batch permanently deleted.")

    except Exception as e:
        BatchSyncLog.objects.create(
            batch=batch,
            action="delete_failed",
            message=str(e),
        )
        messages.error(request, f"Delete failed: {e}")

    finally:
        keep_system_awake_stop()

    return redirect("batch_history")



from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from core.models import MasterEncounter
from core.services.forecasting import TimeSeriesForecaster, save_forecast_pickle


@login_required
def prediction_dashboard(request):
    return render(request, "core/developer/prediction_dashboard.html")


@login_required
def train_all_models(request):
    encounters = MasterEncounter.objects.all()

    # REQUIRED METRICS (must train both models)
    required_metrics = ["visits", "patients", "hospitals"]

    # OPTIONAL METRICS (GB optional)
    optional_metrics = ["avg_cost", "avg_coverage", "avg_oop"]

    try:
        # -------- REQUIRED --------
        for metric in required_metrics:
            for model_name in ["random_forest", "xgboost"]:
                forecaster = TimeSeriesForecaster(
                    encounters_qs=encounters,
                    model_name=model_name
                )

                result = forecaster.run(metric=metric)

                payload = {
                    "train": result.train_monthly,
                    "future": result.future_monthly,
                    "metric": metric,
                    "model": model_name
                }

                save_forecast_pickle(metric, model_name, payload)

        # -------- OPTIONAL --------
        for metric in optional_metrics:
            # Random Forest always
            forecaster = TimeSeriesForecaster(
                encounters_qs=encounters,
                model_name="random_forest"
            )

            result = forecaster.run(metric=metric)

            payload = {
                "train": result.train_monthly,
                "future": result.future_monthly,
                "metric": metric,
                "model": "random_forest"
            }

            save_forecast_pickle(metric, "random_forest", payload)

            # XGBoost optional
            forecaster = TimeSeriesForecaster(
                encounters_qs=encounters,
                model_name="xgboost"
            )

            result = forecaster.run(metric=metric)

            payload = {
                "train": result.train_monthly,
                "future": result.future_monthly,
                "metric": metric,
                "model": "xgboost"
            }

            save_forecast_pickle(metric, "xgboost", payload)

        messages.success(request, "All models trained and PKL files created successfully!")

    except Exception as e:
        messages.error(request, f"Training failed: {str(e)}")

    return redirect("prediction_dashboard")
# -----------------------
# Developer Pages
# -----------------------

# def developer_dashboard(request):
#     batches = UploadBatch.objects.order_by("-uploaded_at")[:10]
#     return render(request, "core/developer_dashboard.html", {"batches": batches})


# def batch_upload_view(request):
#     form = BatchUploadForm()

#     if request.method == "POST":
#         form = BatchUploadForm(request.POST, request.FILES)
#         if form.is_valid():
#             zip_file = form.cleaned_data["zip_file"]
#             batch_name = form.cleaned_data.get("batch_name")

#             batch = UploadBatch.objects.create(
#                 name=batch_name,
#                 zip_file_name=zip_file.name,
#                 status="uploaded"
#             )

#             extracted = save_and_extract_zip(zip_file, batch_name=batch_name)
#             batch.extracted_path = str(extracted["batch_dir"])
#             batch.save()

#             file_validation = validate_required_files(extracted["batch_dir"])
#             if not file_validation["is_valid"]:
#                 batch.status = "failed"
#                 batch.validation_message = f"Missing files: {file_validation['missing_files']}"
#                 batch.save()
#                 messages.error(request, batch.validation_message)
#                 return redirect("batch_history")

#             column_validation = validate_required_columns(file_validation["found_files"])
#             if not column_validation["is_valid"]:
#                 batch.status = "failed"
#                 batch.validation_message = "Required columns missing"
#                 batch.save()
#                 messages.error(request, batch.validation_message)
#                 return redirect("batch_history")

#             store_raw_batch(batch, file_validation["found_files"])
#             batch.status = "validated"
#             batch.validation_message = "Batch validated and raw data stored"
#             batch.save()

#             messages.success(request, "Batch uploaded and validated successfully.")
#             return redirect("batch_detail", batch_id=batch.id)

#     return render(request, "core/batch_upload.html", {"form": form})


# def batch_history_view(request):
#     batches = UploadBatch.objects.order_by("-uploaded_at")
#     return render(request, "core/batch_history.html", {"batches": batches})


# def batch_detail_view(request, batch_id):
#     batch = get_object_or_404(UploadBatch, id=batch_id)
#     return render(request, "core/batch_detail.html", {"batch": batch})


# def sync_batch_view(request, batch_id):
#     batch = get_object_or_404(UploadBatch, id=batch_id)
#     sync_batch_to_master(batch)
#     messages.success(request, "Batch synced into master data.")
#     return redirect("batch_detail", batch_id=batch.id)


# def rollback_batch_view(request, batch_id):
#     batch = get_object_or_404(UploadBatch, id=batch_id)
#     rollback_batch(batch, delete_storage=True, delete_raw_data=True)
#     messages.warning(request, "Batch rolled back and storage deleted.")
#     return redirect("batch_history")


# def rebuild_master_view(request):
#     rebuild_all_master_summaries()
#     messages.success(request, "Master summaries rebuilt.")
#     return redirect("developer_dashboard")


# -----------------------
# User Pages
# -----------------------
# -----------------------
# User Pages
# -----------------------

import json
from datetime import date

from django.db.models import Avg, Count, F, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render

from .forms import FilterForm
from .models import MasterEncounter, MasterHospital, MasterPatient, RawPayer


def home_view(request):
    selected_state = request.GET.get("state", "")
    selected_city = request.GET.get("city", "")

    # ---------------------------------
    # Build payer lookup from RawPayer
    # payer_id -> payer_name
    # ---------------------------------
    payer_rows = (
        RawPayer.objects.exclude(payer_id__isnull=True)
        .exclude(payer_id__exact="")
        .values("payer_id", "name")
    )

    payer_id_to_name = {}
    payer_name_to_ids = {}

    for row in payer_rows:
        pid = row["payer_id"]
        pname = (row["name"] or "Unknown").strip()

        if pid not in payer_id_to_name:
            payer_id_to_name[pid] = pname

        if pname not in payer_name_to_ids:
            payer_name_to_ids[pname] = []

        if pid not in payer_name_to_ids[pname]:
            payer_name_to_ids[pname].append(pid)

    # ---------------------------------
    # Filter dropdown choices
    # ---------------------------------
    state_choices = list(
        MasterHospital.objects.exclude(state__isnull=True)
        .exclude(state__exact="")
        .values_list("state", "state")
        .distinct()
        .order_by("state")
    )

    city_choices = []
    if selected_state:
        city_choices = list(
            MasterHospital.objects.filter(state=selected_state)
            .exclude(city__isnull=True)
            .exclude(city__exact="")
            .values_list("city", "city")
            .distinct()
            .order_by("city")
        )

    filters = FilterForm(
        request.GET or None,
        state_choices=state_choices,
        city_choices=city_choices,
    )

    # ---------------------------------
    # Base queryset
    # ---------------------------------
    queryset = MasterEncounter.objects.select_related("hospital", "patient").all()

    # ---------------------------------
    # Apply filters
    # ---------------------------------
    if filters.is_bound and filters.is_valid():
        state = filters.cleaned_data.get("state")
        city = filters.cleaned_data.get("city")

        if state:
            queryset = queryset.filter(hospital__state=state)

            if city:
                queryset = queryset.filter(hospital__city=city)

    # ---------------------------------
    # KPIs
    # IMPORTANT:
    # Count patient uniqueness using patient_id + patient.state + patient.city
    # not only patient FK id
    # ---------------------------------
    total_hospitals = queryset.values("hospital").distinct().count()

    total_patients = (
        queryset.filter(patient__isnull=False)
        .annotate(
            patient_identity_id=Coalesce(F("patient__patient_id"), Value("")),
            patient_identity_state=Coalesce(F("patient__state"), Value("")),
            patient_identity_city=Coalesce(F("patient__city"), Value("")),
        )
        .values(
            "patient_identity_id",
            "patient_identity_state",
            "patient_identity_city",
        )
        .distinct()
        .count()
    )

    total_visits = queryset.count()
    avg_cost = queryset.aggregate(avg=Avg("total_claim_cost"))["avg"] or 0
    avg_coverage = queryset.aggregate(avg=Avg("payer_coverage"))["avg"] or 0

    # ---------------------------------
    # Filtered patient identity set
    # Use patient business identity, not only row id
    # ---------------------------------
    patient_identity_rows = list(
        queryset.filter(patient__isnull=False)
        .annotate(
            patient_identity_id=Coalesce(F("patient__patient_id"), Value("")),
            patient_identity_state=Coalesce(F("patient__state"), Value("")),
            patient_identity_city=Coalesce(F("patient__city"), Value("")),
        )
        .values(
            "patient_identity_id",
            "patient_identity_state",
            "patient_identity_city",
        )
        .distinct()
    )

    patient_identity_set = {
        (
            row["patient_identity_id"] or "",
            row["patient_identity_state"] or "",
            row["patient_identity_city"] or "",
        )
        for row in patient_identity_rows
    }

    filtered_patients = list(
        MasterPatient.objects.all().values(
            "id",
            "patient_id",
            "state",
            "city",
            "gender",
            "birthdate",
        )
    )

    filtered_patients = [
        p for p in filtered_patients
        if (
            (p["patient_id"] or ""),
            (p["state"] or ""),
            (p["city"] or ""),
        ) in patient_identity_set
    ]

    # ---------------------------------
    # Gender chart
    # Count unique patients by business identity
    # ---------------------------------
    gender_counts = {}
    seen_gender_keys = set()

    for patient in filtered_patients:
        identity_key = (
            patient["patient_id"] or "",
            patient["state"] or "",
            patient["city"] or "",
        )

        if identity_key in seen_gender_keys:
            continue

        seen_gender_keys.add(identity_key)
        gender = patient["gender"] or "Unknown"
        gender_counts[gender] = gender_counts.get(gender, 0) + 1

    gender_chart = json.dumps({
        "labels": list(gender_counts.keys()),
        "values": list(gender_counts.values()),
    })

    # ---------------------------------
    # Age group chart
    # Count unique patients by business identity
    # ---------------------------------
    age_buckets = {
        "0-18": 0,
        "19-35": 0,
        "36-50": 0,
        "51-65": 0,
        "66+": 0,
    }

    today = date.today()
    seen_age_keys = set()

    for patient in filtered_patients:
        identity_key = (
            patient["patient_id"] or "",
            patient["state"] or "",
            patient["city"] or "",
        )

        if identity_key in seen_age_keys:
            continue

        seen_age_keys.add(identity_key)

        birthdate = patient["birthdate"]
        if not birthdate:
            continue

        age = today.year - birthdate.year - (
            (today.month, today.day) < (birthdate.month, birthdate.day)
        )

        if age <= 18:
            age_buckets["0-18"] += 1
        elif age <= 35:
            age_buckets["19-35"] += 1
        elif age <= 50:
            age_buckets["36-50"] += 1
        elif age <= 65:
            age_buckets["51-65"] += 1
        else:
            age_buckets["66+"] += 1

    age_chart = json.dumps({
        "labels": list(age_buckets.keys()),
        "values": list(age_buckets.values()),
    })

    # ---------------------------------
    # Top insurance payer chart
    # Aggregate by payer_id then convert to payer name
    # Count unique patient identities per payer
    # ---------------------------------
    payer_rows = list(
        queryset.exclude(payer_id__isnull=True)
        .exclude(payer_id__exact="")
        .annotate(
            patient_identity_id=Coalesce(F("patient__patient_id"), Value("")),
            patient_identity_state=Coalesce(F("patient__state"), Value("")),
            patient_identity_city=Coalesce(F("patient__city"), Value("")),
        )
        .values(
            "payer_id",
            "patient_identity_id",
            "patient_identity_state",
            "patient_identity_city",
        )
    )

    payer_patient_sets = {}

    for row in payer_rows:
        payer_id = row["payer_id"]
        patient_key = (
            row["patient_identity_id"] or "",
            row["patient_identity_state"] or "",
            row["patient_identity_city"] or "",
        )

        if not payer_id:
            continue

        if payer_id not in payer_patient_sets:
            payer_patient_sets[payer_id] = set()

        payer_patient_sets[payer_id].add(patient_key)

    payer_totals_by_name = {}
    for payer_id, patient_set in payer_patient_sets.items():
        pname = payer_id_to_name.get(payer_id, "Unknown")
        payer_totals_by_name[pname] = payer_totals_by_name.get(pname, 0) + len(patient_set)

    payer_top = sorted(
        payer_totals_by_name.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    payer_chart = json.dumps({
        "labels": [x[0] for x in payer_top],
        "values": [x[1] for x in payer_top],
    })

        # ---------------------------------
    # State-wise hospital chart
    # Count distinct hospitals by state
    # ---------------------------------
    state_hospital_qs = (
        MasterHospital.objects.exclude(state__isnull=True)
        .exclude(state__exact="")
        .values("state")
        .annotate(total_hospitals=Count("hospital_id", distinct=True))
        .order_by("-total_hospitals", "state")
    )

    state_hospital_labels = [row["state"] for row in state_hospital_qs]
    state_hospital_values = [row["total_hospitals"] for row in state_hospital_qs]

    state_hospital_chart = {
        "labels": state_hospital_labels,
        "values": state_hospital_values,
    }

    state_hospital_chart = {
    "labels": state_hospital_labels,
    "values": state_hospital_values,
    }

    context = {
        "filters": filters,
        "total_hospitals": total_hospitals,
        "total_patients": total_patients,
        "total_visits": total_visits,
        "avg_cost": avg_cost,
        "avg_coverage": avg_coverage,
        "gender_chart": gender_chart,
        "age_chart": age_chart,
        "payer_chart": payer_chart,
        "state_hospital_chart": json.dumps(state_hospital_chart),
    }



    return render(request, "core/home.html", context)
# -----------------------
# Recommendations Page
# -----------------------

import json
from django.db.models import Count, Avg, OuterRef, Subquery, FloatField
from django.shortcuts import render
from .models import MasterEncounter, RawPayer
from .forms import RecommendationFilterForm


def recommendations_view(request):
    state = request.GET.get('state', '').strip()
    city = request.GET.get('city', '').strip()
    gender = request.GET.get('gender', '').strip()
    payer_name = request.GET.get('payer_name', '').strip()

    # Add payer name from RawPayer using payer_id
    payer_subquery = RawPayer.objects.filter(
        payer_id=OuterRef('payer_id')
    ).values('name')[:1]

    base_qs = MasterEncounter.objects.select_related('hospital', 'patient').annotate(
        payer_name_resolved=Subquery(payer_subquery)
    )

    if state:
        base_qs = base_qs.filter(hospital__state=state)

    if city:
        base_qs = base_qs.filter(hospital__city=city)

    if gender:
        base_qs = base_qs.filter(patient__gender=gender)

    if payer_name:
        base_qs = base_qs.filter(payer_name_resolved=payer_name)

    # Payer dropdown values should depend on current state/city/gender selection
    payer_choice_qs = base_qs.exclude(
        payer_name_resolved__isnull=True
    ).exclude(
        payer_name_resolved=''
    ).values_list('payer_name_resolved', flat=True).distinct().order_by('payer_name_resolved')

    payer_choices = [(p, p) for p in payer_choice_qs if p]

    filters_form = RecommendationFilterForm(
        request.GET or None,
        payer_choices=payer_choices,
        initial={
            'state': state,
            'city': city,
            'gender': gender,
            'payer_name': payer_name,
        }
    )

    overall = base_qs.aggregate(
        total_visits=Count('id'),
        total_hospitals=Count('hospital', distinct=True),
        avg_cost=Avg('total_claim_cost'),
        avg_coverage=Avg('payer_coverage'),
        avg_oop=Avg('out_of_pocket'),
    )

    hospital_metrics_qs = base_qs.values(
        'hospital__id',   # ✅ THIS IS IMPORTANT
        'hospital__hospital_id',
        'hospital__name',
        'hospital__city',
        'hospital__state',
        'hospital__lat',
        'hospital__lon',
    ).annotate(
        visits=Count('id'),
        avg_cost=Avg('total_claim_cost'),
        avg_coverage=Avg('payer_coverage'),
        avg_oop=Avg('out_of_pocket'),
    )

    top_by_visits = list(hospital_metrics_qs.order_by('-visits', 'hospital__name')[:10])
    top_by_coverage = list(hospital_metrics_qs.order_by('-avg_coverage', 'hospital__name')[:10])

    overall_oop = overall.get('avg_oop') or 0
    overall_cov = overall.get('avg_coverage') or 0

    def enrich_rows(rows):
        for row in rows:
            row['id'] = row['hospital__id']
            row['hospital_id'] = row['hospital__hospital_id']
            row['name'] = row['hospital__name']
            row['city'] = row['hospital__city']
            row['state'] = row['hospital__state']
            row['lat'] = row['hospital__lat']
            row['lon'] = row['hospital__lon']

            avg_cost = float(row.get('avg_cost') or 0)
            avg_oop = float(row.get('avg_oop') or 0)
            avg_cov = float(row.get('avg_coverage') or 0)

            if avg_cost > 0:
                row['saving_pct'] = round((avg_cov / avg_cost) * 100, 2)
            else:
                row['saving_pct'] = 0.0

            row['avg_cost'] = round(avg_cost, 2)
            row['avg_oop'] = round(avg_oop, 2)
            row['avg_coverage'] = round(avg_cov, 2)

        return rows

    top_by_visits = enrich_rows(top_by_visits)
    top_by_coverage = enrich_rows(top_by_coverage)

    candidate_rows = list(hospital_metrics_qs.order_by('-visits')[:50])
    candidate_rows = enrich_rows(candidate_rows)

    max_visits = max([r['visits'] for r in candidate_rows], default=1)
    max_saving_pct = max([r['saving_pct'] for r in candidate_rows], default=1)

    for row in candidate_rows:
        visits_score = (row['visits'] / max_visits) if max_visits else 0
        savings_score = (row['saving_pct'] / max_saving_pct) if max_saving_pct else 0

        # simpler recommendation score
        row['recommendation_score'] = round(
            (visits_score * 0.55) + (savings_score * 0.45),
            4
        )

    top_recommendations = sorted(
        candidate_rows,
        key=lambda x: x['recommendation_score'],
        reverse=True
    )[:5]

    # Map points
    map_points = []
    for row in candidate_rows:
        if row.get('lat') is not None and row.get('lon') is not None:
            map_points.append({
                'name': row['name'],
                'city': row['city'],
                'state': row['state'],
                'lat': float(row['lat']),
                'lon': float(row['lon']),
                'visits': row['visits'],
                'avg_coverage': round(row['avg_coverage'] or 0, 2),
                'avg_oop': round(row['avg_oop'] or 0, 2),
                'saving_pct': row['saving_pct'],
            })

    context = {
        'filters_form': filters_form,
        'selected_filters': {
            'state': state,
            'city': city,
            'gender': gender,
            'payer_name': payer_name,
        },
        'overall': overall,
        'top_by_visits': top_by_visits,
        'top_by_coverage': top_by_coverage,
        'top_recommendations': top_recommendations,
        'map_points_json': json.dumps(map_points),
    }
    return render(request, 'core/recommendations.html', context)
# Hospital Detail
# Hospital Detail

import json
import os
import pickle

import pandas as pd
from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.db.models.functions import ExtractYear
from django.shortcuts import get_object_or_404, render

from .models import MasterEncounter, MasterHospital, RawPayer


# ---------------------------------------------------
# PKL HELPERS
# ---------------------------------------------------
def _pkl_file_path(metric, model_name="random_forest"):
    return os.path.join(
        settings.MEDIA_ROOT,
        "pickles",
        metric,
        f"{metric}_{model_name}.pkl",
    )


def _safe_pickle_load(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _coerce_month_column(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["month_start", "forecast_value"])

    df = df.copy()

    month_candidates = [
        "month_start",
        "month",
        "date",
        "ds",
        "timestamp",
        "period",
    ]
    value_candidates = [
        "forecast_value",
        "prediction",
        "predicted",
        "forecast",
        "value",
        "yhat",
    ]

    month_col = next((c for c in month_candidates if c in df.columns), None)
    value_col = next((c for c in value_candidates if c in df.columns), None)

    if month_col is None:
        if len(df.columns) >= 1:
            month_col = df.columns[0]

    if value_col is None:
        numeric_cols = [c for c in df.columns if c != month_col and pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            value_col = numeric_cols[0]
        elif len(df.columns) >= 2:
            value_col = df.columns[1]

    if month_col is None or value_col is None:
        return pd.DataFrame(columns=["month_start", "forecast_value"])

    out = df[[month_col, value_col]].copy()
    out.columns = ["month_start", "forecast_value"]

    out["month_start"] = pd.to_datetime(out["month_start"], errors="coerce", utc=True).dt.tz_localize(None)
    out["forecast_value"] = pd.to_numeric(out["forecast_value"], errors="coerce")

    out = out.dropna(subset=["month_start", "forecast_value"]).copy()
    out["month_start"] = out["month_start"].dt.to_period("M").dt.to_timestamp()
    out = out.sort_values("month_start").drop_duplicates(subset=["month_start"], keep="last")

    return out.reset_index(drop=True)


def _dict_month_value_to_df(data):
    rows = []
    for key, value in data.items():
        try:
            month_val = pd.to_datetime(str(key), errors="coerce")
        except Exception:
            month_val = pd.NaT

        if pd.isna(month_val):
            continue

        try:
            numeric_val = float(value)
        except Exception:
            continue

        rows.append(
            {
                "month_start": pd.Timestamp(month_val).to_period("M").to_timestamp(),
                "forecast_value": numeric_val,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["month_start", "forecast_value"])

    df = pd.DataFrame(rows).sort_values("month_start").drop_duplicates(subset=["month_start"], keep="last")
    return df.reset_index(drop=True)


def _filter_df_for_hospital(df, hospital):
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()

    id_cols = ["hospital_id", "org_id", "organization_id", "id"]
    name_cols = ["hospital_name", "hospital", "name", "organization_name"]

    for col in id_cols:
        if col in work.columns:
            try:
                filtered = work[work[col].astype(str) == str(hospital.id)].copy()
                if not filtered.empty:
                    return filtered
            except Exception:
                pass

    for col in name_cols:
        if col in work.columns:
            try:
                filtered = work[work[col].astype(str).str.strip().str.lower() == hospital.name.strip().lower()].copy()
                if not filtered.empty:
                    return filtered
            except Exception:
                pass

    return work


def _extract_forecast_df_from_any(obj, hospital):
    if obj is None:
        return pd.DataFrame(columns=["month_start", "forecast_value"])

    if isinstance(obj, pd.DataFrame):
        filtered = _filter_df_for_hospital(obj, hospital)
        return _coerce_month_column(filtered)

    if isinstance(obj, dict):
        for key in [hospital.id, str(hospital.id), hospital.name, str(hospital.name)]:
            if key in obj:
                return _extract_forecast_df_from_any(obj[key], hospital)

        nested_keys = [
            "future_monthly",
            "predictions",
            "forecast",
            "forecasts",
            "data",
            "results",
            "values",
        ]
        for key in nested_keys:
            if key in obj:
                candidate = _extract_forecast_df_from_any(obj[key], hospital)
                if candidate is not None and not candidate.empty:
                    return candidate

        month_value_df = _dict_month_value_to_df(obj)
        if not month_value_df.empty:
            return month_value_df

        for _, value in obj.items():
            candidate = _extract_forecast_df_from_any(value, hospital)
            if candidate is not None and not candidate.empty:
                return candidate

        return pd.DataFrame(columns=["month_start", "forecast_value"])

    if isinstance(obj, list):
        if not obj:
            return pd.DataFrame(columns=["month_start", "forecast_value"])

        try:
            df = pd.DataFrame(obj)
            filtered = _filter_df_for_hospital(df, hospital)
            return _coerce_month_column(filtered)
        except Exception:
            return pd.DataFrame(columns=["month_start", "forecast_value"])

    return pd.DataFrame(columns=["month_start", "forecast_value"])


def _load_metric_forecast(metric, hospital, model_name="random_forest"):
    file_path = _pkl_file_path(metric, model_name=model_name)
    raw_obj = _safe_pickle_load(file_path)
    return _extract_forecast_df_from_any(raw_obj, hospital)


def _shift_future_to_global_last_month(forecast_df, global_last_month):
    if forecast_df is None or forecast_df.empty or global_last_month is None:
        return forecast_df if forecast_df is not None else pd.DataFrame(columns=["month_start", "forecast_value"])

    work = forecast_df.copy()
    work["month_start"] = pd.to_datetime(work["month_start"], errors="coerce", utc=True).dt.tz_localize(None)
    work = work.dropna(subset=["month_start"]).copy()

    if work.empty:
        return work

    expected_first_month = pd.Timestamp(global_last_month) + pd.offsets.MonthBegin(1)
    current_first_month = work["month_start"].min()

    month_diff = (
        (expected_first_month.year - current_first_month.year) * 12
        + (expected_first_month.month - current_first_month.month)
    )

    work["month_start"] = work["month_start"] + pd.DateOffset(months=month_diff)
    work = work.sort_values("month_start").drop_duplicates(subset=["month_start"], keep="last")

    return work.reset_index(drop=True)


def _history_df_from_monthly_group(monthly_grouped, value_col):
    if monthly_grouped is None or monthly_grouped.empty or value_col not in monthly_grouped.columns:
        return pd.DataFrame(columns=["month_start", "value"])

    out = monthly_grouped[["month_start", value_col]].copy()
    out.columns = ["month_start", "value"]
    out["month_start"] = pd.to_datetime(out["month_start"], errors="coerce", utc=True).dt.tz_localize(None)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["month_start", "value"]).copy()
    out = out.sort_values("month_start").drop_duplicates(subset=["month_start"], keep="last")
    return out.reset_index(drop=True)


def _build_history_forecast_series(history_df, forecast_df):
    history_map = {}
    forecast_map = {}

    if history_df is not None and not history_df.empty:
        hist_df = history_df.copy()
        hist_df["month_start"] = pd.to_datetime(hist_df["month_start"], errors="coerce", utc=True).dt.tz_localize(None)
        hist_df = hist_df.dropna(subset=["month_start"])
        for _, row in hist_df.iterrows():
            history_map[pd.Timestamp(row["month_start"]).strftime("%Y-%m")] = round(float(row["value"]), 2)

    if forecast_df is not None and not forecast_df.empty:
        fc_df = forecast_df.copy()
        fc_df["month_start"] = pd.to_datetime(fc_df["month_start"], errors="coerce", utc=True).dt.tz_localize(None)
        fc_df = fc_df.dropna(subset=["month_start"])
        for _, row in fc_df.iterrows():
            forecast_map[pd.Timestamp(row["month_start"]).strftime("%Y-%m")] = round(float(row["forecast_value"]), 2)

    all_labels = sorted(set(history_map.keys()) | set(forecast_map.keys()))
    history_values = [history_map.get(label, None) for label in all_labels]
    forecast_values = [forecast_map.get(label, None) for label in all_labels]

    return all_labels, history_values, forecast_values


def _get_hospital_global_last_month(hospital_obj):
    global_df = pd.DataFrame(
        list(
            MasterEncounter.objects.filter(hospital=hospital_obj).values("start")
        )
    )

    if global_df.empty:
        return None

    global_df["start"] = pd.to_datetime(global_df["start"], errors="coerce", utc=True).dt.tz_localize(None)
    global_df = global_df.dropna(subset=["start"]).copy()

    if global_df.empty:
        return None

    global_df["month_start"] = global_df["start"].dt.to_period("M").dt.to_timestamp()
    return global_df["month_start"].max()


# ---------------------------------------------------
# MAIN VIEW
# ---------------------------------------------------
def hospital_detail_view(request, hospital_id):
    hospital = get_object_or_404(MasterHospital, pk=hospital_id)

    # ---------------------------------------------------
    # STEP 1: PAGE FILTERS
    # ---------------------------------------------------
    gender = request.GET.get("gender", "").strip()
    payer_name = request.GET.get("payer_name", "").strip()

    # ---------------------------------------------------
    # STEP 2: FILTERED DATASET
    # ---------------------------------------------------
    encounters = MasterEncounter.objects.filter(hospital=hospital).select_related("patient")

    if gender:
        encounters = encounters.filter(patient__gender=gender)

    if payer_name:
        payer_ids = list(
            RawPayer.objects.filter(name=payer_name).values_list("payer_id", flat=True)
        )
        if payer_ids:
            encounters = encounters.filter(payer_id__in=payer_ids)
        else:
            encounters = encounters.none()

    # ---------------------------------------------------
    # FILTER DROPDOWN OPTIONS
    # ---------------------------------------------------
    gender_options = list(
        MasterEncounter.objects.filter(hospital=hospital)
        .exclude(patient__gender__isnull=True)
        .exclude(patient__gender__exact="")
        .values_list("patient__gender", flat=True)
        .distinct()
        .order_by("patient__gender")
    )

    payer_ids_used = list(
        MasterEncounter.objects.filter(hospital=hospital)
        .exclude(payer_id__isnull=True)
        .values_list("payer_id", flat=True)
        .distinct()
    )

    payer_name_options = list(
        RawPayer.objects.filter(payer_id__in=payer_ids_used)
        .exclude(name__isnull=True)
        .exclude(name__exact="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

    # ---------------------------------------------------
    # KPI VALUES
    # ---------------------------------------------------
    total_visits = encounters.count()
    total_patients = encounters.values("patient").distinct().count()

    avg_cost = encounters.aggregate(v=Avg("total_claim_cost"))["v"] or 0
    avg_coverage = encounters.aggregate(v=Avg("payer_coverage"))["v"] or 0
    avg_oop = encounters.aggregate(v=Avg("out_of_pocket"))["v"] or 0

    total_cost = encounters.aggregate(v=Sum("total_claim_cost"))["v"] or 0
    total_coverage = encounters.aggregate(v=Sum("payer_coverage"))["v"] or 0
    total_oop = encounters.aggregate(v=Sum("out_of_pocket"))["v"] or 0

    coverage_ratio = 0
    if total_cost and total_cost > 0:
        coverage_ratio = (total_coverage / total_cost) * 100

    # ---------------------------------------------------
    # HISTORICAL YEARLY DATA
    # ---------------------------------------------------
    yearly_data = (
        encounters
        .annotate(year=ExtractYear("start"))
        .values("year")
        .annotate(
            visits=Count("id"),
            avg_cost=Avg("total_claim_cost"),
            avg_coverage=Avg("payer_coverage"),
            avg_oop=Avg("out_of_pocket"),
        )
        .order_by("year")
    )

    yearly_labels = [str(row["year"]) for row in yearly_data if row["year"]]
    yearly_avg_cost = [round(row["avg_cost"] or 0, 2) for row in yearly_data if row["year"]]
    yearly_avg_coverage = [round(row["avg_coverage"] or 0, 2) for row in yearly_data if row["year"]]
    yearly_avg_oop = [round(row["avg_oop"] or 0, 2) for row in yearly_data if row["year"]]

    # ---------------------------------------------------
    # HISTORICAL MONTHLY DATA
    # ---------------------------------------------------
    hist_monthly_df = pd.DataFrame(
        list(
            encounters.values(
                "start",
                "total_claim_cost",
                "payer_coverage",
                "out_of_pocket",
                "patient_id",
                "hospital_id",
            )
        )
    )

    monthly_labels = []
    monthly_avg_cost = []
    monthly_avg_coverage = []
    monthly_avg_oop = []
    monthly_grouped = pd.DataFrame()

    if not hist_monthly_df.empty:
        hist_monthly_df["start"] = pd.to_datetime(
            hist_monthly_df["start"], errors="coerce", utc=True
        ).dt.tz_localize(None)
        hist_monthly_df = hist_monthly_df.dropna(subset=["start"]).copy()

        for col in ["total_claim_cost", "payer_coverage", "out_of_pocket"]:
            hist_monthly_df[col] = pd.to_numeric(hist_monthly_df[col], errors="coerce").fillna(0)

        hist_monthly_df["month_start"] = hist_monthly_df["start"].dt.to_period("M").dt.to_timestamp()

        monthly_grouped = (
            hist_monthly_df.groupby("month_start")
            .agg(
                avg_cost=("total_claim_cost", "mean"),
                avg_coverage=("payer_coverage", "mean"),
                avg_oop=("out_of_pocket", "mean"),
            )
            .reset_index()
            .sort_values("month_start")
        )

        monthly_labels = monthly_grouped["month_start"].dt.strftime("%Y-%m").tolist()
        monthly_avg_cost = monthly_grouped["avg_cost"].round(2).tolist()
        monthly_avg_coverage = monthly_grouped["avg_coverage"].round(2).tolist()
        monthly_avg_oop = monthly_grouped["avg_oop"].round(2).tolist()

    # ---------------------------------------------------
    # STEP 3: LOAD FORECASTS FROM PKL (NO RETRAINING)
    # ---------------------------------------------------
    global_last_month = _get_hospital_global_last_month(hospital)

    cost_forecast_df = _load_metric_forecast("avg_cost", hospital, model_name="random_forest")
    coverage_forecast_df = _load_metric_forecast("avg_coverage", hospital, model_name="random_forest")
    oop_forecast_df = _load_metric_forecast("avg_oop", hospital, model_name="random_forest")

    cost_forecast_df = _shift_future_to_global_last_month(cost_forecast_df, global_last_month)
    coverage_forecast_df = _shift_future_to_global_last_month(coverage_forecast_df, global_last_month)
    oop_forecast_df = _shift_future_to_global_last_month(oop_forecast_df, global_last_month)

    if global_last_month is not None:
        cost_forecast_df = cost_forecast_df[cost_forecast_df["month_start"] > global_last_month].copy() if not cost_forecast_df.empty else cost_forecast_df
        coverage_forecast_df = coverage_forecast_df[coverage_forecast_df["month_start"] > global_last_month].copy() if not coverage_forecast_df.empty else coverage_forecast_df
        oop_forecast_df = oop_forecast_df[oop_forecast_df["month_start"] > global_last_month].copy() if not oop_forecast_df.empty else oop_forecast_df

    predicted_avg_spend_next_visit = 0
    predicted_avg_coverage_next_visit = 0
    predicted_avg_oop_next_visit = 0
    predicted_coverage_ratio_next_visit = 0

    if cost_forecast_df is not None and not cost_forecast_df.empty:
        predicted_avg_spend_next_visit = round(float(cost_forecast_df.iloc[0]["forecast_value"]), 2)

    if coverage_forecast_df is not None and not coverage_forecast_df.empty:
        predicted_avg_coverage_next_visit = round(float(coverage_forecast_df.iloc[0]["forecast_value"]), 2)

    if oop_forecast_df is not None and not oop_forecast_df.empty:
        predicted_avg_oop_next_visit = round(float(oop_forecast_df.iloc[0]["forecast_value"]), 2)

    if predicted_avg_spend_next_visit > 0:
        predicted_coverage_ratio_next_visit = round(
            (predicted_avg_coverage_next_visit / predicted_avg_spend_next_visit) * 100, 2
        )

    # ---------------------------------------------------
    # STEP 4: BUILD FINAL PREDICTION OUTPUTS
    # ---------------------------------------------------
    next_3_months_rows = []
    future_lookup = {}

    future_cost_df = cost_forecast_df.copy() if cost_forecast_df is not None else pd.DataFrame(columns=["month_start", "forecast_value"])
    future_cov_df = coverage_forecast_df.copy() if coverage_forecast_df is not None else pd.DataFrame(columns=["month_start", "forecast_value"])
    future_oop_df = oop_forecast_df.copy() if oop_forecast_df is not None else pd.DataFrame(columns=["month_start", "forecast_value"])

    if not future_cost_df.empty:
        future_cost_df["month_start"] = pd.to_datetime(future_cost_df["month_start"]).dt.tz_localize(None)
    if not future_cov_df.empty:
        future_cov_df["month_start"] = pd.to_datetime(future_cov_df["month_start"]).dt.tz_localize(None)
    if not future_oop_df.empty:
        future_oop_df["month_start"] = pd.to_datetime(future_oop_df["month_start"]).dt.tz_localize(None)

    future_months = sorted(
        set(future_cost_df["month_start"].dt.strftime("%Y-%m").tolist()) if not future_cost_df.empty else []
    )

    for ym in future_months:
        cost_val = None
        cov_val = None
        oop_val = None

        if not future_cost_df.empty:
            row = future_cost_df[future_cost_df["month_start"].dt.strftime("%Y-%m") == ym]
            if not row.empty:
                cost_val = round(float(row.iloc[0]["forecast_value"]), 2)

        if not future_cov_df.empty:
            row = future_cov_df[future_cov_df["month_start"].dt.strftime("%Y-%m") == ym]
            if not row.empty:
                cov_val = round(float(row.iloc[0]["forecast_value"]), 2)

        if not future_oop_df.empty:
            row = future_oop_df[future_oop_df["month_start"].dt.strftime("%Y-%m") == ym]
            if not row.empty:
                oop_val = round(float(row.iloc[0]["forecast_value"]), 2)

        future_lookup[ym] = {
            "total_claim_cost": cost_val,
            "coverage_cost": cov_val,
            "out_of_pocket": oop_val,
        }

    for ym in future_months[:3]:
        next_3_months_rows.append(
            {
                "month": ym,
                "total_claim_cost": future_lookup[ym]["total_claim_cost"],
                "coverage_cost": future_lookup[ym]["coverage_cost"],
                "out_of_pocket": future_lookup[ym]["out_of_pocket"],
            }
        )

    future_year_options = sorted(list({m.split("-")[0] for m in future_months}))
    future_month_options = [
        {"value": "01", "label": "January"},
        {"value": "02", "label": "February"},
        {"value": "03", "label": "March"},
        {"value": "04", "label": "April"},
        {"value": "05", "label": "May"},
        {"value": "06", "label": "June"},
        {"value": "07", "label": "July"},
        {"value": "08", "label": "August"},
        {"value": "09", "label": "September"},
        {"value": "10", "label": "October"},
        {"value": "11", "label": "November"},
        {"value": "12", "label": "December"},
    ]

    # ---------------------------------------------------
    # STEP 5: GRAPH DATA
    # ---------------------------------------------------
    cost_history_df = _history_df_from_monthly_group(monthly_grouped, "avg_cost")
    coverage_history_df = _history_df_from_monthly_group(monthly_grouped, "avg_coverage")
    oop_history_df = _history_df_from_monthly_group(monthly_grouped, "avg_oop")

    cost_line_labels, cost_history_values, cost_forecast_values = _build_history_forecast_series(
        cost_history_df,
        cost_forecast_df,
    )

    coverage_line_labels, coverage_history_values, coverage_forecast_values = _build_history_forecast_series(
        coverage_history_df,
        coverage_forecast_df,
    )

    oop_line_labels, oop_history_values, oop_forecast_values = _build_history_forecast_series(
        oop_history_df,
        oop_forecast_df,
    )

    final_line_labels = cost_line_labels
    if not final_line_labels:
        final_line_labels = coverage_line_labels
    if not final_line_labels:
        final_line_labels = oop_line_labels

    line_chart_json = {
        "labels": final_line_labels,
        "cost_history": cost_history_values,
        "cost_forecast": cost_forecast_values,
        "coverage_history": coverage_history_values,
        "coverage_forecast": coverage_forecast_values,
        "oop_history": oop_history_values,
        "oop_forecast": oop_forecast_values,
    }

    # ---------------------------------------------------
    # OTHER CHARTS
    # ---------------------------------------------------
    encounter_class_data = (
        encounters
        .values("encounter_class")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )

    class_labels = [
        row["encounter_class"].title() if row["encounter_class"] else "Unknown"
        for row in encounter_class_data
    ]
    class_values = [row["total"] for row in encounter_class_data]

    insurance_base = (
        encounters
        .exclude(payer_id__isnull=True)
        .values("payer_id")
        .annotate(avg_coverage=Avg("payer_coverage"))
        .order_by("-avg_coverage")[:3]
    )

    payer_ids = [row["payer_id"] for row in insurance_base if row["payer_id"]]

    payer_name_map = dict(
        RawPayer.objects.filter(payer_id__in=payer_ids).values_list("payer_id", "name")
    )

    insurance_labels = [
        payer_name_map.get(row["payer_id"], "Unknown Insurance")
        for row in insurance_base
    ]
    insurance_values = [round(row["avg_coverage"] or 0, 2) for row in insurance_base]

    cost_split_labels = ["Average Coverage", "Average Out of Pocket"]
    cost_split_values = [round(avg_coverage, 2), round(avg_oop, 2)]

    financial_summary_labels = ["Average Cost", "Average Coverage", "Average Out of Pocket"]
    financial_summary_values = [
        round(avg_cost, 2),
        round(avg_coverage, 2),
        round(avg_oop, 2),
    ]

    context = {
        "hospital": hospital,

        "selected_gender": gender,
        "selected_payer_name": payer_name,
        "gender_options": gender_options,
        "payer_name_options": payer_name_options,

        "total_visits": total_visits,
        "total_patients": total_patients,
        "avg_cost": round(avg_cost, 2),
        "avg_coverage": round(avg_coverage, 2),
        "avg_oop": round(avg_oop, 2),
        "coverage_ratio": round(coverage_ratio, 2),

        "predicted_avg_spend_next_visit": predicted_avg_spend_next_visit,
        "predicted_avg_coverage_next_visit": predicted_avg_coverage_next_visit,
        "predicted_avg_oop_next_visit": predicted_avg_oop_next_visit,
        "predicted_coverage_ratio_next_visit": predicted_coverage_ratio_next_visit,

        "next_3_months_rows": next_3_months_rows,
        "future_year_options": future_year_options,
        "future_month_options": future_month_options,
        "future_lookup_json": json.dumps(future_lookup),

        "line_chart_json": json.dumps(line_chart_json),

        "class_labels": json.dumps(class_labels),
        "class_values": json.dumps(class_values),

        "insurance_labels": json.dumps(insurance_labels),
        "insurance_values": json.dumps(insurance_values),

        "cost_split_labels": json.dumps(cost_split_labels),
        "cost_split_values": json.dumps(cost_split_values),

        "financial_summary_labels": json.dumps(financial_summary_labels),
        "financial_summary_values": json.dumps(financial_summary_values),

        "yearly_labels": json.dumps(yearly_labels),
        "yearly_avg_cost": json.dumps(yearly_avg_cost),
        "yearly_avg_coverage": json.dumps(yearly_avg_coverage),
        "yearly_avg_oop": json.dumps(yearly_avg_oop),

        "monthly_labels": json.dumps(monthly_labels),
        "monthly_avg_cost": json.dumps(monthly_avg_cost),
        "monthly_avg_coverage": json.dumps(monthly_avg_coverage),
        "monthly_avg_oop": json.dumps(monthly_avg_oop),
    }

    return render(request, "core/hospital_detail.html", context)

## COmpare 
def _hospital_name_from_obj(hospital_obj, hospital_id=None):
    """
    Safely return a readable hospital name from different possible model schemas.
    """
    if not hospital_obj:
        return f"Hospital {hospital_id}" if hospital_id is not None else "Unknown Hospital"

    for field in ["name", "hospital_name", "organization_name", "display_name", "provider_name"]:
        value = getattr(hospital_obj, field, None)
        if value:
            return str(value)

    if hospital_id is None:
        hospital_id = getattr(hospital_obj, "id", None)

    return f"Hospital {hospital_id}" if hospital_id is not None else "Unknown Hospital"


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default

from django.apps import apps

# -----------------------------
# Discover payer model dynamically
# -----------------------------
def _discover_payer_model():
    candidates = [
        ("core", "Payer"),
        ("core", "Payers"),
        ("core", "Insurance"),
        ("core", "InsurancePayer"),
    ]

    for app_label, model_name in candidates:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            continue

    return None


# -----------------------------
# Get payer name field dynamically
# -----------------------------
def _payer_name_field(model_cls):
    if not model_cls:
        return None

    possible_fields = [
        "name",
        "payer_name",
        "organization_name",
        "display_name",
        "description",
    ]

    model_fields = {f.name for f in model_cls._meta.fields}

    for field in possible_fields:
        if field in model_fields:
            return field

    return None


# -----------------------------
# Get payer id field dynamically
# -----------------------------
def _payer_id_field(model_cls):
    if not model_cls:
        return None

    possible_fields = [
        "id",
        "payer_id",
        "payerid",
    ]

    model_fields = {f.name for f in model_cls._meta.fields}

    for field in possible_fields:
        if field in model_fields:
            return field

    return None

def compare_view(request):
    # -----------------------------
    # Read selected hospitals
    # -----------------------------
    raw_ids = request.GET.getlist("hospital_ids")
    payer_name = (request.GET.get("payer_name") or "").strip()

    hospital_ids = []
    seen = set()

    for value in raw_ids:
        try:
            hid = int(value)
            if hid not in seen:
                hospital_ids.append(hid)
                seen.add(hid)
        except Exception:
            continue

    # limit max 4
    hospital_ids = hospital_ids[:4]

    if len(hospital_ids) < 2:
        messages.warning(request, "Please select at least 2 hospitals to compare.")
        return redirect("recommendations")

    # -----------------------------
    # Base queryset
    # -----------------------------
    encounters = (
        MasterEncounter.objects
        .filter(hospital_id__in=hospital_ids)
        .select_related("hospital")
        .select_related("patient")
        .order_by("hospital_id", "start")
    )

    # -----------------------------
    # Optional payer filter
    # Only this filter is kept
    # -----------------------------
    payer_model = _discover_payer_model()
    applied_payer_ids = []

    if payer_name and payer_model:
        payer_name_col = _payer_name_field(payer_model)
        payer_id_col = _payer_id_field(payer_model)

        if payer_name_col and payer_id_col:
            payer_matches = payer_model.objects.filter(**{f"{payer_name_col}__iexact": payer_name})
            applied_payer_ids = list(payer_matches.values_list(payer_id_col, flat=True))

            if applied_payer_ids:
                encounters = encounters.filter(payer_id__in=applied_payer_ids)
            else:
                # if exact match fails, try contains
                payer_matches = payer_model.objects.filter(**{f"{payer_name_col}__icontains": payer_name})
                applied_payer_ids = list(payer_matches.values_list(payer_id_col, flat=True))
                if applied_payer_ids:
                    encounters = encounters.filter(payer_id__in=applied_payer_ids)

    # -----------------------------
    # Aggregate in Python
    # safer for your current model structure
    # -----------------------------
    hospital_stats = {}
    monthly_visits = defaultdict(lambda: defaultdict(int))
    monthly_avg_cost_temp = defaultdict(lambda: defaultdict(list))
    encounter_class_map = defaultdict(lambda: defaultdict(int))
    age_group_map = defaultdict(lambda: defaultdict(int))

    hospital_objects = {
        hospital.id: hospital
        for hospital in MasterHospital.objects.filter(id__in=hospital_ids)
    }

    for hid in hospital_ids:
        hospital_obj = hospital_objects.get(hid)
        hospital_stats[hid] = {
            "hospital_id": hid,
            "name": _hospital_name_from_obj(hospital_obj, hid),
            "total_visits": 0,
            "unique_patients_set": set(),
            "cost_values": [],
            "coverage_values": [],
            "oop_values": [],
            "coverage_ratio_values": [],
            "score": 0,
        }

    for row in encounters:
        hid = row.hospital_id
        if hid not in hospital_stats:
            continue

        total_cost = _safe_float(getattr(row, "total_claim_cost", 0))
        coverage = _safe_float(getattr(row, "payer_coverage", 0))
        oop = _safe_float(getattr(row, "out_of_pocket", total_cost - coverage))
        patient_id = getattr(row, "patient_id", None)
        encounter_class = getattr(row, "encounter_class", None) or "Unknown"
        age_at_visit = getattr(row, "age_at_visit", None)

        hospital_stats[hid]["total_visits"] += 1
        if patient_id:
            hospital_stats[hid]["unique_patients_set"].add(str(patient_id))

        hospital_stats[hid]["cost_values"].append(total_cost)
        hospital_stats[hid]["coverage_values"].append(coverage)
        hospital_stats[hid]["oop_values"].append(oop)

        ratio = 0
        if total_cost > 0:
            ratio = (coverage / total_cost) * 100
        hospital_stats[hid]["coverage_ratio_values"].append(ratio)

        # monthly trends
        start_dt = getattr(row, "start", None)
        if start_dt:
            month_key = start_dt.strftime("%Y-%m")
            monthly_visits[hid][month_key] += 1
            monthly_avg_cost_temp[hid][month_key].append(total_cost)

        # encounter class split
        encounter_class_map[hid][str(encounter_class)] += 1

        # age group split
        age_num = _safe_int(age_at_visit, default=-1)
        if age_num >= 0:
            if age_num <= 18:
                age_group = "0-18"
            elif age_num <= 35:
                age_group = "19-35"
            elif age_num <= 50:
                age_group = "36-50"
            elif age_num <= 65:
                age_group = "51-65"
            else:
                age_group = "66+"
            age_group_map[hid][age_group] += 1

    # Final summary rows
    summary_cards = []
    for hid in hospital_ids:
        item = hospital_stats[hid]

        avg_cost = mean(item["cost_values"]) if item["cost_values"] else 0
        avg_coverage = mean(item["coverage_values"]) if item["coverage_values"] else 0
        avg_oop = mean(item["oop_values"]) if item["oop_values"] else 0
        coverage_ratio = mean(item["coverage_ratio_values"]) if item["coverage_ratio_values"] else 0

        # simple comparison score
        # higher coverage and visits good, lower cost and oop better
        score = (
            (coverage_ratio * 0.40)
            + (item["total_visits"] * 0.20)
            + (avg_coverage * 0.0008)
            - (avg_cost * 0.0005)
            - (avg_oop * 0.0004)
        )

        item["score"] = round(score, 2)

        detail_url = reverse("hospital_detail", args=[hid])
        if payer_name:
            detail_url += f"?payer_name={payer_name}"

        summary_cards.append({
            "hospital_id": hid,
            "name": item["name"],
            "total_visits": item["total_visits"],
            "unique_patients": len(item["unique_patients_set"]),
            "avg_cost": round(avg_cost, 2),
            "avg_coverage": round(avg_coverage, 2),
            "avg_oop": round(avg_oop, 2),
            "coverage_ratio": round(coverage_ratio, 2),
            "score": round(score, 2),
            "detail_url": detail_url,
        })

    # -----------------------------
    # Best / worst highlighting
    # -----------------------------
    def _best_id(key, reverse=True):
        valid = [x for x in summary_cards]
        if not valid:
            return None
        sorted_items = sorted(valid, key=lambda x: x[key], reverse=reverse)
        return sorted_items[0]["hospital_id"]

    def _worst_id(key, reverse=True):
        valid = [x for x in summary_cards]
        if not valid:
            return None
        sorted_items = sorted(valid, key=lambda x: x[key], reverse=reverse)
        return sorted_items[-1]["hospital_id"]

    best_visits_id = _best_id("total_visits", reverse=True)
    best_patients_id = _best_id("unique_patients", reverse=True)
    best_coverage_id = _best_id("avg_coverage", reverse=True)
    best_ratio_id = _best_id("coverage_ratio", reverse=True)
    lowest_cost_id = _best_id("avg_cost", reverse=False)
    lowest_oop_id = _best_id("avg_oop", reverse=False)
    best_score_id = _best_id("score", reverse=True)

    # -----------------------------
    # Comparison tags
    # -----------------------------
    for row in summary_cards:
        tags = []
        hid = row["hospital_id"]

        if hid == best_visits_id:
            tags.append("Most Visited")
        if hid == best_patients_id:
            tags.append("More Patients")
        if hid == best_coverage_id:
            tags.append("Best Avg Coverage")
        if hid == best_ratio_id:
            tags.append("Best Coverage %")
        if hid == lowest_cost_id:
            tags.append("Lowest Avg Cost")
        if hid == lowest_oop_id:
            tags.append("Lowest Out-of-Pocket")
        if hid == best_score_id:
            tags.append("Balanced Best Option")

        row["tags"] = tags

    # -----------------------------
    # Chart data prep
    # -----------------------------
    hospital_names = [row["name"] for row in summary_cards]

    visits_chart = {
        "labels": hospital_names,
        "values": [row["total_visits"] for row in summary_cards],
    }

    patients_chart = {
        "labels": hospital_names,
        "values": [row["unique_patients"] for row in summary_cards],
    }

    financial_split_chart = {
        "labels": hospital_names,
        "coverage": [row["avg_coverage"] for row in summary_cards],
        "oop": [row["avg_oop"] for row in summary_cards],
    }

    avg_cost_chart = {
        "labels": hospital_names,
        "values": [row["avg_cost"] for row in summary_cards],
    }

    ratio_chart = {
        "labels": hospital_names,
        "values": [row["coverage_ratio"] for row in summary_cards],
    }

    score_chart = {
        "labels": hospital_names,
        "values": [row["score"] for row in summary_cards],
    }

    # monthly visits and monthly avg cost
    all_months = set()
    for hid in hospital_ids:
        all_months.update(monthly_visits[hid].keys())
        all_months.update(monthly_avg_cost_temp[hid].keys())

    all_months = sorted(list(all_months))

    monthly_visits_chart = {
        "labels": all_months,
        "datasets": []
    }

    monthly_cost_chart = {
        "labels": all_months,
        "datasets": []
    }

    for row in summary_cards:
        hid = row["hospital_id"]

        monthly_visits_chart["datasets"].append({
            "label": row["name"],
            "data": [monthly_visits[hid].get(m, 0) for m in all_months]
        })

        monthly_cost_chart["datasets"].append({
            "label": row["name"],
            "data": [
                round(mean(monthly_avg_cost_temp[hid][m]), 2) if monthly_avg_cost_temp[hid].get(m) else 0
                for m in all_months
            ]
        })

    # encounter class grouped
    all_classes = set()
    for hid in hospital_ids:
        all_classes.update(encounter_class_map[hid].keys())
    all_classes = sorted(list(all_classes))

    encounter_class_chart = {
        "labels": all_classes,
        "datasets": []
    }

    for row in summary_cards:
        hid = row["hospital_id"]
        encounter_class_chart["datasets"].append({
            "label": row["name"],
            "data": [encounter_class_map[hid].get(cls, 0) for cls in all_classes]
        })

    # age groups
    age_labels = ["0-18", "19-35", "36-50", "51-65", "66+"]
    age_group_chart = {
        "labels": age_labels,
        "datasets": []
    }

    for row in summary_cards:
        hid = row["hospital_id"]
        age_group_chart["datasets"].append({
            "label": row["name"],
            "data": [age_group_map[hid].get(label, 0) for label in age_labels]
        })

    context = {
        "summary_cards": summary_cards,
        "selected_hospital_ids": hospital_ids,
        "payer_name": payer_name,

        "visits_chart_json": json.dumps(visits_chart),
        "patients_chart_json": json.dumps(patients_chart),
        "financial_split_chart_json": json.dumps(financial_split_chart),
        "avg_cost_chart_json": json.dumps(avg_cost_chart),
        "ratio_chart_json": json.dumps(ratio_chart),
        "score_chart_json": json.dumps(score_chart),
        "monthly_visits_chart_json": json.dumps(monthly_visits_chart),
        "monthly_cost_chart_json": json.dumps(monthly_cost_chart),
        "encounter_class_chart_json": json.dumps(encounter_class_chart),
        "age_group_chart_json": json.dumps(age_group_chart),
    }

    return render(request, "core/compare.html", context)

from .services.delete_batch_service import delete_batch_data

def delete_batch_data_view(request, batch_id):
    batch = get_object_or_404(UploadBatch, id=batch_id)
    delete_batch_data(batch, delete_batch_record=False)
    messages.error(request, "Batch raw data and extracted files deleted.")
    return redirect("batch_history")

    


from django.shortcuts import render
from django.db.models import Count, Avg, Case, When, Value, CharField, OuterRef, Subquery
from django.db.models.functions import ExtractYear
import plotly.express as px
from plotly.offline import plot

from .models import MasterHospital, MasterEncounter, RawPayer

import os
import pickle
from django.conf import settings
import plotly.graph_objects as go
import pandas as pd


US_STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC"
}


def load_prediction(metric, model):
    file_path = os.path.join(
        settings.MEDIA_ROOT,
        "pickles",
        metric,
        f"{metric}_{model}.pkl"
    )

    if not os.path.exists(file_path):
        return None

    with open(file_path, "rb") as f:
        return pickle.load(f)


def _normalize_pkl_series(series_obj):
    """
    Supports:
    1. dict like {"2024-01": 123, ...}
    2. pandas DataFrame with month/value columns
    """
    if series_obj is None:
        return pd.DataFrame(columns=["month_start", "plot_value"])

    if isinstance(series_obj, dict):
        rows = []
        for k, v in series_obj.items():
            try:
                rows.append({
                    "month_start": pd.to_datetime(k),
                    "plot_value": float(v),
                })
            except Exception:
                continue
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["month_start", "plot_value"])
        return df.sort_values("month_start").reset_index(drop=True)

    if isinstance(series_obj, pd.DataFrame):
        df = series_obj.copy()

        if "month_start" not in df.columns:
            if "date" in df.columns:
                df["month_start"] = df["date"]
            elif "month" in df.columns:
                df["month_start"] = df["month"]

        if "plot_value" not in df.columns:
            if "value" in df.columns:
                df["plot_value"] = df["value"]
            elif "forecast_value" in df.columns:
                df["plot_value"] = df["forecast_value"]

        if "month_start" not in df.columns or "plot_value" not in df.columns:
            return pd.DataFrame(columns=["month_start", "plot_value"])

        df["month_start"] = pd.to_datetime(df["month_start"], errors="coerce")
        df["plot_value"] = pd.to_numeric(df["plot_value"], errors="coerce")
        df = df.dropna(subset=["month_start", "plot_value"]).copy()
        return df.sort_values("month_start").reset_index(drop=True)

    return pd.DataFrame(columns=["month_start", "plot_value"])


def developer_data_dashboard(request):
    selected_state = request.GET.get("state", "").strip()
    selected_city = request.GET.get("city", "").strip()
    selected_year = request.GET.get("year", "").strip()
    selected_top_n = request.GET.get("top_n", "10").strip()

    pred_metric = request.GET.get("pred_metric", "visits").strip().lower()
    pred_model = request.GET.get("pred_model", "random_forest").strip().lower()
    pred_year = request.GET.get("pred_year", "").strip()
    pred_month = request.GET.get("pred_month", "").strip()

    if pred_metric not in {"visits", "patients", "hospitals"}:
        pred_metric = "visits"

    if pred_model not in {"random_forest", "xgboost"}:
        pred_model = "random_forest"

    try:
        top_n = int(selected_top_n)
        if top_n <= 0:
            top_n = 10
    except ValueError:
        top_n = 10

    base_encounters = MasterEncounter.objects.select_related("hospital", "patient").all()
    hospitals = MasterHospital.objects.all()

    # filter options
    states = (
        MasterHospital.objects.exclude(state__isnull=True)
        .exclude(state__exact="")
        .values_list("state", flat=True)
        .distinct()
        .order_by("state")
    )

    cities_qs = MasterHospital.objects.exclude(city__isnull=True).exclude(city__exact="")
    if selected_state:
        cities_qs = cities_qs.filter(state=selected_state)
    cities = cities_qs.values_list("city", flat=True).distinct().order_by("city")

    years_qs = (
        MasterEncounter.objects.annotate(year=ExtractYear("start"))
        .values_list("year", flat=True)
        .distinct()
        .order_by("year")
    )
    years = [y for y in years_qs if y is not None]

    encounters_for_general = base_encounters
    encounters_for_forecast = base_encounters

    if selected_state:
        encounters_for_general = encounters_for_general.filter(hospital__state=selected_state)
        encounters_for_forecast = encounters_for_forecast.filter(hospital__state=selected_state)
        hospitals = hospitals.filter(state=selected_state)

    if selected_city:
        encounters_for_general = encounters_for_general.filter(hospital__city=selected_city)
        encounters_for_forecast = encounters_for_forecast.filter(hospital__city=selected_city)
        hospitals = hospitals.filter(city=selected_city)

    if selected_year:
        try:
            selected_year_int = int(selected_year)
            encounters_for_general = encounters_for_general.filter(start__year=selected_year_int)
        except ValueError:
            pass

    # KPI cards
    total_patients = encounters_for_general.values("patient").distinct().count()
    total_hospitals = hospitals.values("hospital_id").distinct().count()
    total_visits = encounters_for_general.count()
    total_states = hospitals.exclude(state__isnull=True).exclude(state__exact="").values("state").distinct().count()
    total_cities = hospitals.exclude(city__isnull=True).exclude(city__exact="").values("city").distinct().count()

    # -----------------------------
    # Age Group Chart
    # -----------------------------
    age_group_qs = (
        encounters_for_general.exclude(patient__birthdate__isnull=True)
        .exclude(start__isnull=True)
        .annotate(age_years=ExtractYear("start") - ExtractYear("patient__birthdate"))
        .annotate(
            age_group=Case(
                When(age_years__lt=18, then=Value("0-17")),
                When(age_years__gte=18, age_years__lte=25, then=Value("18-25")),
                When(age_years__gte=26, age_years__lte=35, then=Value("26-35")),
                When(age_years__gte=36, age_years__lte=45, then=Value("36-45")),
                When(age_years__gte=46, age_years__lte=60, then=Value("46-60")),
                When(age_years__gte=61, then=Value("61+")),
                default=Value("Unknown"),
                output_field=CharField(),
            )
        )
        .values("age_group")
        .annotate(total_visits=Count("encounter_id"))
    )

    age_group_data = list(age_group_qs)
    age_order = ["0-17", "18-25", "26-35", "36-45", "46-60", "61+", "Unknown"]
    age_group_data_sorted = []

    for age_label in age_order:
        for row in age_group_data:
            if row["age_group"] == age_label:
                age_group_data_sorted.append(row)
                break

    if age_group_data_sorted:
        fig_age_group = px.bar(
            age_group_data_sorted,
            x="age_group",
            y="total_visits",
            title="Visits by Age Group",
            labels={"age_group": "Age Group", "total_visits": "Visits"},
        )
        fig_age_group.update_layout(height=460, margin=dict(l=30, r=30, t=60, b=60))
        chart_age_group = plot(fig_age_group, output_type="div", include_plotlyjs=False)
    else:
        chart_age_group = None

    # -----------------------------
    # Top Cities by Visits
    # -----------------------------
    top_cities_qs = (
        encounters_for_general.exclude(hospital__city__isnull=True)
        .exclude(hospital__city__exact="")
        .values("hospital__city")
        .annotate(total_visits=Count("encounter_id"))
        .order_by("-total_visits")[:top_n]
    )
    top_cities_data = list(top_cities_qs)

    if top_cities_data:
        fig_cities = px.bar(
            top_cities_data,
            x="hospital__city",
            y="total_visits",
            title=f"Top {top_n} Cities by Visits",
            labels={"hospital__city": "City", "total_visits": "Visits"},
        )
        fig_cities.update_layout(height=450, xaxis_tickangle=-35, margin=dict(l=30, r=30, t=60, b=110))
        chart_cities = plot(fig_cities, output_type="div", include_plotlyjs=False)
    else:
        chart_cities = None

    # -----------------------------
    # Top Insurance Providers
    # -----------------------------
    payer_name_subquery = (
        RawPayer.objects
        .filter(payer_id=OuterRef("payer_id"))
        .exclude(name__isnull=True)
        .exclude(name__exact="")
        .values("name")[:1]
    )

    payer_chart_qs = (
        encounters_for_general.exclude(payer_id__isnull=True)
        .exclude(payer_id__exact="")
        .annotate(payer_display=Subquery(payer_name_subquery))
        .values("payer_id", "payer_display")
        .annotate(total_visits=Count("encounter_id"))
        .order_by("-total_visits")
    )

    payer_chart_data = []
    for row in payer_chart_qs:
        payer_name = row["payer_display"] if row["payer_display"] else row["payer_id"]
        payer_chart_data.append({
            "payer_name": payer_name,
            "total_visits": row["total_visits"],
        })

    payer_chart_data = payer_chart_data[:top_n]

    if payer_chart_data:
        fig_payers = px.bar(
            payer_chart_data,
            x="payer_name",
            y="total_visits",
            title=f"Top {top_n} Insurance Providers",
            labels={"payer_name": "Insurance Provider", "total_visits": "Visits"},
        )
        fig_payers.update_layout(height=450, xaxis_tickangle=-35, margin=dict(l=30, r=30, t=60, b=110))
        chart_payers = plot(fig_payers, output_type="div", include_plotlyjs=False)
    else:
        chart_payers = None

    # -----------------------------
    # Predictive card data FROM PKL
    # -----------------------------
    metric_title_map = {
        "visits": "Hospital Visit Trend",
        "patients": "Patient Trend",
        "hospitals": "Hospital Count Trend",
    }

    chart_predictive = None
    chart_compare_monthly = None
    prediction_summary_label = None
    prediction_summary_value = None
    predictive_years = []
    month_options = [
        ("", "All Months"),
        ("1", "Jan"), ("2", "Feb"), ("3", "Mar"), ("4", "Apr"),
        ("5", "May"), ("6", "Jun"), ("7", "Jul"), ("8", "Aug"),
        ("9", "Sep"), ("10", "Oct"), ("11", "Nov"), ("12", "Dec"),
    ]

    pkl_data = load_prediction(pred_metric, pred_model)

    if pkl_data:
        historical_df = _normalize_pkl_series(pkl_data.get("train"))
        future_df = _normalize_pkl_series(pkl_data.get("future"))

        if not historical_df.empty:
            historical_df["series_type"] = "Historical"
        if not future_df.empty:
            future_df["series_type"] = "Forecast"

        combined_df = pd.concat(
            [historical_df, future_df],
            ignore_index=True
        ).sort_values("month_start") if (not historical_df.empty or not future_df.empty) else pd.DataFrame()

        if not combined_df.empty:
            combined_df["year"] = combined_df["month_start"].dt.year
            combined_df["month_num"] = combined_df["month_start"].dt.month
            combined_df["month_name"] = combined_df["month_start"].dt.strftime("%b")

            predictive_years = sorted(combined_df["year"].dropna().unique().tolist())

            if not pred_year and predictive_years:
                pred_year = str(predictive_years[0])

            chart_df = combined_df.copy()

            if pred_year:
                try:
                    pred_year_int = int(pred_year)
                    chart_df = chart_df[chart_df["year"] == pred_year_int].copy()
                except ValueError:
                    pass

            summary_df = chart_df.copy()

            if pred_month:
                try:
                    pred_month_int = int(pred_month)
                    summary_df = summary_df[summary_df["month_num"] == pred_month_int].copy()
                except ValueError:
                    pred_month_int = None
            else:
                pred_month_int = None

            if not summary_df.empty:
                selected_metric_title = metric_title_map[pred_metric].replace(" Trend", "")

                if pred_month_int:
                    month_label = pd.Timestamp(year=2000, month=pred_month_int, day=1).strftime("%b")
                    last_row = summary_df.sort_values(["month_start", "series_type"]).iloc[-1]
                    value_type = "Predicted" if last_row["series_type"] == "Forecast" else "Actual"
                    prediction_summary_label = f"{value_type} {selected_metric_title} for {month_label} {int(last_row['year'])}"
                    prediction_summary_value = f"{last_row['plot_value']:.0f}"
                else:
                    forecast_exists = (summary_df["series_type"] == "Forecast").any()
                    value_type = "Predicted" if forecast_exists else "Actual"
                    total_value = summary_df["plot_value"].sum()
                    year_label = int(summary_df["year"].iloc[0]) if not summary_df.empty else ""
                    prediction_summary_label = f"Total {value_type} {selected_metric_title} for {year_label}"
                    prediction_summary_value = f"{total_value:.0f}"

            if not chart_df.empty:
                chart_df = chart_df.sort_values(["month_start", "series_type"]).copy()

                fig = go.Figure()

                hist_year_df = chart_df[chart_df["series_type"] == "Historical"].copy()
                fcst_year_df = chart_df[chart_df["series_type"] == "Forecast"].copy()

                if not hist_year_df.empty:
                    fig.add_trace(go.Scatter(
                        x=hist_year_df["month_name"],
                        y=hist_year_df["plot_value"],
                        mode="lines+markers",
                        name="Historical",
                        line=dict(width=3),
                        hovertemplate="Month=%{x}<br>Actual=%{y:.0f}<extra></extra>",
                    ))

                if not fcst_year_df.empty:
                    bridge_x = []
                    bridge_y = []

                    if not hist_year_df.empty:
                        bridge_x.append(hist_year_df["month_name"].iloc[-1])
                        bridge_y.append(hist_year_df["plot_value"].iloc[-1])

                    bridge_x.extend(list(fcst_year_df["month_name"]))
                    bridge_y.extend(list(fcst_year_df["plot_value"]))

                    fig.add_trace(go.Scatter(
                        x=bridge_x,
                        y=bridge_y,
                        mode="lines+markers",
                        name="Forecast",
                        line=dict(width=3, dash="dash"),
                        hovertemplate="Month=%{x}<br>Forecast=%{y:.0f}<extra></extra>",
                    ))

                if not future_df.empty:
                    forecast_start_month_name = future_df["month_start"].iloc[0].strftime("%b")
                    forecast_start_year = future_df["month_start"].iloc[0].year
                    if pred_year and str(forecast_start_year) == str(pred_year):
                        fig.add_shape(
                            type="line",
                            x0=forecast_start_month_name,
                            x1=forecast_start_month_name,
                            y0=0,
                            y1=1,
                            xref="x",
                            yref="paper",
                            line=dict(color="red", dash="dot", width=2),
                        )

                        fig.add_annotation(
                            x=forecast_start_month_name,
                            y=1,
                            xref="x",
                            yref="paper",
                            text="Forecast Start",
                            showarrow=False,
                            yshift=10,
                            font=dict(color="red"),
                        )

                fig.update_layout(
                    title=f"{metric_title_map[pred_metric]} ({pred_model.replace('_', ' ').title()})",
                    height=560,
                    margin=dict(l=30, r=30, t=70, b=50),
                    xaxis_title="Month",
                    yaxis_title=metric_title_map[pred_metric].replace(" Trend", ""),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="center",
                        x=0.5
                    )
                )

                fig.update_xaxes(
                    categoryorder="array",
                    categoryarray=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                )

                chart_predictive = plot(fig, output_type="div", include_plotlyjs=False)

    # -----------------------------
    # Comparison graph from PKL
    # -----------------------------
    rf_data = load_prediction(pred_metric, "random_forest")
    xgb_data = load_prediction(pred_metric, "xgboost")

    if rf_data and xgb_data:
        hist_compare_df = _normalize_pkl_series(rf_data.get("train"))
        rf_future_df = _normalize_pkl_series(rf_data.get("future"))
        xgb_future_df = _normalize_pkl_series(xgb_data.get("future"))

        if not hist_compare_df.empty and (not rf_future_df.empty or not xgb_future_df.empty):
            fig_compare = go.Figure()

            fig_compare.add_trace(go.Scatter(
                x=hist_compare_df["month_start"],
                y=hist_compare_df["plot_value"],
                mode="lines",
                name="Historical Actual",
                line=dict(width=3),
                hovertemplate="Date=%{x|%b %Y}<br>Historical=%{y:.0f}<extra></extra>",
            ))

            rf_x = []
            rf_y = []
            if not hist_compare_df.empty:
                rf_x.append(hist_compare_df["month_start"].iloc[-1])
                rf_y.append(hist_compare_df["plot_value"].iloc[-1])
            rf_x.extend(list(rf_future_df["month_start"]))
            rf_y.extend(list(rf_future_df["plot_value"]))

            if rf_x and rf_y:
                fig_compare.add_trace(go.Scatter(
                    x=rf_x,
                    y=rf_y,
                    mode="lines",
                    name="Random Forest - Future",
                    line=dict(width=3, dash="dash"),
                    hovertemplate="Date=%{x|%b %Y}<br>Random Forest=%{y:.0f}<extra></extra>",
                ))

            xgb_x = []
            xgb_y = []
            if not hist_compare_df.empty:
                xgb_x.append(hist_compare_df["month_start"].iloc[-1])
                xgb_y.append(hist_compare_df["plot_value"].iloc[-1])
            xgb_x.extend(list(xgb_future_df["month_start"]))
            xgb_y.extend(list(xgb_future_df["plot_value"]))

            if xgb_x and xgb_y:
                fig_compare.add_trace(go.Scatter(
                    x=xgb_x,
                    y=xgb_y,
                    mode="lines",
                    name="XGBoost - Future",
                    line=dict(width=3, dash="dot"),
                    hovertemplate="Date=%{x|%b %Y}<br>XGBoost=%{y:.0f}<extra></extra>",
                ))

            fig_compare.update_layout(
                title=f"{metric_title_map[pred_metric].replace(' Trend', '')}: Historical and Future Monthly Comparison",
                height=560,
                margin=dict(l=30, r=30, t=70, b=50),
                xaxis_title="Year",
                yaxis_title=metric_title_map[pred_metric].replace(" Trend", ""),
                hovermode="x unified",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                )
            )

            chart_compare_monthly = plot(fig_compare, output_type="div", include_plotlyjs=False)

    # -----------------------------
    # Top States by Visits
    # -----------------------------
    state_visits_qs = (
        encounters_for_general.exclude(hospital__state__isnull=True)
        .exclude(hospital__state__exact="")
        .values("hospital__state")
        .annotate(total_visits=Count("encounter_id"))
        .order_by("-total_visits")[:top_n]
    )
    state_visits_data = list(state_visits_qs)

    if state_visits_data:
        fig_states = px.bar(
            state_visits_data,
            x="hospital__state",
            y="total_visits",
            title=f"Top {top_n} States by Visits",
            labels={"hospital__state": "State", "total_visits": "Visits"},
        )
        fig_states.update_layout(height=460, xaxis_tickangle=-35, margin=dict(l=30, r=30, t=60, b=80))
        chart_states = plot(fig_states, output_type="div", include_plotlyjs=False)
    else:
        chart_states = None

    # -----------------------------
    # State Cost / Coverage / Out-of-Pocket
    # -----------------------------
    coverage_state_qs = (
        encounters_for_general.exclude(hospital__state__isnull=True)
        .exclude(hospital__state__exact="")
        .values("hospital__state")
        .annotate(
            avg_total_claim=Avg("total_claim_cost"),
            avg_coverage=Avg("payer_coverage"),
            avg_out_of_pocket=Avg("out_of_pocket"),
        )
        .order_by("-avg_coverage")[:top_n]
    )

    coverage_state_data = list(coverage_state_qs)

    if coverage_state_data:
        long_data = []
        for row in coverage_state_data:
            state_name = row["hospital__state"]
            long_data.append({"state": state_name, "metric": "Avg Total Claim Cost", "value": row["avg_total_claim"] or 0})
            long_data.append({"state": state_name, "metric": "Avg Coverage", "value": row["avg_coverage"] or 0})
            long_data.append({"state": state_name, "metric": "Avg Out of Pocket", "value": row["avg_out_of_pocket"] or 0})

        fig_coverage_state = px.bar(
            long_data,
            x="state",
            y="value",
            color="metric",
            barmode="group",
            title=f"Top {top_n} States: Cost vs Coverage vs Out-of-Pocket",
            labels={"state": "State", "value": "Amount", "metric": "Metric"},
        )
        fig_coverage_state.update_layout(height=460, xaxis_tickangle=-35, margin=dict(l=30, r=30, t=60, b=90))
        chart_coverage_state = plot(fig_coverage_state, output_type="div", include_plotlyjs=False)
    else:
        chart_coverage_state = None

    # -----------------------------
    # USA hotspot map
    # -----------------------------
    usa_map_qs = (
        encounters_for_general.exclude(hospital__state__isnull=True)
        .exclude(hospital__state__exact="")
        .values("hospital__state")
        .annotate(total_visits=Count("encounter_id"))
        .order_by("-total_visits")
    )

    usa_map_data = []
    for row in usa_map_qs:
        state_name = row["hospital__state"]
        abbr = US_STATE_ABBR.get(state_name, state_name if len(state_name) == 2 else None)
        if abbr:
            usa_map_data.append({
                "state_name": state_name,
                "state_code": abbr,
                "total_visits": row["total_visits"],
            })

    if usa_map_data:
        fig_usa_map = px.choropleth(
            usa_map_data,
            locations="state_code",
            locationmode="USA-states",
            color="total_visits",
            scope="usa",
            hover_name="state_name",
            title="USA State Hotspot by Visits",
        )
        fig_usa_map.update_layout(height=650, margin=dict(l=10, r=10, t=60, b=10))
        chart_usa_map = plot(fig_usa_map, output_type="div", include_plotlyjs=False)
    else:
        chart_usa_map = None

    context = {
        "states": states,
        "cities": cities,
        "years": years,
        "selected_state": selected_state,
        "selected_city": selected_city,
        "selected_year": selected_year,
        "selected_top_n": str(top_n),

        "total_patients": total_patients,
        "total_hospitals": total_hospitals,
        "total_visits": total_visits,
        "total_states": total_states,
        "total_cities": total_cities,

        "chart_age_group": chart_age_group,
        "chart_cities": chart_cities,
        "chart_payers": chart_payers,
        "chart_predictive": chart_predictive,
        "chart_states": chart_states,
        "chart_coverage_state": chart_coverage_state,
        "chart_usa_map": chart_usa_map,
        "chart_compare_monthly": chart_compare_monthly,

        "pred_metric": pred_metric,
        "pred_model": pred_model,
        "pred_year": pred_year,
        "pred_month": pred_month,
        "predictive_years": predictive_years,
        "month_options": month_options,
        "prediction_summary_label": prediction_summary_label,
        "prediction_summary_value": prediction_summary_value,
    }

    return render(request, "core/developer/data_dashboard.html", context)


### ChatBOT

@csrf_exempt
@require_POST
def chatbot_message_view(request):
    """
    Global assistant:
    asks state -> city -> gender -> insurance -> metric
    and returns top hospitals
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}

    user_message = (data.get("message") or "").strip()
    session_key = "hospital_chatbot_state"

    state_data = request.session.get(session_key)
    if not state_data:
        state_data = get_initial_state(hospital_id=None)

    if not user_message:
        reply = "Which state are you looking for?"
        request.session[session_key] = state_data
        request.session.modified = True
        return JsonResponse({
            "ok": True,
            "reply": reply,
            "state": state_data,
        })

    updated_state, reply = process_chat_message(
        user_message=user_message,
        state_data=state_data,
        hospital_id=None,
    )

    request.session[session_key] = updated_state
    request.session.modified = True

    return JsonResponse({
        "ok": True,
        "reply": reply,
        "state": updated_state,
    })


@csrf_exempt
@require_POST
def hospital_detail_chatbot_message_view(request, hospital_id):
    """
    Hospital detail assistant:
    asks only gender + insurance provider
    then gives quick hospital summary
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}

    user_message = (data.get("message") or "").strip()
    session_key = f"hospital_detail_chatbot_state_{hospital_id}"

    state_data = request.session.get(session_key)
    if not state_data:
        state_data = get_initial_state(hospital_id=hospital_id)

    if not user_message:
        reply = "For this hospital, do you want a gender filter? Type Male / Female / Other or 'skip'."
        request.session[session_key] = state_data
        request.session.modified = True
        return JsonResponse({
            "ok": True,
            "reply": reply,
            "state": state_data,
        })

    updated_state, reply = process_chat_message(
        user_message=user_message,
        state_data=state_data,
        hospital_id=hospital_id,
    )

    request.session[session_key] = updated_state
    request.session.modified = True

    return JsonResponse({
        "ok": True,
        "reply": reply,
        "state": updated_state,
    })