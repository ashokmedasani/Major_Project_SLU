# core/services/chatbot.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.apps import apps
from django.db.models import Avg, Count, F, Q


APP_LABEL = "core"


# -----------------------------
# MODEL LOADERS
# -----------------------------
def get_model(model_name: str):
    return apps.get_model(APP_LABEL, model_name)


MasterHospital = get_model("MasterHospital")
MasterEncounter = get_model("MasterEncounter")


# -----------------------------
# SAFE FIELD HELPERS
# -----------------------------
def model_field_names(model) -> set:
    return {f.name for f in model._meta.get_fields()}


def has_field(model, field_name: str) -> bool:
    return field_name in model_field_names(model)


def first_existing_field(model, candidates: List[str]) -> Optional[str]:
    names = model_field_names(model)
    for c in candidates:
        if c in names:
            return c
    return None


def get_hospital_name_field() -> str:
    return first_existing_field(MasterHospital, ["name", "hospital_name", "organization_name"]) or "name"


def get_hospital_state_field() -> str:
    return first_existing_field(MasterHospital, ["state", "address_state", "province"]) or "state"


def get_hospital_city_field() -> str:
    return first_existing_field(MasterHospital, ["city", "address_city", "municipality"]) or "city"


def get_encounter_cost_field() -> str:
    return first_existing_field(
        MasterEncounter,
        ["total_claim_cost", "total_cost", "encounter_cost", "base_encounter_cost"]
    ) or "total_claim_cost"


def get_encounter_coverage_field() -> str:
    return first_existing_field(
        MasterEncounter,
        ["payer_coverage", "coverage_amount", "covered_amount"]
    ) or "payer_coverage"


def get_encounter_oop_field() -> str:
    return first_existing_field(
        MasterEncounter,
        ["out_of_pocket", "oop_amount", "patient_pay"]
    ) or "out_of_pocket"


def get_encounter_start_field() -> str:
    return first_existing_field(
        MasterEncounter,
        ["start", "encounter_date", "visit_date", "date"]
    ) or "start"


def get_patient_gender_lookup() -> Optional[str]:
    # MasterEncounter -> patient -> gender
    encounter_fields = model_field_names(MasterEncounter)
    if "patient" in encounter_fields:
        patient_model = MasterEncounter._meta.get_field("patient").related_model
        if has_field(patient_model, "gender"):
            return "patient__gender"
        if has_field(patient_model, "sex"):
            return "patient__sex"
    return None


def get_insurance_lookup() -> Optional[str]:
    """
    Try direct encounter fields first, then common related paths.
    """
    direct_candidates = [
        "insurance_provider_name",
        "payer_name",
        "insurance_name",
        "payer_id",  # fallback if only payer_id exists
    ]
    for c in direct_candidates:
        if has_field(MasterEncounter, c):
            return c

    # Check related payer if it exists
    if has_field(MasterEncounter, "payer"):
        payer_model = MasterEncounter._meta.get_field("payer").related_model
        if has_field(payer_model, "name"):
            return "payer__name"
        if has_field(payer_model, "payer_name"):
            return "payer__payer_name"

    return None


# -----------------------------
# NORMALIZATION
# -----------------------------
def clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def normalize_skip(value: str) -> bool:
    value = clean_text(value).lower()
    return value in {"skip", "none", "na", "n/a", "no", "not needed", "any", "all"}


def normalize_metric(value: str) -> str:
    v = clean_text(value).lower()
    if "coverage" in v:
        return "coverage"
    if "visit" in v:
        return "visits"
    if "oop" in v or "out of pocket" in v:
        return "oop"
    return "cost"


def title_case_or_empty(value: str) -> str:
    value = clean_text(value)
    return value.title() if value else ""


# -----------------------------
# DATABASE CHOICES
# -----------------------------
def get_distinct_states() -> List[str]:
    state_field = get_hospital_state_field()
    values = (
        MasterHospital.objects.exclude(**{f"{state_field}__isnull": True})
        .exclude(**{state_field: ""})
        .values_list(state_field, flat=True)
        .distinct()
        .order_by(state_field)
    )
    return [v for v in values if v]


