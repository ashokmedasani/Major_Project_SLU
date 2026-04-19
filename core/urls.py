from django.urls import path
from . import views

urlpatterns = [
        # user pages
    path("", views.home_view, name="home"),
    path("recommendations/", views.recommendations_view, name="recommendations"),
    path("hospital/<int:hospital_id>/", views.hospital_detail_view, name="hospital_detail"),
    path("compare/", views.compare_view, name="compare_hospitals"),

    # developer auth
    path("developer/login/", views.developer_login, name="developer_login"),
    path("developer/request-access/", views.developer_request_access, name="developer_request_access"),
    path("developer/logout/", views.developer_logout, name="developer_logout"),

    # developer pages
    path("developer/", views.developer_dashboard, name="developer_dashboard"),
    path("developer/data-dashboard/", views.developer_data_dashboard, name="developer_data_dashboard"),
    path("developer/upload/", views.batch_upload_view, name="batch_upload"),
    path("developer/batches/", views.batch_history_view, name="batch_history"),
    path("developer/batches/<int:batch_id>/", views.batch_detail_view, name="batch_detail"),

    # batch actions
    path("developer/batches/<int:batch_id>/sync/", views.sync_batch_view, name="sync_batch"),
    path("developer/batches/<int:batch_id>/unsync/", views.unsync_batch_view, name="unsync_batch"),
    path("developer/batches/<int:batch_id>/recycle/", views.recycle_batch_view, name="recycle_batch"),
    path("developer/batches/<int:batch_id>/restore/", views.restore_batch_view, name="restore_batch"),
    path("developer/batches/<int:batch_id>/delete/", views.delete_batch_view, name="delete_batch"),
    # Predictions
    path("developer/predictions/", views.prediction_dashboard, name="prediction_dashboard"),
    path("developer/predictions/train/", views.train_all_models, name="train_models"),

    path("assistant/chat/", views.chatbot_message_view, name="chatbot_message"),
    path(
        "assistant/chat/hospital/<int:hospital_id>/",
        views.hospital_detail_chatbot_message_view,
        name="hospital_detail_chatbot_message",
    ),
]