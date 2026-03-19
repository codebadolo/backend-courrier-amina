# dashboard/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DashboardViewSet

router = DefaultRouter()
router.register(r'', DashboardViewSet, basename='dashboard')

urlpatterns = [
    # ── Actions explicites AVANT le router ──────────────────────
    # Sans cela, DRF ne sait pas mapper GET /stats/ → .stats()
    path('stats/',          DashboardViewSet.as_view({'get': 'stats'}),          name='dashboard-stats'),
    path('trends/',         DashboardViewSet.as_view({'get': 'trends'}),         name='dashboard-trends'),
    path('performance/',    DashboardViewSet.as_view({'get': 'performance'}),    name='dashboard-performance'),
    path('role-dashboard/', DashboardViewSet.as_view({'get': 'role_dashboard'}), name='dashboard-role'),
    path('widgets/',        DashboardViewSet.as_view({'get': 'widgets'}),        name='dashboard-widgets'),
    path('export/',         DashboardViewSet.as_view({'get': 'export'}),         name='dashboard-export'),

    # ── Router (liste / détail des rapports) ────────────────────
    path('', include(router.urls)),
]