from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Avg
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from dateutil import parser

import io
import tempfile
import uuid
import os
import datetime
import logging
import re
from django.http import FileResponse, Http404
from .permissions import IsChefOfService

from .models import Courrier, Imputation, PieceJointe, ActionHistorique, ModeleCourrier
from .serializers import (
    CourrierListSerializer, CourrierDetailSerializer,
    CourrierCreateSerializer, CourrierUpdateSerializer,
    ImputationSerializer, ActionHistoriqueSerializer,
    PieceJointeSerializer, ModeleCourrierSerializer,
    CourrierStatsSerializer, ImportCourrierSerializer,
    ExportCourrierSerializer
)
from workflow.services.ocr import process_ocr
from workflow.services.accuse_reception import send_accuse_reception_email
from workflow.services.classifier import classifier_courrier
from core.models import Category, Service
from workflow.services.ocr_enhanced import OCRService
from workflow.services.ocr import ocr_processor
import pandas as pd
import json
from datetime import datetime, timedelta
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)


class CourrierViewSet(viewsets.ModelViewSet):
    """
    ViewSet complet pour la gestion des courriers
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['reference', 'objet', 'expediteur_nom', 'contenu_texte']
    ordering_fields = ['created_at', 'date_reception', 'date_echeance', 'priorite']
    ordering = ['-created_at']
    
    filterset_fields = {
        'type': ['exact', 'in'],
        'statut': ['exact', 'in'],
        'priorite': ['exact', 'in'],
        'confidentialite': ['exact', 'in'],
        'canal': ['exact', 'in'],
        'category': ['exact', 'in'],
        'service_impute': ['exact', 'in'],
        'created_by': ['exact'],
        'date_reception': ['gte', 'lte', 'exact'],
        'date_echeance': ['gte', 'lte', 'exact'],
    }
    
    def get_queryset(self):
        queryset = Courrier.objects.all()
        
        # Filtrage par type
        type_courrier = self.request.query_params.get("type")
        if type_courrier:
            queryset = queryset.filter(type=type_courrier)
        
        # Filtrage selon le rôle de l'utilisateur
        user = self.request.user
        
        if user.is_superuser or user.role == 'admin':
            # Admin voit tout
            pass
        elif user.role == 'direction':
            # Direction voit les courriers non confidentiels
            queryset = queryset.filter(confidentialite__in=['normale', 'restreinte'])
        elif user.role == 'chef':
            # Chef voit les courriers de son service
            if user.service:
                queryset = queryset.filter(
                    Q(service_impute=user.service) |
                    Q(service_actuel=user.service)
                )
        elif user.role == 'agent_service':
            # ✅ AGENT DE SERVICE : voit UNIQUEMENT les courriers qui lui sont assignés
            if user.service:
                queryset = queryset.filter(
                    Q(responsable_actuel=user)  # Courriers assignés spécifiquement à cet agent
                ).filter(
                    Q(service_actuel=user.service)  # Sécurité : de son service
                )
            else:
                # Si pas de service, ne voit rien
                queryset = queryset.none()
        elif user.role == 'collaborateur':
            # Collaborateur voit les courriers de son service
            if user.service:
                queryset = queryset.filter(service_actuel=user.service)
        
        if self.request.query_params.get("en_retard") == "true":
            queryset = queryset.filter(
                date_echeance__lt=timezone.now().date(),
                statut__in=['recu', 'impute', 'traitement']
            )
        return queryset
      
    def get_serializer_class(self):
        if self.action == 'list':
            return CourrierListSerializer
        elif self.action in ['retrieve', 'create', 'update', 'partial_update']:
            return CourrierDetailSerializer
        return CourrierDetailSerializer
    
    def get_permissions(self):
        if self.request.method == 'OPTIONS':
            return [AllowAny()]
        return super().get_permissions()
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Création d'un courrier avec gestion des pièces jointes"""
        serializer = CourrierCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        logger.info(f"Données reçues pour creation: {request.data}")
        
        if not serializer.is_valid():
            logger.error(f"Erreurs de validation: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            type_courrier = serializer.validated_data.get('type', 'entrant')
            reference = self._generate_reference(type_courrier)
            
            courrier_data = serializer.validated_data.copy()
            courrier_data.pop('pieces_jointes', [])
            ocr_enabled = courrier_data.pop('ocr', True)
            classifier_enabled = courrier_data.pop('classifier', False)
            creer_workflow = courrier_data.pop('creer_workflow', True)
            
            courrier = Courrier.objects.create(
                reference=reference,
                created_by=request.user,
                **courrier_data
            )
            
            texte_ocr_global = self._process_pieces_jointes(
                request.FILES.getlist('pieces_jointes', []),
                courrier,
                request.user,
                ocr_enabled
            )
            
            if texte_ocr_global:
                courrier.contenu_texte = texte_ocr_global
                courrier.save(update_fields=['contenu_texte'])
            
            if classifier_enabled:
                self._process_classification_ia(courrier, request.user)
            
            if creer_workflow:
                self._creer_workflow_automatique(courrier, request.user)
            
            ActionHistorique.objects.create(
                courrier=courrier,
                user=request.user,
                action="CREATION",
                commentaire=f"Courrier {type_courrier} créé"
            )
            
            return Response(
                CourrierDetailSerializer(courrier, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Erreur création courrier: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Erreur création: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def imputer(self, request, pk=None):
        """Imputer un courrier à un service"""
        courrier = self.get_object()
        service_id = request.data.get('service_id')
        commentaire = request.data.get('commentaire', '')
        
        if not service_id:
            return Response({"error": "Le service est requis"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = Service.objects.get(id=service_id)
            imputation = Imputation.objects.create(
                courrier=courrier,
                service=service,
                responsable=request.user,
                commentaire=commentaire
            )
            courrier.service_impute = service
            courrier.service_actuel = service
            courrier.responsable_actuel = request.user
            courrier.statut = 'impute'
            courrier.save()
            
            ActionHistorique.objects.create(
                courrier=courrier,
                user=request.user,
                action="IMPUTATION",
                commentaire=f"Imputé au service {service.nom}"
            )
            
            return Response(
                {"message": "Courrier imputé avec succès", "imputation": ImputationSerializer(imputation).data},
                status=status.HTTP_200_OK
            )
        except Service.DoesNotExist:
            return Response({"error": "Service non trouvé"}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def traiter(self, request, pk=None):
        courrier = self.get_object()
        if courrier.statut != 'impute':
            return Response({"error": "Le courrier doit être imputé avant traitement"}, status=status.HTTP_400_BAD_REQUEST)
        courrier.statut = 'traitement'
        courrier.save(update_fields=['statut'])
        ActionHistorique.objects.create(courrier=courrier, user=request.user, action="DEBUT_TRAITEMENT")
        return Response({"message": "Courrier en traitement"}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def repondre(self, request, pk=None):
        courrier = self.get_object()
        reponse_texte = request.data.get('reponse')
        if not reponse_texte:
            return Response({"error": "Le texte de réponse est requis"}, status=status.HTTP_400_BAD_REQUEST)
        courrier.statut = 'repondu'
        courrier.date_cloture = timezone.now().date()
        courrier.save(update_fields=['statut', 'date_cloture'])
        ActionHistorique.objects.create(courrier=courrier, user=request.user, action="REPONSE")
        return Response({"message": "Courrier marqué comme répondu"}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def archiver(self, request, pk=None):
        courrier = self.get_object()
        courrier.archived = True
        courrier.date_archivage = timezone.now().date()
        courrier.save(update_fields=['archived', 'date_archivage'])
        ActionHistorique.objects.create(courrier=courrier, user=request.user, action="ARCHIVAGE")
        return Response({"message": "Courrier archivé"}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def statistiques(self, request):
        queryset = self.get_queryset()
        stats = {
            'total': queryset.count(),
            'entrants': queryset.filter(type='entrant').count(),
            'sortants': queryset.filter(type='sortant').count(),
            'internes': queryset.filter(type='interne').count(),
            'en_cours': queryset.filter(statut__in=['recu', 'impute', 'traitement']).count(),
            'en_retard': queryset.filter(
                date_echeance__lt=timezone.now().date(),
                statut__in=['recu', 'impute', 'traitement']
            ).count(),
            'traites': queryset.filter(statut='repondu').count(),
            'taux_traitement': 0,
            'delai_moyen': 0
        }
        if stats['total'] > 0:
            stats['taux_traitement'] = round((stats['traites'] / stats['total']) * 100, 2)
        courriers_traites = queryset.filter(statut='repondu', date_reception__isnull=False, date_cloture__isnull=False)
        if courriers_traites.exists():
            delais = [(c.date_cloture - c.date_reception).days for c in courriers_traites]
            stats['delai_moyen'] = round(sum(delais) / len(delais), 2)
        serializer = CourrierStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        serializer = ImportCourrierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fichier = serializer.validated_data['fichier']
        type_courrier = serializer.validated_data['type_courrier']
        mapping = serializer.validated_data.get('mapping', {})
        try:
            if fichier.name.endswith('.csv'):
                df = pd.read_csv(fichier)
            elif fichier.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(fichier)
            else:
                return Response({"error": "Format de fichier non supporté"}, status=status.HTTP_400_BAD_REQUEST)
            if mapping:
                df = df.rename(columns=mapping)
            resultats = []
            for _, row in df.iterrows():
                try:
                    courrier = Courrier.objects.create(
                        reference=self._generate_reference(type_courrier),
                        type=type_courrier,
                        objet=row.get('objet', ''),
                        expediteur_nom=row.get('expediteur_nom', ''),
                        expediteur_email=row.get('expediteur_email', ''),
                        date_reception=row.get('date_reception') or timezone.now().date(),
                        created_by=request.user
                    )
                    resultats.append({'reference': courrier.reference, 'status': 'success'})
                except Exception as e:
                    resultats.append({'ligne': _ + 1, 'status': 'error', 'error': str(e)})
            return Response({"message": f"Import terminé", "resultats": resultats})
        except Exception as e:
            return Response({"error": f"Erreur import: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def export(self, request):
        serializer = ExportCourrierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        format = serializer.validated_data['format']
        periode_debut = serializer.validated_data.get('periode_debut')
        periode_fin = serializer.validated_data.get('periode_fin')
        type_courrier = serializer.validated_data['type_courrier']
        colonnes = serializer.validated_data['colonnes']
        queryset = self.get_queryset()
        if periode_debut:
            queryset = queryset.filter(date_reception__gte=periode_debut)
        if periode_fin:
            queryset = queryset.filter(date_reception__lte=periode_fin)
        if type_courrier != 'tous':
            queryset = queryset.filter(type=type_courrier)
        data = []
        for courrier in queryset:
            item = {}
            for colonne in colonnes:
                if hasattr(courrier, colonne):
                    value = getattr(courrier, colonne)
                    if isinstance(value, datetime):
                        value = value.strftime('%Y-%m-%d %H:%M')
                    item[colonne] = value
                elif colonne == 'category_nom' and courrier.category:
                    item[colonne] = courrier.category.name
                elif colonne == 'service_impute_nom' and courrier.service_impute:
                    item[colonne] = courrier.service_impute.nom
            data.append(item)
        if format == 'json':
            return Response(data)
        return Response({"message": "Export non implémenté pour ce format"}, status=status.HTTP_501_NOT_IMPLEMENTED)
    
    def _generate_reference(self, type_courrier):
        prefixes = {'entrant': 'CE', 'sortant': 'CS', 'interne': 'CI'}
        prefix = prefixes.get(type_courrier, 'CR')
        return f"{prefix}/{timezone.now().year}/{uuid.uuid4().hex[:6].upper()}"
    
    def _process_pieces_jointes(self, fichiers, courrier, user, ocr_enabled):
        texte_ocr_global = ""
        for fichier in fichiers:
            try:
                pj = PieceJointe.objects.create(courrier=courrier, fichier=fichier, uploaded_by=user)
                if ocr_enabled:
                    texte = process_ocr(pj.fichier.path)
                    if texte:
                        texte_ocr_global += f"\n--- {fichier.name} ---\n{texte}\n"
            except Exception as e:
                logger.error(f"Erreur pièce jointe {fichier.name}: {str(e)}")
        return texte_ocr_global
    
    def _process_classification_ia(self, courrier, user):
        try:
            result = classifier_courrier(courrier)
            if result and 'category' in result:
                category_name = result['category']
                category = Category.objects.filter(name__icontains=category_name).first()
                if category:
                    courrier.category = category
            if result and 'service_impute' in result:
                service_name = result['service_impute']
                service = Service.objects.filter(nom__icontains=service_name).first()
                if service:
                    courrier.service_impute = service
                    courrier.statut = 'impute'
                    Imputation.objects.create(
                        courrier=courrier,
                        service=service,
                        responsable=user,
                        suggestion_ia=True,
                        score_ia=result.get('confidence', 0.0)
                    )
            courrier.save()
            ActionHistorique.objects.create(
                courrier=courrier,
                user=user,
                action="CLASSIFICATION_IA",
                commentaire=f"Catégorie: {result.get('category', 'N/A')}"
            )
        except Exception as e:
            logger.error(f"Erreur classification IA: {str(e)}")
    
    def _creer_workflow_automatique(self, courrier, user):
        try:
            from workflow.models import Workflow, WorkflowStep
            workflow = Workflow.objects.create(courrier=courrier)
            if courrier.type == 'entrant':
                steps_config = [
                    {'label': 'Réception et enregistrement', 'role': 'agent_courrier'},
                    {'label': 'Analyse préliminaire', 'role': 'chef'},
                    {'label': 'Traitement technique', 'role': 'collaborateur'},
                    {'label': 'Validation finale', 'role': 'direction'}
                ]
            elif courrier.type == 'sortant':
                steps_config = [
                    {'label': 'Rédaction', 'role': 'collaborateur'},
                    {'label': 'Visa chef de service', 'role': 'chef'},
                    {'label': 'Validation juridique', 'role': 'direction'},
                    {'label': 'Signature et envoi', 'role': 'direction'}
                ]
            else:
                steps_config = [
                    {'label': 'Rédaction', 'role': 'collaborateur'},
                    {'label': 'Validation hiérarchique', 'role': 'chef'},
                    {'label': 'Diffusion', 'role': 'agent_courrier'}
                ]
            for i, config in enumerate(steps_config, 1):
                WorkflowStep.objects.create(workflow=workflow, step_number=i, label=config['label'])
            ActionHistorique.objects.create(courrier=courrier, user=user, action="WORKFLOW_CREATE")
        except Exception as e:
            logger.error(f"Erreur création workflow: {str(e)}")
    
    @action(detail=True, methods=['get'])
    def export_pdf(self, request, pk=None):
        courrier = self.get_object()
        buffer = io.BytesIO()
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, 750, f"Courrier: {courrier.reference}")
        p.setFont("Helvetica", 12)
        p.drawString(50, 720, f"Objet: {courrier.objet}")
        p.drawString(50, 700, f"Expéditeur: {courrier.expediteur_nom}")
        p.drawString(50, 680, f"Date réception: {courrier.date_reception}")
        p.drawString(50, 660, f"Statut: {courrier.get_statut_display()}")
        p.showPage()
        p.save()
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf',
                            headers={'Content-Disposition': f'attachment; filename="courrier_{courrier.reference}.pdf"'})

    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def demarrer_analyse(self, request, pk=None):
        """Démarrer l'analyse d'un courrier"""
        courrier = self.get_object()
        
        # Vérifier les permissions
        user = request.user
        if user.role not in ['chef', 'direction', 'admin', 'agent_service']:
            return Response(
                {"error": "Vous n'êtes pas autorisé à analyser ce courrier"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Mettre à jour le statut
        courrier.traitement_statut = 'analyse'
        courrier.date_debut_traitement = timezone.now()
        courrier.agent_traitant = user
        courrier.save()
        
        # Créer une étape de traitement
        from .models import TraitementEtape
        etape = TraitementEtape.objects.create(
            courrier=courrier,
            type_etape='analyse',
            agent=user,
            description="Début de l'analyse du courrier",
            statut='en_cours'
        )
        
        # Journaliser
        ActionHistorique.objects.create(
            courrier=courrier,
            user=user,
            action="DEBUT_ANALYSE",
            commentaire="Début de l'analyse du courrier"
        )
        
        return Response({
            "message": "Analyse démarrée avec succès",
            "etape_id": str(etape.id),
            "courrier": CourrierDetailSerializer(courrier, context={'request': request}).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enregistrer_analyse(self, request, pk=None):
        """Enregistrer les résultats de l'analyse"""
        courrier = self.get_object()
        
        # Récupérer les données
        analyse_notes = request.data.get('analyse_notes', '')
        actions_requises = request.data.get('actions_requises', [])
        documents_necessaires = request.data.get('documents_necessaires', [])
        consultations = request.data.get('consultations', [])
        decision_preliminaire = request.data.get('decision_preliminaire', '')
        prochaine_etape = request.data.get('prochaine_etape', 'instruction')
        
        # Mettre à jour le courrier
        courrier.analyse_notes = analyse_notes
        courrier.actions_requises = actions_requises
        courrier.documents_necessaires = documents_necessaires
        courrier.consultations = consultations
        courrier.decision_preliminaire = decision_preliminaire
        courrier.analyse_date = timezone.now()
        courrier.analyse_par = request.user
        courrier.traitement_statut = prochaine_etape
        courrier.save()
        
        # Terminer l'étape d'analyse
        from .models import TraitementEtape
        etape_en_cours = TraitementEtape.objects.filter(
            courrier=courrier,
            type_etape='analyse',
            statut='en_cours'
        ).first()
        
        if etape_en_cours:
            etape_en_cours.statut = 'termine'
            etape_en_cours.date_fin = timezone.now()
            etape_en_cours.save()
        
        # Créer la prochaine étape
        if prochaine_etape != 'attente':
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape=prochaine_etape,
                description=f"Suite de l'analyse",
                statut='en_attente'
            )
        
        # Journaliser
        ActionHistorique.objects.create(
            courrier=courrier,
            user=request.user,
            action="ANALYSE_TERMINEE",
            commentaire=f"Analyse terminée. Prochaine étape: {prochaine_etape}"
        )
        
        return Response({
            "message": "Analyse enregistrée avec succès",
            "courrier": CourrierDetailSerializer(courrier, context={'request': request}).data
        })

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def services_consultables(self, request, pk=None):
        """Liste des services qui peuvent être consultés"""
        courrier = self.get_object()
        
        services = Service.objects.exclude(id=courrier.service_actuel.id).values(
            'id', 'nom', 'description'
        ).annotate(
            consultations_anterieures=Count(
                'service_consulte',
                filter=Q(service_consulte__courrier=courrier)
            )
        )
        
        return Response(list(services))

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def consulter_service(self, request, pk=None):
        """Demander l'avis d'un autre service"""
        courrier = self.get_object()
        service_id = request.data.get('service_id')
        motif = request.data.get('motif', '')
        urgence = request.data.get('urgence', False)
        
        if not service_id:
            return Response({"error": "Service ID requis"}, status=400)
        
        try:
            service = Service.objects.get(id=service_id)
        except Service.DoesNotExist:
            return Response({"error": "Service non trouvé"}, status=404)
        
        # Créer la consultation
        consultation = {
            'id': str(uuid.uuid4()),
            'service_id': service.id,
            'service_nom': service.nom,
            'motif': motif,
            'date_demande': timezone.now().isoformat(),
            'demandeur_id': request.user.id,
            'demandeur_nom': request.user.get_full_name(),
            'statut': 'en_attente',
            'urgence': urgence,
            'reponse': None,
            'date_reponse': None
        }
        
        # Ajouter aux consultations existantes
        consultations = courrier.consultations or []
        consultations.append(consultation)
        courrier.consultations = consultations
        courrier.save()
        
        return Response({
            "message": f"Demande d'avis envoyée au service {service.nom}",
            "consultation": consultation
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enregistrer_instruction(self, request, pk=None):
        """
        Enregistrer les données de l'instruction
        """
        courrier = self.get_object()
        
        courrier.actions_requises = request.data.get('actions_requises', [])
        courrier.documents_necessaires = request.data.get('documents_necessaires', [])
        courrier.notes_instruction = request.data.get('notes_instruction', '')
        courrier.consultations = request.data.get('consultations', [])
        
        if request.data.get('statut_instruction') == 'terminee':
            courrier.traitement_statut = 'redaction'
        
        courrier.save()
        
        ActionHistorique.objects.create(
            courrier=courrier,
            user=request.user,
            action="INSTRUCTION",
            commentaire="Instruction mise à jour"
        )
        
        return Response({
            "message": "Instruction enregistrée",
            "courrier": CourrierDetailSerializer(courrier).data
    })

class ImputationViewSet(viewsets.ModelViewSet):
    queryset = Imputation.objects.all().order_by('-date_imputation')
    serializer_class = ImputationSerializer
    permission_classes = [IsAuthenticated, IsChefOfService]


class PieceJointeViewSet(viewsets.ModelViewSet):
    queryset = PieceJointe.objects.all().order_by('-uploaded_at')
    serializer_class = PieceJointeSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        courrier_id = self.request.query_params.get('courrier_id')
        if courrier_id:
            queryset = queryset.filter(courrier_id=courrier_id)
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class ModeleCourrierViewSet(viewsets.ModelViewSet):
    queryset = ModeleCourrier.objects.filter(actif=True).order_by('nom')
    serializer_class = ModeleCourrierSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nom', 'contenu']
    
    @action(detail=True, methods=['post'])
    def utiliser(self, request, pk=None):
        modele = self.get_object()
        variables = modele.variables
        valeurs = request.data.get('valeurs', {})
        contenu = modele.contenu
        for var in variables:
            if var in valeurs:
                contenu = contenu.replace(f'{{{{ {var} }}}}', valeurs[var])
        return Response({
            "contenu": contenu,
            "entete": modele.entete,
            "pied_page": modele.pied_page,
            "modele": modele.nom
        })


class ImputationDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsChefOfService]
    
    def list(self, request):
        try:
            courriers_en_attente = Courrier.objects.filter(
                Q(statut='recu') | Q(service_impute__isnull=True),
                archived=False
            ).select_related('category', 'service_impute').order_by('-date_reception')
            
            type_courrier = request.query_params.get('type')
            if type_courrier:
                courriers_en_attente = courriers_en_attente.filter(type=type_courrier)
            search = request.query_params.get('search')
            if search:
                courriers_en_attente = courriers_en_attente.filter(
                    Q(objet__icontains=search) |
                    Q(reference__icontains=search) |
                    Q(expediteur_nom__icontains=search)
                )
            data = []
            for courrier in courriers_en_attente:
                suggestions_ia = []
                if courrier.meta_analyse and 'classification' in courrier.meta_analyse:
                    suggestions_ia = [{
                        'service_id': courrier.meta_analyse['classification'].get('service_id'),
                        'service_nom': courrier.meta_analyse['classification'].get('service_suggere'),
                        'confiance': courrier.meta_analyse['classification'].get('confiance_service', 0)
                    }]
                data.append({
                    'id': courrier.id,
                    'reference': courrier.reference,
                    'type': courrier.type,
                    'type_display': courrier.get_type_display(),
                    'objet': courrier.objet,
                    'expediteur_nom': courrier.expediteur_nom,
                    'expediteur_email': courrier.expediteur_email,
                    'date_reception': courrier.date_reception,
                    'category_id': courrier.category.id if courrier.category else None,
                    'category_nom': courrier.category.name if courrier.category else None,
                    'service_impute_id': courrier.service_impute.id if courrier.service_impute else None,
                    'service_impute_nom': courrier.service_impute.nom if courrier.service_impute else None,
                    'statut': courrier.statut,
                    'confidentialite': courrier.confidentialite,
                    'priorite': courrier.priorite,
                    'meta_analyse': courrier.meta_analyse,
                    'suggestions_ia': suggestions_ia,
                    'has_ia_suggestion': bool(suggestions_ia)
                })
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Erreur récupération dashboard imputation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def statistiques(self, request):
        try:
            stats = {
                'total_en_attente': Courrier.objects.filter(
                    Q(statut='recu') | Q(service_impute__isnull=True), archived=False).count(),
                'entrants_en_attente': Courrier.objects.filter(
                    Q(statut='recu') | Q(service_impute__isnull=True), type='entrant', archived=False).count(),
                'sortants_en_attente': Courrier.objects.filter(
                    Q(statut='recu') | Q(service_impute__isnull=True), type='sortant', archived=False).count(),
                'internes_en_attente': Courrier.objects.filter(
                    Q(statut='recu') | Q(service_impute__isnull=True), type='interne', archived=False).count(),
                'avec_suggestion_ia': Courrier.objects.filter(meta_analyse__isnull=False, archived=False).count(),
            }
            return Response(stats, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Erreur statistiques imputation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CourrierAnalyzeAIView(APIView):
    """Vue pour l'analyse IA avec création de fichier texte"""
    def post(self, request):
        try:
            file_obj = request.FILES.get('pieces_jointes')
            if not file_obj:
                return Response({"error": "Aucun fichier fourni"}, status=status.HTTP_400_BAD_REQUEST)
            temp_path = self._save_temp_file(file_obj)
            try:
                from workflow.services.ocr import process_ocr
                extracted_text = process_ocr(temp_path, None)
                if not extracted_text or not extracted_text.strip():
                    return Response({"error": "Impossible d'extraire le texte du document"}, status=status.HTTP_400_BAD_REQUEST)
                from workflow.services.file_storage import text_storage
                metadata = {
                    "source_file": file_obj.name,
                    "file_size": file_obj.size,
                    "ocr_date": datetime.now().isoformat(),
                    "ocr_engine": "Tesseract",
                    "language": "fra+eng"
                }
                if request.data:
                    for field in ['objet', 'expediteur_nom', 'expediteur_email', 'date_reception']:
                        if field in request.data:
                            metadata[field] = request.data[field]
                file_info = text_storage.save_extracted_text(text=extracted_text, metadata=metadata)
                from workflow.services.extracteur_ocr import extracteur_ocr
                structured_info = extracteur_ocr.extraire_toutes_informations(extracted_text)
                classification = self._classify_with_ai(extracted_text)
                priorite = self._determine_priority(extracted_text)
                response_data = {
                    "texte_ocr": extracted_text,
                    "classification": classification,
                    "priorite": priorite,
                    "analyse": {
                        "resume": self._generate_summary(extracted_text),
                        "mots_cles": structured_info.get("mots_cles", [])
                    },
                    "expediteur": structured_info.get("expediteur", {}),
                    "structured_info": structured_info,
                    "fichiers_traites": [file_obj.name],
                    "ia_disponible": True,
                    "objet": structured_info.get("objet", ""),
                    "confidentialite_suggestion": "normale",
                    "text_file_created": file_info is not None,
                    "text_file_info": file_info
                }
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.info(f"Analyse IA terminée - Fichier texte créé: {file_info}")
                return Response(response_data, status=status.HTTP_200_OK)
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.error(f"Erreur traitement: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Erreur analyse IA: {str(e)}")
            return Response({"error": f"Erreur lors de l'analyse: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _save_temp_file(self, file_obj):
        import tempfile
        temp_dir = tempfile.gettempdir()
        safe_name = file_obj.name.replace(' ', '_').replace('/', '_')
        temp_path = os.path.join(temp_dir, safe_name)
        with open(temp_path, 'wb') as f:
            for chunk in file_obj.chunks():
                f.write(chunk)
        return temp_path
    
    def _classify_with_ai(self, extracted_text):
        return {
            "categorie_suggeree": "ADMINISTRATIF",
            "service_suggere": "Secrétariat Général",
            "confiance_categorie": 0.3,
            "confiance_service": 0.3
        }
    
    def _determine_priority(self, extracted_text):
        return {"niveau": "basse", "confiance": 0.5, "raison": "Document non prioritaire"}
    
    def _generate_summary(self, extracted_text):
        if len(extracted_text) > 200:
            return extracted_text[:200] + "..."
        return extracted_text


class CourrierDownloadTextView(APIView):
    def get(self, request, pk):
        try:
            from workflow.services.file_storage import text_storage
            courrier = Courrier.objects.get(pk=pk)
            file_path = text_storage.get_courrier_text_file(courrier.id)
            if not file_path or not file_path.exists():
                raise Http404("Aucun fichier texte disponible pour ce courrier")
            response = FileResponse(open(file_path, 'rb'), content_type='text/plain; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{file_path.name}"'
            return response
        except Courrier.DoesNotExist:
            return Response({"error": "Courrier non trouvé"}, status=status.HTTP_404_NOT_FOUND)
        except Http404:
            return Response({"error": "Fichier texte non trouvé"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erreur téléchargement texte: {str(e)}")
            return Response({"error": "Erreur lors du téléchargement"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AgentServiceDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.request.user.role != 'agent_service':
            return [permissions.IsAdminUser()]
        return super().get_permissions()
    
    def list(self, request):
        try:
            user = request.user
            if user.role != 'agent_service':
                return Response({"error": "Réservé aux agents de service"}, status=status.HTTP_403_FORBIDDEN)
            service = user.service
            if not service:
                return Response({"error": "Vous n'êtes affecté à aucun service"}, status=status.HTTP_400_BAD_REQUEST)
            mes_courriers = Courrier.objects.filter(responsable_actuel=user, archived=False).order_by('-date_reception')
            courriers_service = Courrier.objects.filter(
                service_actuel=service, responsable_actuel__isnull=True, archived=False,
                statut__in=['impute', 'traitement']
            ).order_by('-date_reception')
            stats = {
                'mes_courriers_total': mes_courriers.count(),
                'mes_courriers_en_retard': mes_courriers.filter(
                    date_echeance__lt=timezone.now().date(), statut__in=['impute', 'traitement']
                ).count(),
                'courriers_service_disponibles': courriers_service.count(),
                'service_nom': service.nom,
                'service_chef': service.chef.get_full_name() if service.chef else None
            }
            mes_courriers_data = CourrierListSerializer(mes_courriers[:10], many=True, context={'request': request}).data
            courriers_service_data = CourrierListSerializer(courriers_service[:10], many=True, context={'request': request}).data
            return Response({'stats': stats, 'mes_courriers': mes_courriers_data, 'courriers_disponibles': courriers_service_data})
        except Exception as e:
            logger.error(f"Erreur dashboard agent: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def prendre_courrier(self, request):
        try:
            courrier_id = request.data.get('courrier_id')
            if not courrier_id:
                return Response({"error": "ID du courrier requis"}, status=status.HTTP_400_BAD_REQUEST)
            if request.user.role != 'agent_service':
                return Response({"error": "Réservé aux agents de service"}, status=status.HTTP_403_FORBIDDEN)
            courrier = Courrier.objects.get(pk=courrier_id)
            user = request.user
            if courrier.service_actuel != user.service:
                return Response({"error": "Ce courrier n'appartient pas à votre service"}, status=status.HTTP_403_FORBIDDEN)
            if courrier.responsable_actuel and courrier.responsable_actuel != user:
                return Response({"error": "Ce courrier est déjà pris en charge par un autre agent"}, status=status.HTTP_400_BAD_REQUEST)
            courrier.responsable_actuel = user
            courrier.statut = 'traitement'
            courrier.save()
            ActionHistorique.objects.create(courrier=courrier, user=user, action="PRISE_EN_CHARGE")
            return Response({"message": "Courrier pris en charge avec succès"})
        except Courrier.DoesNotExist:
            return Response({"error": "Courrier non trouvé"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erreur prise en charge: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Les classes suivantes sont déjà présentes dans votre code, je les conserve mais elles peuvent être incomplètes.
# Vous devrez ajouter les modèles manquants si nécessaire (ValidationCourrier, InstructionCourrier, etc.)


class CourrierTraitementViewSet(viewsets.ViewSet):
    """
    ViewSet pour la gestion du traitement des courriers
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Retourne les courriers accessibles pour le traitement"""
        user = self.request.user
        
        # Si admin ou direction, voir tout
        if user.role in ['admin', 'direction']:
            return Courrier.objects.filter(
                Q(statut='traitement') | Q(traitement_statut__isnull=False),
                archived=False
            )
        
        # Chef de service
        elif user.role == 'chef' and user.service:
            return Courrier.objects.filter(
                Q(service_actuel=user.service) | Q(service_impute=user.service),
                Q(statut='traitement') | Q(traitement_statut__isnull=False),
                archived=False
            )
        
        # Agent de service
        elif user.role == 'agent_service' and user.service:
            return Courrier.objects.filter(
                Q(responsable_actuel=user) | 
                Q(service_actuel=user.service, responsable_actuel__isnull=True),
                Q(statut='traitement') | Q(traitement_statut__isnull=False),
                archived=False
            )
        
        # Collaborateur
        elif user.role == 'collaborateur':
            return Courrier.objects.filter(
                Q(responsable_actuel=user) &
                (
                    Q(statut='traitement') |
                    Q(traitement_statut__isnull=False)
                ) &
                Q(archived=False)
            )

    
    def list(self, request):
        """Liste des courriers à traiter pour l'utilisateur"""
        try:
            queryset = self.get_queryset()
            
            # Filtres supplémentaires
            statut_traitement = request.query_params.get('statut_traitement')
            if statut_traitement:
                queryset = queryset.filter(traitement_statut=statut_traitement)
            
            priorite = request.query_params.get('priorite')
            if priorite:
                queryset = queryset.filter(priorite=priorite)
            
            type_courrier = request.query_params.get('type')
            if type_courrier:
                queryset = queryset.filter(type=type_courrier)
            
            # Pagination
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            start = (page - 1) * page_size
            end = start + page_size
            
            courriers = queryset.order_by('-date_reception', 'priorite')[start:end]
            
            serializer = CourrierDetailSerializer(
                courriers, many=True, context={'request': request}
            )
            
            return Response({
                'results': serializer.data,
                'count': queryset.count(),
                'page': page,
                'page_size': page_size,
                'total_pages': (queryset.count() + page_size - 1) // page_size
            })
            
        except Exception as e:
            logger.error(f"Erreur liste traitement: {str(e)}")
            return Response(
                {"error": "Erreur lors de la récupération des courriers"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques pour le dashboard de traitement"""
        try:
            user = request.user
            queryset = self.get_queryset()
            
            stats = {
                'total': queryset.count(),
                'en_cours': queryset.filter(traitement_statut='analyse').count(),
                'en_validation': queryset.filter(traitement_statut='validation').count(),
                'a_envoyer': queryset.filter(traitement_statut='envoi').count(),
                'en_retard': queryset.filter(
                    date_echeance__lt=timezone.now().date(),
                    traitement_statut__in=['analyse', 'instruction', 'validation']
                ).count(),
                'mes_courriers': queryset.filter(responsable_actuel=user).count(),
            }
            
            return Response(stats)
            
        except Exception as e:
            logger.error(f"Erreur stats traitement: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='prendre-en-charge')
    def prendre_en_charge(self, request, pk=None):
        """Prendre en charge un courrier pour traitement"""
        try:
            with transaction.atomic():
                courrier = Courrier.objects.get(pk=pk)
                
                # Vérifier les permissions
                user = request.user
                
                # Vérifier si déjà pris en charge
                if courrier.responsable_actuel and courrier.responsable_actuel != user:
                    return Response(
                        {"error": "Ce courrier est déjà pris en charge par un autre agent"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Vérifier que l'utilisateur peut prendre en charge
                if user.role == 'agent_service' and user.service != courrier.service_actuel:
                    return Response(
                        {"error": "Vous ne pouvez pas prendre en charge un courrier d'un autre service"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Mettre à jour le courrier
                courrier.responsable_actuel = user
                courrier.agent_traitant = user
                courrier.traitement_statut = TraitementStatus.ANALYSE
                courrier.date_debut_traitement = timezone.now()
                courrier.statut = 'traitement'
                
                # Définir le délai de traitement
                delai_jours = request.data.get('delai_jours', 5)
                courrier.delai_traitement_jours = delai_jours
                
                courrier.save()
                
                # Créer une étape de traitement
                TraitementEtape.objects.create(
                    courrier=courrier,
                    type_etape='prise_en_charge',
                    agent=user,
                    description=f"Prise en charge par {user.get_full_name()}",
                    commentaire=request.data.get('commentaire', ''),
                    statut='termine',
                    date_fin=timezone.now()
                )
                
                # Journaliser
                from .models import ActionHistorique
                ActionHistorique.objects.create(
                    courrier=courrier,
                    user=user,
                    action="PRISE_EN_CHARGE_TRAITEMENT",
                    commentaire=f"Courrier pris en charge pour traitement"
                )
                
                serializer = CourrierDetailSerializer(courrier, context={'request': request})
                return Response(serializer.data)
                
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur prise en charge: {str(e)}")
            return Response(
                {"error": "Erreur lors de la prise en charge"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def ajouter_instruction(self, request, pk=None):
        """Ajouter une instruction pour le traitement"""
        try:
            courrier = Courrier.objects.get(pk=pk)
            
            # Vérifier que l'utilisateur peut ajouter des instructions
            user = request.user
            if user.role not in ['admin', 'direction', 'chef'] and courrier.agent_traitant != user:
                return Response(
                    {"error": "Vous n'avez pas la permission d'ajouter des instructions"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            instruction_data = request.data
            
            # Créer l'instruction
            instruction = InstructionCourrier.objects.create(
                courrier=courrier,
                type_instruction=instruction_data.get('type_instruction', 'analyse'),
                instruction=instruction_data.get('instruction'),
                agent_assignee_id=instruction_data.get('agent_assignee_id'),
                date_echeance=instruction_data.get('date_echeance'),
                statut='en_attente'
            )
            
            # Mettre à jour le statut du traitement
            if courrier.traitement_statut == TraitementStatus.ANALYSE:
                courrier.traitement_statut = TraitementStatus.INSTRUCTION
                courrier.save(update_fields=['traitement_statut'])
            
            # Créer une étape de traitement
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='instruction',
                agent=user,
                description=f"Instruction ajoutée: {instruction_data.get('instruction', '')[:100]}...",
                statut='termine',
                date_fin=timezone.now()
            )
            
            return Response({
                "message": "Instruction ajoutée avec succès",
                "instruction_id": str(instruction.id)
            })
            
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur ajout instruction: {str(e)}")
            return Response(
                {"error": "Erreur lors de l'ajout de l'instruction"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def rediger_reponse(self, request, pk=None):
        """Rédiger une réponse au courrier"""
        try:
            with transaction.atomic():
                courrier = Courrier.objects.get(pk=pk)
                user = request.user
                
                # Vérifier les permissions
                if courrier.agent_traitant != user and user.role not in ['admin', 'direction', 'chef']:
                    return Response(
                        {"error": "Vous n'avez pas la permission de rédiger une réponse"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Validation des données
                required_fields = ['type_reponse', 'objet', 'contenu', 'destinataires']
                for field in required_fields:
                    if field not in request.data:
                        return Response(
                            {"error": f"Le champ {field} est requis"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                # Créer la réponse
                reponse = CourrierReponse.objects.create(
                    courrier_origine=courrier,
                    type_reponse=request.data['type_reponse'],
                    objet=request.data['objet'],
                    contenu=request.data['contenu'],
                    destinataires=request.data['destinataires'],
                    copies=request.data.get('copies', []),
                    canal_envoi=request.data.get('canal_envoi', 'email'),
                    redacteur=user,
                    statut='brouillon',
                    pieces_jointes_reponse=request.data.get('pieces_jointes', [])
                )
                
                # Si un modèle est spécifié
                if request.data.get('modele_id'):
                    from .models import ModeleCourrier
                    try:
                        modele = ModeleCourrier.objects.get(pk=request.data['modele_id'])
                        reponse.modele_utilise = modele
                        reponse.save()
                    except ModeleCourrier.DoesNotExist:
                        pass
                
                # Mettre à jour le statut du traitement
                courrier.traitement_statut = TraitementStatus.REDACTION
                courrier.reponse_associee = reponse
                courrier.save()
                
                # Créer une étape de traitement
                TraitementEtape.objects.create(
                    courrier=courrier,
                    type_etape='redaction',
                    agent=user,
                    description="Rédaction de la réponse",
                    commentaire=f"Type: {request.data['type_reponse']}",
                    statut='termine',
                    date_fin=timezone.now()
                )
                
                return Response({
                    "message": "Réponse rédigée avec succès",
                    "reponse_id": str(reponse.id),
                    "reponse_reference": reponse.reference
                })
                
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur rédaction réponse: {str(e)}")
            return Response(
                {"error": "Erreur lors de la rédaction de la réponse"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def soumettre_validation(self, request, pk=None):
        """Soumettre pour validation"""
        try:
            with transaction.atomic():
                courrier = Courrier.objects.get(pk=pk)
                user = request.user
                
                # Vérifier les permissions
                if courrier.agent_traitant != user and user.role not in ['admin', 'direction', 'chef']:
                    return Response(
                        {"error": "Vous n'avez pas la permission de soumettre pour validation"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                validation_data = request.data
                reponse_id = validation_data.get('reponse_id')
                validateurs_ids = validation_data.get('validateurs', [])
                niveau_validation = validation_data.get('niveau_validation', 1)
                
                # Récupérer la réponse si spécifiée
                reponse = None
                if reponse_id:
                    try:
                        reponse = CourrierReponse.objects.get(id=reponse_id, courrier_origine=courrier)
                        reponse.statut = 'a_valider'
                        reponse.save(update_fields=['statut'])
                    except CourrierReponse.DoesNotExist:
                        return Response(
                            {"error": "Réponse non trouvée"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                
                # Créer les validations
                validations_created = []
                for validateur_id in validateurs_ids:
                    validation = ValidationCourrier.objects.create(
                        courrier=courrier,
                        type_validation=validation_data.get('type_validation', 'hierarchique'),
                        validateur_id=validateur_id,
                        ordre=niveau_validation,
                        statut='en_attente'
                    )
                    validations_created.append(validation)
                
                # Mettre à jour le courrier
                courrier.traitement_statut = TraitementStatus.VALIDATION
                courrier.besoin_validation = True
                courrier.niveau_validation_requis = niveau_validation
                if reponse:
                    courrier.reponse_associee = reponse
                courrier.save()
                
                # Créer une étape de traitement
                TraitementEtape.objects.create(
                    courrier=courrier,
                    type_etape='validation',
                    agent=user,
                    description="Soumis pour validation",
                    commentaire=f"Niveau de validation: {niveau_validation}",
                    validation_requise=True,
                    statut='en_attente'
                )
                
                return Response({
                    "message": "Courrier soumis pour validation",
                    "validations_count": len(validations_created)
                })
                
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur soumission validation: {str(e)}")
            return Response(
                {"error": "Erreur lors de la soumission pour validation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        """Valider une étape de validation"""
        try:
            courrier = Courrier.objects.get(pk=pk)
            validation_id = request.data.get('validation_id')
            
            if not validation_id:
                return Response(
                    {"error": "ID de validation requis"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Récupérer la validation
            try:
                validation = ValidationCourrier.objects.get(id=validation_id, courrier=courrier)
            except ValidationCourrier.DoesNotExist:
                return Response(
                    {"error": "Validation non trouvée"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Vérifier que l'utilisateur est le validateur
            if validation.validateur != request.user:
                return Response(
                    {"error": "Vous n'êtes pas autorisé à valider cette étape"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            action = request.data.get('action', 'valider')
            
            # Mettre à jour la validation
            validation.statut = {
                'valider': 'valide',
                'rejeter': 'rejete',
                'modifier': 'modification'
            }.get(action, 'valide')
            
            validation.commentaire = request.data.get('commentaire', '')
            validation.date_action = timezone.now()
            validation.save()
            
            # Mettre à jour le niveau de validation atteint
            if action == 'valider':
                courrier.niveau_validation_atteint = max(
                    courrier.niveau_validation_atteint,
                    validation.ordre
                )
                
                # Si tous les niveaux sont validés
                if courrier.niveau_validation_atteint >= courrier.niveau_validation_requis:
                    courrier.traitement_statut = TraitementStatus.SIGNATURE
                    
                    # Mettre à jour la réponse si elle existe
                    if courrier.reponse_associee:
                        courrier.reponse_associee.statut = 'a_signature'
                        courrier.reponse_associee.save()
                
                courrier.save()
            
            elif action == 'rejeter':
                # Revenir à l'étape de rédaction
                courrier.traitement_statut = TraitementStatus.REDACTION
                if courrier.reponse_associee:
                    courrier.reponse_associee.statut = 'a_corriger'
                    courrier.reponse_associee.save()
                courrier.save()
            
            # Créer une étape de traitement
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='validation',
                agent=request.user,
                description=f"Validation {action}ée",
                commentaire=request.data.get('commentaire', ''),
                statut='termine',
                date_fin=timezone.now()
            )
            
            return Response({
                "message": f"Validation {action}ée avec succès"
            })
            
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur validation: {str(e)}")
            return Response(
                {"error": "Erreur lors de la validation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def signer(self, request, pk=None):
        """Signer électroniquement"""
        try:
            courrier = Courrier.objects.get(pk=pk)
            user = request.user
            
            # Vérifier les permissions (seuls certains rôles peuvent signer)
            if user.role not in ['admin', 'direction', 'chef']:
                return Response(
                    {"error": "Vous n'avez pas la permission de signer"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            signature_data = request.data.get('signature_data')
            
            # Créer une validation de type signature
            validation = ValidationCourrier.objects.create(
                courrier=courrier,
                type_validation='signature',
                validateur=user,
                statut='signe',
                date_action=timezone.now(),
                signature_data=signature_data,
                signature_image=request.data.get('signature_image'),
                certificat_info=request.data.get('certificat_info'),
                commentaire=request.data.get('commentaire', 'Signature électronique')
            )
            
            # Mettre à jour le statut
            courrier.traitement_statut = TraitementStatus.ENVOI
            
            # Mettre à jour la réponse si elle existe
            if courrier.reponse_associee:
                courrier.reponse_associee.statut = 'a_envoyer'
                courrier.reponse_associee.signataire = user
                courrier.reponse_associee.date_signature = timezone.now()
                courrier.reponse_associee.save()
            
            courrier.save()
            
            # Créer une étape de traitement
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='signature',
                agent=user,
                description="Signature électronique",
                statut='termine',
                date_fin=timezone.now()
            )
            
            return Response({
                "message": "Signature enregistrée avec succès"
            })
            
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur signature: {str(e)}")
            return Response(
                {"error": "Erreur lors de la signature"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def envoyer(self, request, pk=None):
        """Envoyer la réponse"""
        try:
            with transaction.atomic():
                courrier = Courrier.objects.get(pk=pk)
                user = request.user
                
                # Vérifier les permissions
                if user.role not in ['admin', 'direction', 'chef']:
                    return Response(
                        {"error": "Vous n'avez pas la permission d'envoyer la réponse"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Vérifier qu'il y a une réponse à envoyer
                if not courrier.reponse_associee:
                    return Response(
                        {"error": "Aucune réponse à envoyer"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                reponse = courrier.reponse_associee
                
                # Mettre à jour la réponse
                reponse.date_envoi = timezone.now()
                reponse.statut = 'envoye'
                reponse.confirmation_reception = False
                reponse.save()
                
                # Mettre à jour le courrier
                courrier.traitement_statut = TraitementStatus.CLOTURE
                courrier.statut = 'repondu'
                courrier.date_fin_traitement = timezone.now()
                courrier.date_cloture = timezone.now().date()
                courrier.save()
                
                # Créer une étape de traitement
                TraitementEtape.objects.create(
                    courrier=courrier,
                    type_etape='envoi',
                    agent=user,
                    description=f"Réponse envoyée par {reponse.canal_envoi}",
                    commentaire=f"Destinataires: {len(reponse.destinataires)}",
                    statut='termine',
                    date_fin=timezone.now()
                )
                
                # Journaliser
                from .models import ActionHistorique
                ActionHistorique.objects.create(
                    courrier=courrier,
                    user=user,
                    action="REPONSE_ENVOYEE",
                    commentaire=f"Réponse envoyée par {reponse.canal_envoi}"
                )
                
                return Response({
                    "message": "Réponse envoyée avec succès"
                })
                
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur envoi: {str(e)}")
            return Response(
                {"error": "Erreur lors de l'envoi de la réponse"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        """Récupérer la timeline du traitement"""
        try:
            courrier = Courrier.objects.get(pk=pk)
            
            # Récupérer toutes les données de timeline
            timeline_data = []
            
            # Étape de réception
            if courrier.date_reception:
                timeline_data.append({
                    'type': 'reception',
                    'date': courrier.date_reception,
                    'titre': 'Réception du courrier',
                    'description': f'Courrier reçu de {courrier.expediteur_nom}',
                    'auteur': courrier.created_by.get_full_name() if courrier.created_by else 'Système'
                })
            
            # Étape d'imputation
            imputations = courrier.imputations.all()
            for imputation in imputations:
                timeline_data.append({
                    'type': 'imputation',
                    'date': imputation.date_imputation,
                    'titre': 'Imputation',
                    'description': f'Imputé au service {imputation.service.nom if imputation.service else "N/A"}',
                    'auteur': imputation.responsable.get_full_name() if imputation.responsable else 'Système'
                })
            
            # Étapes de traitement
            etapes = courrier.traitement_etapes.all()
            for etape in etapes:
                timeline_data.append({
                    'type': 'traitement',
                    'date': etape.date_debut,
                    'titre': etape.get_type_etape_display(),
                    'description': etape.description,
                    'auteur': etape.agent.get_full_name() if etape.agent else 'Système',
                    'statut': etape.get_statut_display()
                })
            
            # Validations
            validations = courrier.validations.all()
            for validation in validations:
                timeline_data.append({
                    'type': 'validation',
                    'date': validation.date_action or validation.date_demande,
                    'titre': f"Validation {validation.get_type_validation_display()}",
                    'description': validation.commentaire or f"Statut: {validation.get_statut_display()}",
                    'auteur': validation.validateur.get_full_name() if validation.validateur else 'En attente',
                    'statut': validation.get_statut_display()
                })
            
            # Instructions
            instructions = courrier.instructions.all()
            for instruction in instructions:
                timeline_data.append({
                    'type': 'instruction',
                    'date': instruction.date_assignation,
                    'titre': f"Instruction: {instruction.get_type_instruction_display()}",
                    'description': instruction.instruction[:100] + '...' if len(instruction.instruction) > 100 else instruction.instruction,
                    'auteur': 'Système',
                    'statut': instruction.get_statut_display()
                })
            
            # Réponses
            reponses = courrier.reponses.all()
            for reponse in reponses:
                timeline_data.append({
                    'type': 'reponse',
                    'date': reponse.date_redaction,
                    'titre': f"Réponse: {reponse.get_type_reponse_display()}",
                    'description': reponse.objet,
                    'auteur': reponse.redacteur.get_full_name() if reponse.redacteur else 'Système',
                    'statut': reponse.get_statut_display()
                })
            
            # Trier par date
            timeline_data.sort(key=lambda x: x['date'])
            
            return Response(timeline_data)
            
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur timeline: {str(e)}")
            return Response(
                {"error": "Erreur lors de la récupération de la timeline"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def detail_traitement(self, request, pk=None):
        """Récupérer les détails du traitement d'un courrier"""
        try:
            courrier = Courrier.objects.get(pk=pk)
            
            # Récupérer toutes les données associées
            data = {
                'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
                'etapes_traitement': list(courrier.traitement_etapes.values()),
                'validations': list(courrier.validations.values()),
                'instructions': list(courrier.instructions.values()),
                'reponses': list(courrier.reponses.values()),
                'progression': self._calculate_progression(courrier)
            }
            
            return Response(data)
            
        except Courrier.DoesNotExist:
            return Response(
                {"error": "Courrier non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erreur détail traitement: {str(e)}")
            return Response(
                {"error": "Erreur lors de la récupération des détails"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_progression(self, courrier):
        """Calcule la progression du traitement"""
        etapes_total = courrier.traitement_etapes.count()
        etapes_terminees = courrier.traitement_etapes.filter(statut='termine').count()
        
        if etapes_total > 0:
            return int((etapes_terminees / etapes_total) * 100)
        
        # Basé sur le statut de traitement
        progression_map = {
            'prise_en_charge': 10,
            'analyse': 25,
            'instruction': 40,
            'redaction': 60,
            'validation': 75,
            'signature': 85,
            'envoi': 95,
            'cloture': 100,
            'rejete': 100,
        }
        
        return progression_map.get(courrier.traitement_statut, 0)

    # Dans courriers/views.py - Ajoutez ces méthodes améliorées

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def agents_disponibles(self, request, pk=None):
        """
        Liste détaillée des agents disponibles pour l'assignation
        Retourne les agents avec leurs statistiques de charge de travail
        """
        courrier = self.get_object()
        
        # Vérifier les permissions (chef du service ou admin)
        if request.user.role not in ['chef', 'admin', 'direction']:
            return Response(
                {"error": "Accès non autorisé"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Récupérer tous les agents du service
        agents = User.objects.filter(
            service=courrier.service_actuel,
            role__in=['agent_service', 'collaborateur'],
            actif=True
        ).annotate(
            # Compter les courriers en cours pour chaque agent
            courriers_en_cours=Count(
                'courriers_encours',
                filter=Q(courriers_encours__statut='traitement')
            ),
            courriers_en_retard=Count(
                'courriers_encours',
                filter=Q(
                    courriers_encours__statut='traitement',
                    courriers_encours__date_echeance__lt=timezone.now().date()
                )
            )
        ).values(
            'id', 'prenom', 'nom', 'email',
            'courriers_en_cours', 'courriers_en_retard'
        )
        
        # Ajouter une suggestion d'agent basée sur la charge de travail
        agents_list = list(agents)
        if agents_list:
            # Trier par charge de travail (moins de courriers = meilleur candidat)
            agents_list.sort(key=lambda x: x['courriers_en_cours'])
            
            # Ajouter un flag "recommandé" pour l'agent avec le moins de charge
            if len(agents_list) > 0:
                agents_list[0]['recommande'] = True
        
        return Response({
            'courrier': {
                'id': courrier.id,
                'reference': courrier.reference,
                'objet': courrier.objet,
                'priorite': courrier.priorite,
                'date_echeance': courrier.date_echeance
            },
            'agents': agents_list
        })


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def assignation_multi_criteres(self, request, pk=None):
        """
        Assignation avancée avec critères multiples
        """
        courrier = self.get_object()
        agent_id = request.data.get('agent_id')
        priorite_assignation = request.data.get('priorite_assignation', 'normale')
        commentaire = request.data.get('commentaire', '')
        instructions = request.data.get('instructions', '')
        delai_traitement = request.data.get('delai_traitement', 5)
        
        if not agent_id:
            return Response(
                {"error": "L'ID de l'agent est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Vérifier les permissions
        if request.user.role not in ['chef', 'admin', 'direction']:
            return Response(
                {"error": "Vous n'êtes pas autorisé à assigner ce courrier"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Récupérer l'agent avec sa charge de travail
            agent = User.objects.get(
                id=agent_id,
                service=courrier.service_actuel,
                role__in=['agent_service', 'collaborateur'],
                actif=True
            )
            
            # Mettre à jour le courrier
            courrier.responsable_actuel = agent
            courrier.agent_traitant = agent
            courrier.statut = 'traitement'
            courrier.traitement_statut = TraitementStatus.PRISE_EN_CHARGE
            courrier.delai_traitement_jours = delai_traitement
            
            # Recalculer la date d'échéance si nécessaire
            if delai_traitement and courrier.date_reception:
                courrier.date_echeance = courrier.date_reception + timedelta(days=delai_traitement)
            
            courrier.save()
            
            # Créer une instruction si fournie
            if instructions:
                InstructionCourrier.objects.create(
                    courrier=courrier,
                    type_instruction='assignation',
                    instruction=instructions,
                    agent_assignee=agent,
                    date_echeance=courrier.date_echeance,
                    statut='en_attente'
                )
            
            # Créer une étape de traitement
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='prise_en_charge',
                agent=agent,
                description=f"Assigné par {request.user.get_full_name()}",
                commentaire=commentaire,
                statut='en_cours'
            )
            
            # Journaliser
            ActionHistorique.objects.create(
                courrier=courrier,
                user=request.user,
                action="ASSIGNATION_AVANCEE",
                commentaire=f"Assigné à {agent.get_full_name()} avec priorité {priorite_assignation}"
            )
            
            # Retourner les détails complets
            serializer = CourrierDetailSerializer(courrier, context={'request': request})
            return Response({
                "success": True,
                "message": f"Courrier assigné avec succès à {agent.get_full_name()}",
                "courrier": serializer.data
            })
            
        except User.DoesNotExist:
            return Response(
                {"error": "Agent non trouvé ou non autorisé"},
                status=status.HTTP_404_NOT_FOUND
            )


    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def tableau_bord_assignation(self, request):
        """
        Tableau de bord pour le chef de service avec tous les courriers à assigner
        """
        user = request.user
        
        # Vérifier que c'est un chef de service
        if user.role != 'chef' or not user.service:
            return Response(
                {"error": "Accès réservé aux chefs de service"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Courriers à assigner (sans responsable)
        courriers_a_assigner = Courrier.objects.filter(
            service_actuel=user.service,
            responsable_actuel__isnull=True,
            archived=False,
            statut__in=['impute', 'recu']
        ).select_related('category', 'created_by').order_by('-priorite', 'date_echeance')
        
        # Courriers déjà assignés
        courriers_assignes = Courrier.objects.filter(
            service_actuel=user.service,
            responsable_actuel__isnull=False,
            archived=False,
            statut='traitement'
        ).select_related('responsable_actuel', 'category').order_by('-date_echeance')
        
        # Statistiques des agents
        agents_stats = User.objects.filter(
            service=user.service,
            role__in=['agent_service', 'collaborateur'],
            actif=True
        ).annotate(
            courriers_assignes=Count(
                'courriers_encours',
                filter=Q(courriers_encours__statut='traitement')
            ),
            courriers_termines=Count(
                'courriers_encours',
                filter=Q(courriers_encours__statut='repondu')
            ),
            courriers_en_retard=Count(
                'courriers_encours',
                filter=Q(
                    courriers_encours__statut='traitement',
                    courriers_encours__date_echeance__lt=timezone.now().date()
                )
            )
        ).values('id', 'prenom', 'nom', 'email', 'courriers_assignes', 'courriers_termines', 'courriers_en_retard')
        
        return Response({
            'a_assigner': CourrierListSerializer(courriers_a_assigner, many=True, context={'request': request}).data,
            'assignes': CourrierListSerializer(courriers_assignes, many=True, context={'request': request}).data,
            'agents_stats': agents_stats,
            'total_a_assigner': courriers_a_assigner.count(),
            'total_assignes': courriers_assignes.count()
        })


class TraitementDashboardViewSet(viewsets.ViewSet):
    """
    Dashboard spécifique pour le traitement des courriers
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Dashboard principal pour le traitement"""
        try:
            user = request.user
            
            # Statistiques générales
            stats = {
                'total_courriers': Courrier.objects.filter(
                    statut='traitement',
                    archived=False
                ).count(),
                'mes_courriers': Courrier.objects.filter(
                    responsable_actuel=user,
                    statut='traitement',
                    archived=False
                ).count(),
                'en_retard': Courrier.objects.filter(
                    date_echeance__lt=timezone.now().date(),
                    statut='traitement',
                    archived=False
                ).count(),
                'a_valider': ValidationCourrier.objects.filter(
                    validateur=user,
                    statut='en_attente'
                ).count(),
            }
            
            # Courriers urgents
            urgents = Courrier.objects.filter(
                priorite='urgente',
                statut='traitement',
                archived=False
            ).order_by('-date_reception')[:5]
            
            # Mes courriers en cours
            mes_courriers = Courrier.objects.filter(
                responsable_actuel=user,
                statut='traitement',
                archived=False
            ).order_by('-date_reception')[:10]
            
            # Validations en attente
            validations = ValidationCourrier.objects.filter(
                validateur=user,
                statut='en_attente'
            ).select_related('courrier').order_by('date_demande')[:10]
            
            return Response({
                'stats': stats,
                'urgents': CourrierListSerializer(urgents, many=True, context={'request': request}).data,
                'mes_courriers': CourrierDetailSerializer(mes_courriers, many=True, context={'request': request}).data,
                'validations': [{
                    'id': v.id,
                    'courrier_id': v.courrier.id,
                    'courrier_reference': v.courrier.reference,
                    'courrier_objet': v.courrier.objet,
                    'type_validation': v.get_type_validation_display(),
                    'date_demande': v.date_demande
                } for v in validations]
            })
            
        except Exception as e:
            logger.error(f"Erreur dashboard traitement: {str(e)}")
            return Response(
                {"error": "Erreur lors du chargement du dashboard"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )