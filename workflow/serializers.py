from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import (
    Workflow, WorkflowStep, WorkflowAction,
    WorkflowTemplate, Accuse
)
from courriers.serializers import CourrierListSerializer, CourrierDetailSerializer
from core.serializers import ServiceSerializer
from users.serializers import UserSerializer


class WorkflowActionSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    temps_reponse = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowAction
        fields = [
            'id', 'step', 'user', 'user_detail', 'action', 'action_display',
            'commentaire', 'date', 'temps_reponse'
        ]
        read_only_fields = ['date']
    
    def get_temps_reponse(self, obj):
        if obj.step and obj.step.date_action:
            return (obj.date - obj.step.date_action).total_seconds() / 3600  # en heures
        return None


class WorkflowStepSerializer(serializers.ModelSerializer):
    validator_detail = UserSerializer(source='validator', read_only=True)
    approbateur_service_detail = ServiceSerializer(source='approbateur_service', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    actions = WorkflowActionSerializer(many=True, read_only=True)
    est_en_retard = serializers.SerializerMethodField()
    temps_attente = serializers.SerializerMethodField()
    couleur_statut = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowStep
        fields = [
            'id', 'workflow', 'step_number', 'label',
            'validator', 'validator_detail',
            'approbateur_service', 'approbateur_service_detail',
            'statut', 'statut_display', 'couleur_statut',
            'commentaire', 'date_action', 'delai_attente_max',
            'actions_requises', 'notifier_avant_expiration',
            'heures_avant_notification', 'actions', 'est_en_retard',
            'temps_attente'
        ]
    
    def get_est_en_retard(self, obj):
        if obj.date_action and obj.delai_attente_max:
            delai_max = obj.date_action + timedelta(hours=obj.delai_attente_max)
            return timezone.now() > delai_max and obj.statut == 'en_attente'
        return False
    
    def get_temps_attente(self, obj):
        if obj.date_action:
            return (timezone.now() - obj.date_action).total_seconds() / 3600  # en heures
        return None
    
    def get_couleur_statut(self, obj):
        couleurs = {
            'en_attente': 'warning',
            'valide': 'success',
            'rejete': 'danger',
            'brouillon': 'secondary'
        }
        return couleurs.get(obj.statut, 'secondary')


class WorkflowSerializer(serializers.ModelSerializer):
    courrier_detail = CourrierDetailSerializer(source='courrier', read_only=True)
    steps = WorkflowStepSerializer(many=True, read_only=True)
    etape_actuelle = serializers.SerializerMethodField()
    progression = serializers.SerializerMethodField()
    est_bloque = serializers.SerializerMethodField()
    temps_total = serializers.SerializerMethodField()
    
    class Meta:
        model = Workflow
        fields = [
            'id', 'courrier', 'courrier_detail', 'created_at', 'updated_at',
            'current_step', 'steps', 'etape_actuelle', 'progression',
            'est_bloque', 'temps_total'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_etape_actuelle(self, obj):
        try:
            step = obj.steps.get(step_number=obj.current_step)
            return {
                'id': step.id,
                'label': step.label,
                'statut': step.statut,
                'validator': step.validator_id
            }
        except WorkflowStep.DoesNotExist:
            return None
    
    def get_progression(self, obj):
        total_steps = obj.steps.count()
        if total_steps > 0:
            steps_valides = obj.steps.filter(statut='valide').count()
            return round((steps_valides / total_steps) * 100, 2)
        return 0
    
    def get_est_bloque(self, obj):
        # Un workflow est bloqué si une étape est rejetée
        return obj.steps.filter(statut='rejete').exists()
    
    def get_temps_total(self, obj):
        if obj.steps.exists():
            premiere_date = obj.steps.order_by('date_action').first().date_action
            derniere_date = obj.steps.order_by('-date_action').first().date_action
            if premiere_date and derniere_date:
                return (derniere_date - premiere_date).total_seconds() / 3600  # en heures
        return None


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    category_detail = serializers.CharField(source='category.name', read_only=True)
    type_courrier_display = serializers.CharField(source='get_type_courrier_display', read_only=True)
    steps_config = serializers.JSONField(
        default=list,
        help_text="Configuration des étapes: [{'label': 'Validation chef', 'role': 'chef'}, ...]"
    )
    utilisation_count = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowTemplate
        fields = [
            'id', 'nom', 'description', 'type_courrier', 'type_courrier_display',
            'category', 'category_detail', 'steps_config', 'active',
            'utilisation_count', 
        ]
        #read_only_fields = ['created_at']
    
    def get_utilisation_count(self, obj):
        return Workflow.objects.filter(
            courrier__type=obj.type_courrier,
            courrier__category=obj.category
        ).count()


class AccuseSerializer(serializers.ModelSerializer):
    courrier_detail = CourrierListSerializer(source='courrier', read_only=True)
    type_accuse_display = serializers.CharField(source='get_type_accuse_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    est_envoye = serializers.SerializerMethodField()
    
    class Meta:
        model = Accuse
        fields = [
            'id', 'courrier', 'courrier_detail', 'type_accuse', 'type_accuse_display',
            'destinataire_email', 'envoye_le', 'message_id', 'status', 'status_display',
            'est_envoye'
        ]
        read_only_fields = ['envoye_le']
    
    def get_est_envoye(self, obj):
        return obj.status == 'envoye' or obj.status == 'lu'


class WorkflowCreateSerializer(serializers.Serializer):
    """Serializer pour créer un workflow"""
    courrier_id = serializers.IntegerField(required=True)
    template_id = serializers.IntegerField(required=False, allow_null=True)
    validateurs = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Liste des IDs des utilisateurs validateurs dans l'ordre"
    )
    delai_global = serializers.IntegerField(
        required=False,
        default=48,
        help_text="Délai global en heures pour le workflow"
    )
    notifications = serializers.BooleanField(default=True)


class StepActionSerializer(serializers.Serializer):
    """Serializer pour les actions sur les étapes"""
    action = serializers.ChoiceField(
        choices=['valider', 'rejeter', 'commenter', 'transferer']
    )
    commentaire = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )
    nouveau_validateur = serializers.IntegerField(
        required=False,
        help_text="ID du nouveau validateur pour un transfert"
    )
    force = serializers.BooleanField(
        default=False,
        help_text="Forcer l'action même si les conditions ne sont pas remplies"
    )


class WorkflowStatsSerializer(serializers.Serializer):
    """Serializer pour les statistiques de workflow"""
    total_workflows = serializers.IntegerField()
    workflows_actifs = serializers.IntegerField()
    workflows_termines = serializers.IntegerField()
    workflows_bloques = serializers.IntegerField()
    taux_achevement = serializers.FloatField()
    delai_moyen = serializers.FloatField(help_text="En heures")
    etapes_en_retard = serializers.IntegerField()
    service_plus_actif = serializers.DictField()
    validateur_plus_actif = serializers.DictField()
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['taux_achevement'] = round(data['taux_achevement'], 2)
        data['delai_moyen'] = round(data['delai_moyen'], 2)
        return data


class NotificationSerializer(serializers.Serializer):
    """Serializer pour les notifications de workflow"""
    id = serializers.IntegerField()
    type = serializers.CharField()
    titre = serializers.CharField()
    message = serializers.CharField()
    workflow_id = serializers.IntegerField()
    step_id = serializers.IntegerField()
    courrier_reference = serializers.CharField()
    date_notification = serializers.DateTimeField()
    lue = serializers.BooleanField()
    action_requise = serializers.BooleanField()