# core/urls.py - Version corrigée
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ServiceViewSet,
    CategoryViewSet,
    ClassificationRuleViewSet,
    AuditLogViewSet
    # NE PAS importer ServiceMembersViewSet car il n'existe plus
)

router = DefaultRouter()
router.register(r"services", ServiceViewSet, basename="service")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"rules", ClassificationRuleViewSet, basename="rule")
router.register(r"auditlogs", AuditLogViewSet, basename="auditlog")

urlpatterns = router.urls