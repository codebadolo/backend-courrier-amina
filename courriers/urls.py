# courriers/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourrierViewSet, ImputationViewSet,
    PieceJointeViewSet, ModeleCourrierViewSet,
    ImputationDashboardViewSet, CourrierDownloadTextView,
    AgentServiceDashboardViewSet, CourrierAnalyzeAIView,
    CourrierTraitementViewSet, GenererPDFView, gemini_ocr
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
    path('ocr-gemini/', gemini_ocr, name='courrier-ocr-gemini'),
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
    # Dans courriers/urls.py

    # Gestion des courriers entrants pour les chefs
    path('courriers/<int:pk>/membres-service/', 
         CourrierViewSet.as_view({'get': 'membres_service'}), 
         name='courrier-membres-service'),
    path('courriers/<int:pk>/affecter-membre/', 
         CourrierViewSet.as_view({'post': 'affecter_membre'}), 
         name='courrier-affecter-membre'),
    path('courriers/<int:pk>/traiter-courrier/', 
         CourrierViewSet.as_view({'post': 'traiter_courrier'}), 
         name='courrier-traiter-courrier'),
    
    # Pour les agents/collaborateurs
    path('courriers/mes-courriers-a-traiter/', 
         CourrierViewSet.as_view({'get': 'mes_courriers_a_traiter'}), 
         name='mes-courriers-a-traiter'),

    path('courriers/<int:pk>/destinataires-disponibles/', 
     CourrierViewSet.as_view({'get': 'destinataires_disponibles'}), 
     name='courrier-destinataires-disponibles'),
    path('courriers/<int:pk>/envoyer-a/', 
        CourrierViewSet.as_view({'post': 'envoyer_a'}), 
        name='courrier-envoyer-a'),

    
     # Courriers internes
    path('courriers/<int:pk>/transmettre-interne/', 
         CourrierViewSet.as_view({'post': 'transmettre_interne'}), 
         name='courrier-transmettre-interne'),
    path('courriers/<int:pk>/viser-courrier/', 
         CourrierViewSet.as_view({'post': 'viser_courrier'}), 
         name='courrier-viser-courrier'),
    path('courriers/<int:pk>/valider-interne/', 
         CourrierViewSet.as_view({'post': 'valider_interne'}), 
         name='courrier-valider-interne'),
    path('courriers/<int:pk>/services-destinataires/', 
         CourrierViewSet.as_view({'get': 'services_destinataires'}), 
         name='courrier-services-destinataires'),
    path('courriers/<int:pk>/membres-service/', 
         CourrierViewSet.as_view({'get': 'membres_service'}), 
         name='courrier-membres-service'),
     
     # path('ocr-gemini/', gemini_ocr, name='courrier-ocr-gemini')

]  
