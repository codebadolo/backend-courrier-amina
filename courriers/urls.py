# courriers/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourrierViewSet, ImputationViewSet,
    PieceJointeViewSet, ModeleCourrierViewSet,
    ImputationDashboardViewSet, CourrierDownloadTextView,
    AgentServiceDashboardViewSet, CourrierAnalyzeAIView,
    CourrierTraitementViewSet, GenererPDFView,
)

router = DefaultRouter()
router.register(r"courriers", CourrierViewSet, basename="courrier")
router.register(r"imputations", ImputationViewSet, basename="imputation")
router.register(r"pieces-jointes", PieceJointeViewSet, basename="piecejointe")
router.register(r"modeles", ModeleCourrierViewSet, basename="modelecourrier")
router.register(r"imputation-dashboard", ImputationDashboardViewSet, basename="imputation-dashboard")
router.register(r"agent-dashboard", AgentServiceDashboardViewSet, basename='agent-dashboard')
router.register(r"traitement", CourrierTraitementViewSet, basename="traitement")  # ← UNIQUE

urlpatterns = [
    path('', include(router.urls)),
    # Vues spéciales hors ViewSet
    path('courriers/analyze_complete/', CourrierViewSet.as_view({'post': 'analyze_complete'}), name='analyze-complete'),
    path('courriers/<int:pk>/export_pdf/', CourrierViewSet.as_view({'get': 'export_pdf'}), name='courrier-export-pdf'),
    path('courriers/<int:pk>/download-text/', CourrierDownloadTextView.as_view(), name='download_text'),
    path('analyse_ia/', CourrierAnalyzeAIView.as_view(), name='analyse_ia'),
    # Dans courriers/urls.py
    path('courriers/tableau_bord_assignation/', 
        CourrierViewSet.as_view({'get': 'tableau_bord_assignation'}), 
        name='tableau-bord-assignation'),
    path('courriers/<int:pk>/agents_disponibles/', 
        CourrierViewSet.as_view({'get': 'agents_disponibles'}), 
        name='agents-disponibles'),
    path('courriers/<int:pk>/assignation_multi_criteres/', 
        CourrierViewSet.as_view({'post': 'assignation_multi_criteres'}), 
        name='assignation-multi-criteres'),
    path('courriers/<int:pk>/demarrer_analyse/', 
        CourrierViewSet.as_view({'post': 'demarrer_analyse'}), 
        name='courrier-demarrer-analyse'),
    path('courriers/<int:pk>/enregistrer_analyse/', 
        CourrierViewSet.as_view({'post': 'enregistrer_analyse'}), 
        name='courrier-enregistrer-analyse'),
    path('courriers/<int:pk>/services_consultables/', 
        CourrierViewSet.as_view({'get': 'services_consultables'}), 
        name='courrier-services-consultables'),
    path('courriers/<int:pk>/consulter_service/', 
        CourrierViewSet.as_view({'post': 'consulter_service'}), 
        name='courrier-consulter-service'),
   
    path('courriers/<int:pk>/soumettre-validation/', 
        CourrierTraitementViewSet.as_view({'post': 'soumettre_validation'}), 
        name='soumettre-validation'),
    path('courriers/generer-pdf/', GenererPDFView.as_view(), name='generer-pdf'), 


    path('courriers/<int:pk>/soumettre-validation/', 
         CourrierViewSet.as_view({'post': 'soumettre_validation'}), 
         name='courrier-soumettre-validation'),
    path('courriers/<int:pk>/valider/', 
         CourrierViewSet.as_view({'post': 'valider'}), 
         name='courrier-valider'),
    path('courriers/<int:pk>/signer/',CourrierViewSet.as_view({'post': 'signer'}), name='courrier-signer'),
    path('courriers/<int:pk>/envoyer/', 
         CourrierViewSet.as_view({'post': 'envoyer'}), 
         name='courrier-envoyer'),
]