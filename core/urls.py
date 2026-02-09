from django.urls import path
from . import views

urlpatterns = [
    path("data-health/", views.data_health, name="data_health"),
    path("data-schema/", views.data_schema, name="data_schema"),
]
