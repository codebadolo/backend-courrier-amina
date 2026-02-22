# ia/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IAResultViewSet , TestGeminiAPIView, BatchTestGeminiAPIView, AnalyserCourrierAPIView, GenererReponseAPIView, BatchAnalyserCourriersAPIView

router = DefaultRouter()
router.register(r"results", IAResultViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('test-gemini/', TestGeminiAPIView.as_view(), name='test-gemini'),
    path('test-gemini/batch/', BatchTestGeminiAPIView.as_view(), name='test-gemini-batch'),
    path('courriers/<int:courrier_id>/analyser/', AnalyserCourrierAPIView.as_view(), name='analyser-courrier'),
    path('courriers/<int:courrier_id>/generer-reponse/', GenererReponseAPIView.as_view(), name='generer-reponse'),
    path('courriers/batch-analyser/', BatchAnalyserCourriersAPIView.as_view(), name='batch-analyser'),
]