from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkflowViewSet, WorkflowStepViewSet,
    WorkflowTemplateViewSet, AccuseViewSet,
)

router = DefaultRouter()
router.register(r"workflows", WorkflowViewSet, basename="workflow")
router.register(r"steps", WorkflowStepViewSet, basename="workflowstep")
router.register(r"templates", WorkflowTemplateViewSet, basename="workflowtemplate")
router.register(r"accuses", AccuseViewSet, basename="accuse")
# router.register(r"actions", WorkflowActionViewSet, basename="workflowaction")

urlpatterns = [
    path('', include(router.urls)),
]