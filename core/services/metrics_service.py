from django.db.models import Avg, Count
from core.models import MasterPatient, MasterEncounter, MasterHospital, HospitalSummary


def get_home_kpis():
    return {
        "total_patients": MasterPatient.objects.count(),
        "total_visits": MasterEncounter.objects.count(),
        "total_hospitals": MasterHospital.objects.count(),
        "avg_cost": MasterEncounter.objects.aggregate(v=Avg("total_claim_cost"))["v"] or 0,
        "avg_coverage": MasterEncounter.objects.aggregate(v=Avg("payer_coverage"))["v"] or 0,
    }


def get_top_hospitals_by_visits(limit=10):
    return HospitalSummary.objects.select_related("hospital").order_by("-total_visits")[:limit]


def get_top_hospitals_by_coverage(limit=10):
    return HospitalSummary.objects.select_related("hospital").order_by("-coverage_ratio")[:limit]


def get_top_recommended_hospitals(limit=5):
    return HospitalSummary.objects.select_related("hospital").order_by("-weighted_score")[:limit]