def get_distinct_cities(state: Optional[str] = None) -> List[str]:
    city_field = get_hospital_city_field()
    state_field = get_hospital_state_field()

    qs = MasterHospital.objects.exclude(**{f"{city_field}__isnull": True}).exclude(**{city_field: ""})
    if state:
        qs = qs.filter(**{state_field: state})

    values = qs.values_list(city_field, flat=True).distinct().order_by(city_field)
    return [v for v in values if v]


def get_distinct_genders() -> List[str]:
    gender_lookup = get_patient_gender_lookup()
    if not gender_lookup:
        return []

    values = (
        MasterEncounter.objects.exclude(**{f"{gender_lookup}__isnull": True})
        .exclude(**{gender_lookup: ""})
        .values_list(gender_lookup, flat=True)
        .distinct()
        .order_by(gender_lookup)
    )
    return [v for v in values if v]


def get_distinct_insurance_providers() -> List[str]:
    insurance_lookup = get_insurance_lookup()
    if not insurance_lookup:
        return []

    values = (
        MasterEncounter.objects.exclude(**{f"{insurance_lookup}__isnull": True})
        .exclude(**{insurance_lookup: ""})
        .values_list(insurance_lookup, flat=True)
        .distinct()
        .order_by(insurance_lookup)
    )
    return [str(v) for v in values if v]


# -----------------------------
# FILTER BUILDERS
# -----------------------------
def base_encounter_qs():
    return MasterEncounter.objects.select_related("hospital")


def apply_common_filters(qs, filters: Dict[str, Any], hospital_id: Optional[int] = None):
    state_field = get_hospital_state_field()
    city_field = get_hospital_city_field()
    gender_lookup = get_patient_gender_lookup()
    insurance_lookup = get_insurance_lookup()

    if hospital_id:
        qs = qs.filter(hospital_id=hospital_id)

    state = clean_text(filters.get("state"))
    city = clean_text(filters.get("city"))
    gender = clean_text(filters.get("gender"))
    insurance_provider = clean_text(filters.get("insurance_provider"))

    if state:
        qs = qs.filter(**{f"hospital__{state_field}": state})

    if city:
        qs = qs.filter(**{f"hospital__{city_field}": city})

    if gender and gender_lookup:
        qs = qs.filter(**{gender_lookup: gender})

    if insurance_provider and insurance_lookup:
        qs = qs.filter(**{insurance_lookup: insurance_provider})

    return qs


# -----------------------------
# RETRIEVAL / RECOMMENDATION
# -----------------------------
@dataclass
class HospitalResult:
    hospital_id: int
    hospital_name: str
    visits: int
    avg_cost: float
    avg_coverage: float
    avg_oop: float


def retrieve_top_hospitals(filters: Dict[str, Any], hospital_id: Optional[int] = None, limit: int = 5) -> List[HospitalResult]:
    cost_field = get_encounter_cost_field()
    coverage_field = get_encounter_coverage_field()
    oop_field = get_encounter_oop_field()
    hospital_name_field = get_hospital_name_field()

    qs = apply_common_filters(base_encounter_qs(), filters, hospital_id=hospital_id)

    aggregated = (
        qs.values("hospital_id", f"hospital__{hospital_name_field}")
        .annotate(
            visits=Count("id"),
            avg_cost=Avg(cost_field),
            avg_coverage=Avg(coverage_field),
            avg_oop=Avg(oop_field),
        )
    )

    metric = normalize_metric(filters.get("metric", "cost"))

    if metric == "visits":
        aggregated = aggregated.order_by("-visits")
    elif metric == "coverage":
        aggregated = aggregated.order_by("-avg_coverage", "avg_cost")
    elif metric == "oop":
        aggregated = aggregated.order_by("avg_oop", "avg_cost")
    else:
        aggregated = aggregated.order_by("avg_cost", "-avg_coverage")

    results: List[HospitalResult] = []
    for row in aggregated[:limit]:
        results.append(
            HospitalResult(
                hospital_id=row["hospital_id"],
                hospital_name=row.get(f"hospital__{hospital_name_field}", "Unknown Hospital"),
                visits=row["visits"] or 0,
                avg_cost=float(row["avg_cost"] or 0),
                avg_coverage=float(row["avg_coverage"] or 0),
                avg_oop=float(row["avg_oop"] or 0),
            )
        )
    return results


