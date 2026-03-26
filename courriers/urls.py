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
router.register(r"traitement", CourrierTraitementViewSet, basename="traitement")

urlpatterns = [
    path('ocr-gemini/', gemini_ocr, name='courrier-ocr-gemini'),
    path('analyse_ia/', CourrierAnalyzeAIView.as_view(), name='analyse_ia'),

    # ══════════════════════════════════════════════════════════════════
    # RÈGLE CRITIQUE : les routes sans <pk> (actions "list") DOIVENT
    # être déclarées AVANT include(router.urls).
    # Le router DRF génère courriers/<pk>/ et intercepte toute URL
    # de la forme courriers/<slug>/ en essayant de caster en int(pk).
    # ══════════════════════════════════════════════════════════════════

    # ── Actions list (sans pk) — AVANT le router ──────────────────────
    path('courriers/analyze_complete/',
         CourrierViewSet.as_view({'post': 'analyze_complete'}),
         name='analyze-complete'),

    path('courriers/generer-pdf/',
         GenererPDFView.as_view(),
         name='generer-pdf'),

    path('courriers/tableau_bord_assignation/',
         CourrierTraitementViewSet.as_view({'get': 'tableau_bord_assignation'}),
         name='tableau-bord-assignation'),

    # FIX PRINCIPAL — cette route sans pk doit précéder le router
    path('courriers/mes-courriers-a-traiter/',
         CourrierViewSet.as_view({'get': 'mes_courriers_a_traiter'}),
         name='mes-courriers-a-traiter'),

    # ── Router DRF (génère /, /<pk>/, etc.) ───────────────────────────
    path('', include(router.urls)),

    # ── Routes detail (<int:pk>) — APRÈS le router ────────────────────
    path('courriers/<int:pk>/export_pdf/',
         CourrierViewSet.as_view({'get': 'export_pdf'}),
         name='courrier-export-pdf'),

    path('courriers/<int:pk>/download-text/',
         CourrierDownloadTextView.as_view(),
         name='download_text'),

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

    path('courriers/<int:pk>/enregistrer_instruction/',
         CourrierViewSet.as_view({'post': 'enregistrer_instruction'}),
         name='courrier-enregistrer-instruction'),

    path('courriers/<int:pk>/services_consultables/',
         CourrierViewSet.as_view({'get': 'services_consultables'}),
         name='courrier-services-consultables'),

    path('courriers/<int:pk>/consulter_service/',
         CourrierViewSet.as_view({'post': 'consulter_service'}),
         name='courrier-consulter-service'),

    # Actions de traitement
    path('courriers/<int:pk>/prendre-en-charge/',
         CourrierTraitementViewSet.as_view({'post': 'prendre_en_charge'}),
         name='courrier-prendre-en-charge'),

    path('courriers/<int:pk>/rediger-reponse/',
         CourrierViewSet.as_view({'post': 'rediger_reponse'}),
         name='courrier-rediger-reponse'),

    path('courriers/<int:pk>/enregistrer-reponse/',
         CourrierTraitementViewSet.as_view({'post': 'enregistrer_reponse'}),
         name='courrier-enregistrer-reponse'),

    path('courriers/<int:pk>/soumettre-validation/',
         CourrierViewSet.as_view({'post': 'soumettre_validation'}),
         name='courrier-soumettre-validation'),

    path('courriers/<int:pk>/valider/',
         CourrierViewSet.as_view({'post': 'valider'}),
         name='courrier-valider'),

    path('courriers/<int:pk>/signer/',
         CourrierViewSet.as_view({'post': 'signer'}),
         name='courrier-signer'),

    path('courriers/<int:pk>/envoyer/',
         CourrierViewSet.as_view({'post': 'envoyer'}),
         name='courrier-envoyer'),

    path('courriers/<int:pk>/cloturer-directement/',
         CourrierViewSet.as_view({'post': 'cloturer_directement'}),
         name='courrier-cloturer-directement'),


    path('courriers/<int:pk>/archiver/',
         CourrierViewSet.as_view({'post': 'archiver'}),
         name='courrier-archiver'),

    # Membres / affectation
    path('courriers/<int:pk>/membres-service/',
         CourrierViewSet.as_view({'get': 'membres_service'}),
         name='courrier-membres-service'),

    path('courriers/<int:pk>/affecter-membre/',
         CourrierViewSet.as_view({'post': 'affecter_membre'}),
         name='courrier-affecter-membre'),

    path('courriers/<int:pk>/traiter-courrier/',
         CourrierViewSet.as_view({'post': 'traiter_courrier'}),
         name='courrier-traiter-courrier'),

    # Destinataires / transmission
    path('courriers/<int:pk>/destinataires-disponibles/',
         CourrierViewSet.as_view({'get': 'destinataires_disponibles'}),
         name='courrier-destinataires-disponibles'),

    path('courriers/<int:pk>/envoyer-a/',
         CourrierViewSet.as_view({'post': 'envoyer_a'}),
         name='courrier-envoyer-a'),

    path('courriers/<int:pk>/timeline/',
         CourrierViewSet.as_view({'get': 'timeline'}),
         name='courrier-timeline'),

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

    path('courriers/<int:pk>/repondre-courrier/',
         CourrierViewSet.as_view({'post': 'repondre_courrier'}),
         name='courrier-repondre-courrier'),
]