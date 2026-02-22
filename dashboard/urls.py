from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DashboardViewSet

router = DefaultRouter()
# router.register(r"rapports", RapportStatistiqueViewSet)
# router.register(r"rapports", RapportStatistiqueViewSet, basename="rapportstatistique")


urlpatterns = [
    path('', include(router.urls)),
    path('stats/', DashboardViewSet.as_view({'get': 'stats'}), name='dashboard-stats'),
    path('trends/', DashboardViewSet.as_view({'get': 'trends'}), name='dashboard-trends'),
    path('performance/', DashboardViewSet.as_view({'get': 'performance'}), name='dashboard-performance')
]