def retrieve_hospital_detail_summary(hospital_id: int, filters: Dict[str, Any]) -> Dict[str, Any]:
    hospital_name_field = get_hospital_name_field()
    cost_field = get_encounter_cost_field()
    coverage_field = get_encounter_coverage_field()
    oop_field = get_encounter_oop_field()

    try:
        hospital = MasterHospital.objects.get(pk=hospital_id)
    except MasterHospital.DoesNotExist:
        return {"found": False, "message": "Hospital not found."}

    qs = apply_common_filters(base_encounter_qs(), filters, hospital_id=hospital_id)

    stats = qs.aggregate(
        visits=Count("id"),
        avg_cost=Avg(cost_field),
        avg_coverage=Avg(coverage_field),
        avg_oop=Avg(oop_field),
    )

    return {
        "found": True,
        "hospital_id": hospital_id,
        "hospital_name": getattr(hospital, hospital_name_field, "Hospital"),
        "visits": stats["visits"] or 0,
        "avg_cost": float(stats["avg_cost"] or 0),
        "avg_coverage": float(stats["avg_coverage"] or 0),
        "avg_oop": float(stats["avg_oop"] or 0),
    }


# -----------------------------
# SIMPLE CONVERSATION ENGINE
# -----------------------------
DEFAULT_STATE = {
    "mode": "global",  # global or hospital_detail
    "step": "ask_state",
    "filters": {
        "state": "",
        "city": "",
        "gender": "",
        "insurance_provider": "",
        "metric": "",
    },
}


def get_initial_state(hospital_id: Optional[int] = None) -> Dict[str, Any]:
    data = DEFAULT_STATE.copy()
    data["filters"] = DEFAULT_STATE["filters"].copy()

    if hospital_id:
        data["mode"] = "hospital_detail"
        data["step"] = "ask_gender_hd"

    return data


def format_hospital_results(results: List[HospitalResult]) -> str:
    if not results:
        return "I could not find matching hospitals for these filters."

    lines = ["Here are the top matching hospitals:"]
    for i, r in enumerate(results, start=1):
        lines.append(
            f"{i}. {r.hospital_name} | Visits: {r.visits} | "
            f"Avg Cost: ${r.avg_cost:,.2f} | Avg Coverage: ${r.avg_coverage:,.2f} | "
            f"Avg OOP: ${r.avg_oop:,.2f}"
        )
    lines.append("You can also open Hospital Detail to inspect one hospital further.")
    return "\n".join(lines)


def format_hospital_detail(summary: Dict[str, Any]) -> str:
    if not summary.get("found"):
        return summary.get("message", "Hospital not found.")

    return (
        f"{summary['hospital_name']} summary:\n"
        f"- Visits: {summary['visits']}\n"
        f"- Avg Cost: ${summary['avg_cost']:,.2f}\n"
        f"- Avg Coverage: ${summary['avg_coverage']:,.2f}\n"
        f"- Avg OOP: ${summary['avg_oop']:,.2f}"
    )


def next_question_for_global(step: str, filters: Dict[str, Any]) -> str:
    if step == "ask_state":
        return "Which state are you looking for?"
    if step == "ask_city":
        return "Which city do you want? Type 'skip' if you want all cities."
    if step == "ask_gender":
        return "Do you want a gender filter? Type Male / Female / Other or 'skip'."
    if step == "ask_insurance":
        return "Do you want an insurance provider filter? Type provider name or 'skip'."
    if step == "ask_metric":
        return "What matters most? Type: cost, coverage, visits, or oop."
    return "Tell me your requirement."


