from django.utils import timezone
from django.db import models
from django.db import transaction
from django.db.models import Q, Count, Avg
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend


from .models import Workflow, WorkflowStep, WorkflowAction, WorkflowTemplate, Accuse
from .serializers import (
    WorkflowSerializer, WorkflowStepSerializer, WorkflowActionSerializer,
    WorkflowTemplateSerializer, AccuseSerializer, WorkflowCreateSerializer,
    StepActionSerializer, WorkflowStatsSerializer, NotificationSerializer
)
from courriers.models import Courrier
from users.models import User
import logging

logger = logging.getLogger(__name__)


class WorkflowViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des workflows
    """
    queryset = Workflow.objects.all().order_by('-created_at')
    serializer_class = WorkflowSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['courrier__reference', 'courrier__objet']
    ordering_fields = ['created_at', 'updated_at', 'current_step']
    
    filterset_fields = {
        'courrier__type': ['exact'],
        'courrier__statut': ['exact'],
        'courrier__priorite': ['exact'],
        'current_step': ['exact', 'gte', 'lte'],
    }
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtrage par statut
        statut = self.request.query_params.get('statut')
        if statut == 'actif':
            queryset = queryset.filter(courrier__statut__in=['recu', 'impute', 'traitement'])
        elif statut == 'termine':
            queryset = queryset.filter(courrier__statut__in=['repondu', 'archive'])
        elif statut == 'bloque':
            queryset = queryset.filter(steps__statut='rejete').distinct()
        
        # Filtrage par utilisateur
        if not self.request.user.is_superuser:
            # Workflows où l'utilisateur est validateur
            user_steps = WorkflowStep.objects.filter(
                Q(validator=self.request.user) | 
                Q(approbateur_service=self.request.user.service)
            )
            workflow_ids = user_steps.values_list('workflow_id', flat=True).distinct()
            queryset = queryset.filter(id__in=workflow_ids)
        
        return queryset
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Créer un workflow"""
        serializer = WorkflowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            courrier_id = serializer.validated_data['courrier_id']
            template_id = serializer.validated_data.get('template_id')
            validateurs = serializer.validated_data.get('validateurs', [])
            delai_global = serializer.validated_data.get('delai_global', 48)
            
            courrier = get_object_or_404(Courrier, id=courrier_id)
            
            # Vérifier qu'un workflow n'existe pas déjà
            if hasattr(courrier, 'workflow'):
                return Response(
                    {"error": "Un workflow existe déjà pour ce courrier"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Créer le workflow
            workflow = Workflow.objects.create(courrier=courrier)
            
            # Utiliser un template ou créer des étapes par défaut
            if template_id:
                template = get_object_or_404(WorkflowTemplate, id=template_id)
                self._creer_etapes_depuis_template(workflow, template, validateurs, delai_global)
            else:
                self._creer_etapes_par_defaut(workflow, validateurs, delai_global)
            
            return Response(
                WorkflowSerializer(workflow, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Erreur création workflow: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Erreur création: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def avancer(self, request, pk=None):
        """Avancer le workflow à l'étape suivante"""
        workflow = self.get_object()
        
        # Vérifier que l'étape courante est validée
        try:
            step_courante = workflow.steps.get(step_number=workflow.current_step)
            if step_courante.statut != 'valide':
                return Response(
                    {"error": "L'étape courante doit être validée"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except WorkflowStep.DoesNotExist:
            pass
        
        # Avancer
        workflow.current_step += 1
        workflow.save()
        
        # Notifier le prochain validateur
        self._notifier_prochain_validateur(workflow)
        
        return Response({
            "message": f"Workflow avancé à l'étape {workflow.current_step}",
            "current_step": workflow.current_step
        })
    
    @action(detail=True, methods=['post'])
    def reculer(self, request, pk=None):
        """Reculer le workflow à l'étape précédente"""
        workflow = self.get_object()
        
        if workflow.current_step <= 1:
            return Response(
                {"error": "Impossible de reculer, déjà à la première étape"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        workflow.current_step -= 1
        workflow.save()
        
        return Response({
            "message": f"Workflow reculé à l'étape {workflow.current_step}",
            "current_step": workflow.current_step
        })
    
    @action(detail=True, methods=['get'])
    def etapes(self, request, pk=None):
        """Récupérer les étapes d'un workflow"""
        workflow = self.get_object()
        steps = workflow.steps.all().order_by('step_number')
        serializer = WorkflowStepSerializer(steps, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def mes_workflows(self, request):
        """Récupérer les workflows de l'utilisateur"""
        # Workflows où l'utilisateur est validateur sur l'étape courante
        workflows = Workflow.objects.filter(
            steps__step_number=models.F('current_step'),
            steps__validator=request.user
        ).distinct()
        
        serializer = self.get_serializer(workflows, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistiques(self, request):
        workflows = self.get_queryset()

        stats = {
            'total_workflows': workflows.count(),
            'workflows_actifs': workflows.filter(courrier__statut__in=['recu', 'impute', 'traitement']).count(),
            'workflows_termines': workflows.filter(courrier__statut__in=['repondu', 'archive']).count(),
            'workflows_bloques': workflows.filter(steps__statut='rejete').distinct().count(),
            'taux_achevement': 0,
            'delai_moyen': 0,
            'etapes_en_retard': 0,
            'service_plus_actif': None,
            'validateur_plus_actif': None,
        }
        
        # Calcul du taux d'achèvement
        if stats['total_workflows'] > 0:
            stats['taux_achevement'] = round(
                (stats['workflows_termines'] / stats['total_workflows']) * 100, 2
            )
        
        # Calcul du délai moyen
        workflows_termines = workflows.filter(courrier__statut__in=['repondu', 'archive'])
        if workflows_termines.exists():
            delais = []
            for wf in workflows_termines:
                if wf.steps.exists():
                    premiere = wf.steps.order_by('date_action').first().date_action
                    derniere = wf.steps.order_by('-date_action').first().date_action
                    if premiere and derniere:
                        delais.append((derniere - premiere).total_seconds() / 3600)
            
            if delais:
                stats['delai_moyen'] = round(sum(delais) / len(delais), 2)
        
        # Nombre d'étapes en retard
        stats['etapes_en_retard'] = WorkflowStep.objects.filter(
            statut='en_attente',
            date_action__isnull=False,
            delai_attente_max__gt=0
        ).filter(
            date_action__lt=timezone.now() - models.F('delai_attente_max') * 3600
        ).count()
        
        serializer = WorkflowStatsSerializer(stats)
        return Response(serializer.data)
    
    # Méthodes utilitaires
    def _creer_etapes_depuis_template(self, workflow, template, validateurs, delai_global):
        """Créer des étapes depuis un template"""
        from .models import WorkflowStep
        
        steps_config = template.steps_config
        if not steps_config:
            steps_config = [
                {'label': 'Étape 1', 'role': 'collaborateur'},
                {'label': 'Étape 2', 'role': 'chef'},
                {'label': 'Étape 3', 'role': 'direction'}
            ]
        
        # Calculer le délai par étape
        delai_par_etape = delai_global // len(steps_config) if len(steps_config) > 0 else 24
        
        for i, config in enumerate(steps_config, 1):
            validator = None
            if validateurs and i <= len(validateurs):
                try:
                    validator = User.objects.get(id=validateurs[i-1])
                except User.DoesNotExist:
                    pass
            
            WorkflowStep.objects.create(
                workflow=workflow,
                step_number=i,
                label=config.get('label', f'Étape {i}'),
                validator=validator,
                delai_attente_max=delai_par_etape,
                actions_requises=config.get('actions', ['valider'])
            )
    
    def _creer_etapes_par_defaut(self, workflow, validateurs, delai_global):
        """Créer des étapes par défaut"""
        from .models import WorkflowStep
        
        # Configuration par défaut selon le type de courrier
        if workflow.courrier.type == 'entrant':
            labels = ['Réception', 'Analyse', 'Traitement', 'Validation']
        elif workflow.courrier.type == 'sortant':
            labels = ['Rédaction', 'Visa', 'Validation', 'Signature']
        else:
            labels = ['Création', 'Approbation', 'Diffusion']
        
        delai_par_etape = delai_global // len(labels)
        
        for i, label in enumerate(labels, 1):
            validator = None
            if validateurs and i <= len(validateurs):
                try:
                    validator = User.objects.get(id=validateurs[i-1])
                except User.DoesNotExist:
                    pass
            
            WorkflowStep.objects.create(
                workflow=workflow,
                step_number=i,
                label=label,
                validator=validator,
                delai_attente_max=delai_par_etape
            )
    
    def _notifier_prochain_validateur(self, workflow):
        """Notifier le prochain validateur via WebSocket (notify.py)"""
        try:
            from courriers.notify import notify_user
            next_step = workflow.steps.get(step_number=workflow.current_step)
            if next_step.validator_id:
                notify_user(
                    user_id=next_step.validator_id,
                    message=f"Une étape de validation vous attend : {workflow.courrier.reference} — {next_step.label}",
                    notification_type="validation_requise",
                    data={
                        "courrier_id": workflow.courrier_id,
                        "reference": workflow.courrier.reference,
                        "workflow_id": workflow.id,
                        "step_id": next_step.id,
                        "step_label": next_step.label,
                    }
                )
        except WorkflowStep.DoesNotExist:
            pass
        except Exception as e:
            logger.warning(f"[Workflow] Notification impossible: {e}")


class WorkflowStepViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des étapes de workflow
    """
    queryset = WorkflowStep.objects.all().order_by('workflow', 'step_number')
    serializer_class = WorkflowStepSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtrer par workflow
        workflow_id = self.request.query_params.get('workflow_id')
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        
        # Filtrer par validateur
        validateur_id = self.request.query_params.get('validateur_id')
        if validateur_id:
            queryset = queryset.filter(validator_id=validateur_id)
        
        # Filtrer par statut
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        
        # Filtrage des étapes en retard
        if self.request.query_params.get('en_retard') == 'true':
            queryset = queryset.filter(
                statut='en_attente',
                date_action__isnull=False,
                delai_attente_max__gt=0
            ).filter(
                date_action__lt=timezone.now() - models.F('delai_attente_max') * 3600
            )
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def executer_action(self, request, pk=None):
        """Effectuer une action sur une étape"""
        step = self.get_object()
        serializer = StepActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action_type = serializer.validated_data['action']
        commentaire = serializer.validated_data.get('commentaire', '')
        nouveau_validateur = serializer.validated_data.get('nouveau_validateur')
        force = serializer.validated_data.get('force', False)

        try:
            # ─── Vérification des permissions ──────────────────────────────
            if not force:
                autorise = False
                # 1. Validateur direct
                if step.validator == request.user:
                    autorise = True
                # 2. Chef du service approbateur
                elif step.approbateur_service and step.approbateur_service.chef == request.user:
                    autorise = True
                # 3. Admin ou direction
                elif request.user.role in ['admin', 'direction']:
                    autorise = True

                if not autorise:
                    return Response(
                        {"error": "Vous n'êtes pas autorisé à agir sur cette étape"},
                        status=status.HTTP_403_FORBIDDEN
                    )

            # ─── Traitement des actions ────────────────────────────────────
            if action_type == 'valider':
                step.statut = 'valide'
                step.commentaire = commentaire
                step.date_action = timezone.now()
                step.save()

                # Avancer le workflow si c'est l'étape courante
                if step.step_number == step.workflow.current_step:
                    step.workflow.current_step += 1
                    step.workflow.save()

                message = "Étape validée"

            elif action_type == 'rejeter':
                step.statut = 'rejete'
                step.commentaire = commentaire
                step.date_action = timezone.now()
                step.save()
                message = "Étape rejetée"

            elif action_type == 'commenter':
                step.commentaire = commentaire
                step.save()
                message = "Commentaire ajouté"

            elif action_type == 'transferer':
                if nouveau_validateur:
                    try:
                        new_validator = User.objects.get(id=nouveau_validateur)
                        step.validator = new_validator
                        step.save()
                        message = f"Étape transférée à {new_validator.email}"
                    except User.DoesNotExist:
                        return Response(
                            {"error": "Utilisateur non trouvé"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                else:
                    return Response(
                        {"error": "Nouveau validateur requis"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Enregistrer l'action
            WorkflowAction.objects.create(
                step=step,
                user=request.user,
                action=action_type,
                commentaire=commentaire
            )

            return Response({
                "message": message,
                "step": WorkflowStepSerializer(step).data
            })

        except Exception as e:
            logger.error(f"Erreur action étape: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Erreur action: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])   # BUG 5 FIX : detail=True car self.get_object() requiert un pk
    def historique(self, request, pk=None):
        """Récupérer l'historique d'une étape"""
        step = self.get_object()
        actions = step.actions.all().order_by('-date')
        serializer = WorkflowActionSerializer(actions, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def mes_etapes(self, request):
        """Récupérer les étapes assignées à l'utilisateur"""
        steps = self.get_queryset().filter(
            Q(validator=request.user) | 
            Q(approbateur_service=request.user.service)
        ).filter(
            statut='en_attente'
        ).order_by('workflow__current_step', 'step_number')
        
        serializer = self.get_serializer(steps, many=True)
        return Response(serializer.data)


class WorkflowTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des templates de workflow
    """
    queryset = WorkflowTemplate.objects.filter(active=True).order_by('nom')
    serializer_class = WorkflowTemplateSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def dupliquer(self, request, pk=None):
        """Dupliquer un template"""
        template = self.get_object()
        
        new_template = WorkflowTemplate.objects.create(
            nom=f"{template.nom} (copie)",
            description=template.description,
            type_courrier=template.type_courrier,
            category=template.category,
            steps_config=template.steps_config,
            active=True
        )
        
        serializer = self.get_serializer(new_template)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def desactiver(self, request, pk=None):
        """Désactiver un template"""
        template = self.get_object()
        template.active = False
        template.save()
        
        return Response({"message": "Template désactivé"})


class AccuseViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des accusés de réception
    """
    queryset = Accuse.objects.all().order_by('-envoye_le')
    serializer_class = AccuseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtrer par courrier
        courrier_id = self.request.query_params.get('courrier_id')
        if courrier_id:
            queryset = queryset.filter(courrier_id=courrier_id)
        
        # Filtrer par type
        type_accuse = self.request.query_params.get('type_accuse')
        if type_accuse:
            queryset = queryset.filter(type_accuse=type_accuse)
        
        # Filtrer par statut
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def renvoyer(self, request, pk=None):
        """Renvoyer un accusé"""
        accuse = self.get_object()
        
        # Implémenter la logique de renvoi
        # ...
        
        return Response({"message": "Accusé renvoyé"})