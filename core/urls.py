from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("recommendations/", views.recommendations_view, name="recommendations"),
    path("hospital/<int:hospital_id>/", views.hospital_detail_view, name="hospital_detail"),
    path("compare/", views.compare_view, name="compare_hospitals"),

    path("developer/", views.developer_dashboard, name="developer_dashboard"),
    path("developer/upload/", views.batch_upload_view, name="batch_upload"),
    path("developer/history/", views.batch_history_view, name="batch_history"),
    path("developer/batch/<int:batch_id>/", views.batch_detail_view, name="batch_detail"),
    path("developer/batch/<int:batch_id>/sync/", views.sync_batch_view, name="sync_batch"),
    path("developer/batch/<int:batch_id>/rollback/", views.rollback_batch_view, name="rollback_batch"),
    path("developer/rebuild/", views.rebuild_master_view, name="rebuild_master"),
    path("developer/batch/<int:batch_id>/delete-data/", views.delete_batch_data_view, name="delete_batch_data"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("assistant/chat/", views.chatbot_message_view, name="chatbot_message"),
    path("assistant/chat/hospital/<int:hospital_id>/", views.hospital_detail_chatbot_message_view, name="hospital_detail_chatbot_message"),
]