def next_question_for_hospital_detail(step: str) -> str:
    if step == "ask_gender_hd":
        return "For this hospital, do you want a gender filter? Type Male / Female / Other or 'skip'."
    if step == "ask_insurance_hd":
        return "For this hospital, do you want an insurance provider filter? Type provider name or 'skip'."
    return "Tell me what you want to know about this hospital."


def process_chat_message(
    user_message: str,
    state_data: Dict[str, Any],
    hospital_id: Optional[int] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Returns updated_state, bot_reply
    """

    user_message = clean_text(user_message)
    if not state_data:
        state_data = get_initial_state(hospital_id=hospital_id)

    mode = state_data.get("mode", "global")
    step = state_data.get("step", "ask_state")
    filters = state_data.get("filters", {}).copy()

    if user_message.lower() in {"restart", "reset", "start over"}:
        new_state = get_initial_state(hospital_id=hospital_id)
        if hospital_id:
            return new_state, next_question_for_hospital_detail(new_state["step"])
        return new_state, next_question_for_global(new_state["step"], new_state["filters"])

    # -----------------------------
    # GLOBAL FLOW
    # -----------------------------
    if mode == "global":
        if step == "ask_state":
            filters["state"] = title_case_or_empty(user_message)
            state_data["filters"] = filters
            state_data["step"] = "ask_city"
            return state_data, next_question_for_global("ask_city", filters)

        if step == "ask_city":
            filters["city"] = "" if normalize_skip(user_message) else title_case_or_empty(user_message)
            state_data["filters"] = filters
            state_data["step"] = "ask_gender"
            return state_data, next_question_for_global("ask_gender", filters)

        if step == "ask_gender":
            filters["gender"] = "" if normalize_skip(user_message) else title_case_or_empty(user_message)
            state_data["filters"] = filters
            state_data["step"] = "ask_insurance"
            return state_data, next_question_for_global("ask_insurance", filters)

        if step == "ask_insurance":
            filters["insurance_provider"] = "" if normalize_skip(user_message) else user_message.strip()
            state_data["filters"] = filters
            state_data["step"] = "ask_metric"
            return state_data, next_question_for_global("ask_metric", filters)

        if step == "ask_metric":
            filters["metric"] = normalize_metric(user_message)
            state_data["filters"] = filters
            state_data["step"] = "done"

            results = retrieve_top_hospitals(filters, hospital_id=None, limit=5)
            return state_data, format_hospital_results(results)

        # done → allow quick re-query
        if step == "done":
            if "hospital" in user_message.lower():
                results = retrieve_top_hospitals(filters, hospital_id=None, limit=5)
                return state_data, format_hospital_results(results)

            return (
                state_data,
                "Type 'restart' to choose filters again, or ask for hospitals again."
            )

    # -----------------------------
    # HOSPITAL DETAIL FLOW
    # -----------------------------
    if mode == "hospital_detail":
        if step == "ask_gender_hd":
            filters["gender"] = "" if normalize_skip(user_message) else title_case_or_empty(user_message)
            state_data["filters"] = filters
            state_data["step"] = "ask_insurance_hd"
            return state_data, next_question_for_hospital_detail("ask_insurance_hd")

        if step == "ask_insurance_hd":
            filters["insurance_provider"] = "" if normalize_skip(user_message) else user_message.strip()
            state_data["filters"] = filters
            state_data["step"] = "done_hd"

            summary = retrieve_hospital_detail_summary(hospital_id=hospital_id, filters=filters)
            return state_data, format_hospital_detail(summary)

        if step == "done_hd":
            summary = retrieve_hospital_detail_summary(hospital_id=hospital_id, filters=filters)
            return (
                state_data,
                format_hospital_detail(summary) + "\n\nType 'restart' to change gender/insurance filters."
            )

    return state_data, "Sorry, I did not understand that. Type 'restart' to start again."