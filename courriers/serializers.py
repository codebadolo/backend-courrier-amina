from rest_framework import serializers
from django.utils import timezone
from datetime import datetime
from .models import (
    Courrier, PieceJointe, Imputation, ActionHistorique,
    ModeleCourrier, TypeCourrier, StatusCourrier, PriorityLevel, TraitementEtape,
    ValidationCourrier, CourrierReponse, InstructionCourrier, WorkflowValidation
)
from core.serializers import ServiceSerializer, CategorySerializer, MiniUserSerializer
from users.serializers import UserSerializer
import json


class PieceJointeSerializer(serializers.ModelSerializer):
    fichier_url = serializers.SerializerMethodField()
    fichier_nom = serializers.SerializerMethodField()
    fichier_taille = serializers.SerializerMethodField()
    uploaded_by_detail = MiniUserSerializer(source='uploaded_by', read_only=True)
    
    class Meta:
        model = PieceJointe
        fields = [
            'id', 'courrier', 'fichier', 'fichier_url', 'fichier_nom',
            'fichier_taille', 'description', 'uploaded_by', 'uploaded_by_detail',
            'uploaded_at'
        ]
        read_only_fields = ['uploaded_at', 'uploaded_by']
    
    def get_fichier_url(self, obj):
        request = self.context.get('request')
        if request and obj.fichier:
            return request.build_absolute_uri(obj.fichier.url)
        return None
    
    def get_fichier_nom(self, obj):
        if obj.fichier:
            return obj.fichier.name.split('/')[-1]
        return None
    
    def get_fichier_taille(self, obj):
        if obj.fichier:
            try:
                return obj.fichier.size
            except:
                return None
        return None


class ImputationSerializer(serializers.ModelSerializer):
    service_detail = ServiceSerializer(source='service', read_only=True)
    responsable_detail = UserSerializer(source='responsable', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    courrier_objet = serializers.CharField(source='courrier.objet', read_only=True)
    
    class Meta:
        model = Imputation
        fields = [
            'id', 'courrier', 'courrier_reference', 'courrier_objet',
            'service', 'service_detail', 'responsable', 'responsable_detail',
            'commentaire', 'suggestion_ia', 'score_ia', 'date_imputation'
        ]
        read_only_fields = ['date_imputation']


class ActionHistoriqueSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    
    class Meta:
        model = ActionHistorique
        fields = [
            'id', 'courrier', 'courrier_reference', 'user', 'user_detail',
            'action', 'anciens_valeurs', 'nouvelles_valeurs', 'commentaire', 'date'
        ]
        read_only_fields = ['date']


class CourrierListSerializer(serializers.ModelSerializer):
    """Serializer pour la liste (allégé)"""
    category_nom = serializers.CharField(source='category.name', read_only=True)
    service_impute_nom = serializers.CharField(source='service_impute.nom', read_only=True)
    expediteur_initiale = serializers.SerializerMethodField()
    jours_restants = serializers.SerializerMethodField()
    est_en_retard = serializers.SerializerMethodField()
    priorite_icone = serializers.SerializerMethodField()
    
    class Meta:
        model = Courrier
        fields = [
            'id', 'reference', 'type', 'objet', 'expediteur_nom',
            'expediteur_initiale', 'date_reception', 'date_echeance',
            'statut', 'priorite', 'priorite_icone', 'confidentialite',
            'category', 'category_nom', 'service_impute', 'service_impute_nom',
            'jours_restants', 'est_en_retard', 'created_at'
        ]
    
    def get_expediteur_initiale(self, obj):
        if obj.expediteur_nom:
            mots = obj.expediteur_nom.split()
            if len(mots) >= 2:
                return f"{mots[0][0]}{mots[1][0]}".upper()
            return obj.expediteur_nom[0:2].upper()
        return "??"
    
    def get_jours_restants(self, obj):
        if obj.date_echeance:
            delta = obj.date_echeance - timezone.now().date()
            return max(0, delta.days)
        return None
    
    def get_est_en_retard(self, obj):
        if obj.date_echeance and obj.statut not in ['repondu', 'archive']:
            return obj.date_echeance < timezone.now().date()
        return False
    
    def get_priorite_icone(self, obj):
        icones = {
            'urgente': '🔥',
            'haute': '⚠️',
            'normale': '📄',
            'basse': '📋'
        }
        return icones.get(obj.priorite, '📄')


class CourrierDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour un courrier"""
    # Relations directes
    category_detail = CategorySerializer(source='category', read_only=True)
    service_impute_detail = ServiceSerializer(source='service_impute', read_only=True)
    service_actuel_detail = ServiceSerializer(source='service_actuel', read_only=True)
    responsable_actuel_detail = UserSerializer(source='responsable_actuel', read_only=True)
    created_by_detail = UserSerializer(source='created_by', read_only=True)
    ocr = serializers.BooleanField(default=False, write_only=True, required=False )  
    classifier = serializers.BooleanField(default=False, write_only=True, required=False )  
    creer_workflow = serializers.BooleanField(default=False, write_only=True, required=False)
    ia_suggestions_accepted = serializers.BooleanField(default=False, write_only=True, required=False)
    ia_suggestions_data = serializers.JSONField(required=False, allow_null=True)
    user_modifications = serializers.JSONField(required=False, allow_null=True)
    traitement_statut_display = serializers.CharField(source='get_traitement_statut_display', read_only=True)

    
    # Relations inverses
    pieces_jointes = PieceJointeSerializer(many=True, read_only=True)
    imputations = ImputationSerializer(many=True, read_only=True)
    historiques = ActionHistoriqueSerializer(many=True, read_only=True)
    
    # Calculs
    jours_restants = serializers.SerializerMethodField()
    est_en_retard = serializers.SerializerMethodField()
    delai_traitement = serializers.SerializerMethodField()
    
    # Display fields
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    priorite_display = serializers.CharField(source='get_priorite_display', read_only=True)
    confidentialite_display = serializers.CharField(source='get_confidentialite_display', read_only=True)
    canal_display = serializers.CharField(source='get_canal_display', read_only=True)
    
    # Workflow
    workflow_existe = serializers.SerializerMethodField()
    workflow_statut = serializers.SerializerMethodField()

    
    
    class Meta:
        model = Courrier
        fields = [
            # Identifiants
            'id', 'reference',
            
            # Type et statut
            'type', 'type_display', 'statut', 'statut_display',
            
            # Contenu
            'objet', 'contenu_texte', 'meta_analyse', 'reponse_suggeree',
            
            # Priorité et confidentialité
            'priorite', 'priorite_display', 'confidentialite', 'confidentialite_display',
            
            # Expéditeur/Destinataire
            'expediteur_nom', 'expediteur_adresse', 'expediteur_email',
            'destinataire_nom', 'canal', 'canal_display',
            
            # Classification
            'category', 'category_detail', 'service_impute', 'service_impute_detail',
            'service_actuel', 'service_actuel_detail', 'responsable_actuel', 'responsable_actuel_detail',
            
            # Dates
            'date_reception', 'date_echeance', 'date_envoi', 'date_limite_traitement',
            'date_cloture', 'created_at', 'updated_at', 'date_archivage',
            
            # Gestion
            'created_by', 'created_by_detail', 'archived',
            
            # Codes
            'qr_code', 'barcode',
            
            # Calculs
            'jours_restants', 'est_en_retard', 'delai_traitement',
            
            # Workflow
            'workflow_existe', 'workflow_statut',
            
            # Relations
            'pieces_jointes', 'imputations', 'historiques',
            'type', 'objet', 'priorite', 'confidentialite',
            'date_reception', 'expediteur_nom', 'expediteur_adresse',
            'expediteur_email', 'destinataire_nom', 'canal',
            'category', 'service_impute', 'date_echeance',
            'pieces_jointes', 'ocr', 'classifier', 'creer_workflow',
            'ia_suggestions_accepted', 'ia_suggestions_data', 
            'user_modifications',
            'analyse_notes', 'analyse_date', 'analyse_par',
            'actions_requises', 'documents_necessaires',
            'consultations', 'decision_preliminaire',
            'traitement_statut',
            'traitement_statut_display',
            
        ]

        extra_kwargs = {
            'expediteur_adresse': {'required': False, 'allow_blank': True},
            'expediteur_email': {'required': False, 'allow_blank': True},
            'destinataire_nom': {'required': False, 'allow_blank': True},
            'date_echeance': {'required': False},
            'priorite': {'default': 'normale'},
        }

        read_only_fields = [
            'reference', 'created_at', 'updated_at', 'created_by',
            'jours_restants', 'est_en_retard', 'delai_traitement',
            'workflow_existe', 'workflow_statut'
        ]

    def create(self, validated_data):
        # Extraire les données IA
        ia_suggestions_accepted = validated_data.pop('ia_suggestions_accepted', False)
        ia_suggestions_data = validated_data.pop('ia_suggestions_data', None)
        user_modifications = validated_data.pop('user_modifications', None)
        
        # Créer le courrier
        courrier = super().create(validated_data)
        
        # Stocker les données IA dans meta_analyse si acceptées
        if ia_suggestions_accepted and ia_suggestions_data:
            courrier.meta_analyse = {
                **ia_suggestions_data,
                'user_modifications': user_modifications,
                'ia_accepted_at': timezone.now().isoformat(),
                'ia_accepted_by': self.context['request'].user.id
            }
            courrier.save(update_fields=['meta_analyse'])
            
            # Journaliser l'acceptation IA
            ActionHistorique.objects.create(
                courrier=courrier,
                user=self.context['request'].user,
                action="IA_SUGGESTIONS_ACCEPTED",
                commentaire="L'utilisateur a accepté les suggestions de l'IA",
                nouvelles_valeurs=json.dumps({
                    'ia_suggestions': ia_suggestions_data,
                    'user_modifications': user_modifications
                }, ensure_ascii=False)
            )
        
        return courrier   
    
    def get_jours_restants(self, obj):
        if obj.date_echeance:
            delta = obj.date_echeance - timezone.now().date()
            return delta.days
        return None
    
    def get_est_en_retard(self, obj):
        if obj.date_echeance and obj.statut not in ['repondu', 'archive']:
            return obj.date_echeance < timezone.now().date()
        return False
    
    def get_delai_traitement(self, obj):
        if obj.date_reception and obj.date_cloture:
            return (obj.date_cloture - obj.date_reception).days
        elif obj.date_reception:
            return (timezone.now().date() - obj.date_reception).days
        return None
    
    def get_workflow_existe(self, obj):
        return hasattr(obj, 'workflow') and obj.workflow is not None
    
    def get_workflow_statut(self, obj):
        if hasattr(obj, 'workflow'):
            return {
                'current_step': obj.workflow.current_step,
                'total_steps': obj.workflow.steps.count() if hasattr(obj.workflow, 'steps') else 0
            }
        return None


class CourrierCreateSerializer(serializers.ModelSerializer):
    pieces_jointes = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        help_text="Liste des fichiers à joindre"
    )
    ocr = serializers.BooleanField(default=True, write_only=True, required=False) # CHANGÉ
    classifier = serializers.BooleanField(default=True, write_only=True, required=False) # CHANGÉ
    creer_workflow = serializers.BooleanField(default=True, write_only=True, required=False) # CHANGÉ
    
    class Meta:
        model = Courrier
        fields = [
            'type', 'objet', 'priorite', 'confidentialite',
            'date_reception', 'expediteur_nom', 'expediteur_adresse',
            'expediteur_email', 'expediteur_telephone', 'destinataire_nom',
            'canal', 'category', 'service_impute', 'date_echeance',
            'contenu_texte',  # AJOUTÉ pour recevoir le texte OCR
            'pieces_jointes', 'ocr', 'classifier', 'creer_workflow'
        ]
        extra_kwargs = {
            'expediteur_adresse': {'required': False, 'allow_blank': True},
            'expediteur_email': {'required': False, 'allow_blank': True},
            'expediteur_telephone': {'required': False, 'allow_blank': True},
            'destinataire_nom': {'required': False, 'allow_blank': True},
            'date_echeance': {'required': False},
            'priorite': {'default': 'normale'},
            'contenu_texte': {'required': False, 'allow_blank': True},
        }
    
    def validate(self, data):
        # Validation personnalisée
        if data.get('type') == 'entrant' and not data.get('expediteur_nom'):
            raise serializers.ValidationError({
                "expediteur_nom": "L'expéditeur est obligatoire pour un courrier entrant"
            })
        
        if data.get('type') == 'sortant' and not data.get('destinataire_nom'):
            raise serializers.ValidationError({
                "destinataire_nom": "Le destinataire est obligatoire pour un courrier sortant"
            })
        
        # Date d'échéance doit être dans le futur
        if data.get('date_echeance'):
            if data['date_echeance'] < timezone.now().date():
                raise serializers.ValidationError({
                    "date_echeance": "La date d'échéance doit être dans le futur"
                })
        
        return data


class CourrierUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Courrier
        fields = [
            'objet', 'priorite', 'confidentialite',
            'date_echeance', 'category', 'service_impute',
            'service_actuel', 'responsable_actuel', 'statut'
        ]
    
    def validate_statut(self, value):
        """Validation des transitions de statut"""
        instance = self.instance
        transitions_valides = {
            'recu': ['impute', 'archive'],
            'impute': ['traitement', 'archive'],
            'traitement': ['repondu', 'archive'],
            'repondu': ['archive'],
            'archive': []
        }
        
        if instance and instance.statut in transitions_valides:
            if value not in transitions_valides[instance.statut]:
                raise serializers.ValidationError(
                    f"Transition invalide de {instance.statut} vers {value}"
                )
        
        return value


class ModeleCourrierSerializer(serializers.ModelSerializer):
    category_detail = CategorySerializer(source='category', read_only=True)
    service_detail = ServiceSerializer(source='service', read_only=True)
    type_modele_display = serializers.CharField(source='get_type_modele_display', read_only=True)
    utilisations = serializers.SerializerMethodField()
    
    class Meta:
        model = ModeleCourrier
        fields = [
            'id', 'nom', 'type_modele', 'type_modele_display',
            'category', 'category_detail', 'contenu', 'variables',
            'entete', 'pied_page', 'service', 'service_detail',
            'actif', 'utilisations', 'created_at'
        ]
        read_only_fields = ['created_at']
    
    def get_utilisations(self, obj):
        from courriers.models import Courrier
        return Courrier.objects.filter(
            objet__icontains=obj.nom
        ).count()


class CourrierStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    entrants = serializers.IntegerField()
    sortants = serializers.IntegerField()
    internes = serializers.IntegerField()
    en_cours = serializers.IntegerField()
    en_retard = serializers.IntegerField()
    traites = serializers.IntegerField()
    taux_traitement = serializers.FloatField()
    delai_moyen = serializers.FloatField()
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['taux_traitement'] = round(data['taux_traitement'], 2)
        data['delai_moyen'] = round(data['delai_moyen'], 2)
        return data


class ImportCourrierSerializer(serializers.Serializer):
    """Serializer pour l'import de courriers"""
    fichier = serializers.FileField(help_text="Fichier CSV ou Excel")
    type_courrier = serializers.ChoiceField(choices=TypeCourrier.choices)
    mapping = serializers.JSONField(
        default=dict,
        help_text="Mapping des colonnes (ex: {'A': 'expediteur_nom', 'B': 'objet'})"
    )


class ExportCourrierSerializer(serializers.Serializer):
    """Serializer pour l'export de courriers"""
    format = serializers.ChoiceField(choices=['csv', 'excel', 'pdf', 'json'])
    periode_debut = serializers.DateField(required=False)
    periode_fin = serializers.DateField(required=False)
    type_courrier = serializers.ChoiceField(
        choices=TypeCourrier.choices + [('tous', 'Tous')],
        default='tous'
    )
    colonnes = serializers.ListField(
        child=serializers.CharField(),
        default=['reference', 'objet', 'expediteur_nom', 'date_reception', 'statut']
    )

# courriers/serializers.py

class TraitementEtapeSerializer(serializers.ModelSerializer):
    agent_detail = UserSerializer(source='agent', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    courrier_objet = serializers.CharField(source='courrier.objet', read_only=True)
    type_etape_display = serializers.CharField(source='get_type_etape_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    
    class Meta:
        model = TraitementEtape
        fields = [
            'id', 'courrier', 'courrier_reference', 'courrier_objet',
            'type_etape', 'type_etape_display', 'agent', 'agent_detail',
            'description', 'commentaire', 'date_debut', 'date_fin',
            'duree_minutes', 'statut', 'statut_display', 'documents_associes',
            'validation_requise', 'validateurs'
        ]
        read_only_fields = ['date_debut']


class ValidationCourrierSerializer(serializers.ModelSerializer):
    validateur_detail = UserSerializer(source='validateur', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    courrier_objet = serializers.CharField(source='courrier.objet', read_only=True)
    type_validation_display = serializers.CharField(source='get_type_validation_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    
    class Meta:
        model = ValidationCourrier
        fields = [
            'id', 'courrier', 'courrier_reference', 'courrier_objet',
            'type_validation', 'type_validation_display', 'validateur', 'validateur_detail',
            'ordre', 'statut', 'statut_display', 'commentaire',
            'date_demande', 'date_action', 'signature_data',
            'signature_image', 'certificat_info'
        ]
        read_only_fields = ['date_demande']


class CourrierReponseSerializer(serializers.ModelSerializer):
    redacteur_detail = UserSerializer(source='redacteur', read_only=True)
    validateur_detail = UserSerializer(source='validateur', read_only=True)
    signataire_detail = UserSerializer(source='signataire', read_only=True)
    courrier_origine_reference = serializers.CharField(source='courrier_origine.reference', read_only=True)
    courrier_origine_objet = serializers.CharField(source='courrier_origine.objet', read_only=True)
    type_reponse_display = serializers.CharField(source='get_type_reponse_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    canal_envoi_display = serializers.CharField(source='get_canal_envoi_display', read_only=True)
    
    class Meta:
        model = CourrierReponse
        fields = [
            'id', 'courrier_origine', 'courrier_origine_reference', 'courrier_origine_objet',
            'type_reponse', 'type_reponse_display', 'reference', 'objet', 'contenu',
            'modele_utilise', 'destinataires', 'copies', 'date_redaction',
            'date_validation', 'date_signature', 'date_envoi', 'statut', 'statut_display',
            'redacteur', 'redacteur_detail', 'validateur', 'validateur_detail',
            'signataire', 'signataire_detail', 'pieces_jointes_reponse',
            'canal_envoi', 'canal_envoi_display', 'confirmation_reception',
            'date_confirmation', 'template_html', 'entete', 'pied_page',
            'signature_html'
        ]
        read_only_fields = ['date_redaction', 'reference']


class InstructionCourrierSerializer(serializers.ModelSerializer):
    agent_assignee_detail = UserSerializer(source='agent_assignee', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    courrier_objet = serializers.CharField(source='courrier.objet', read_only=True)
    type_instruction_display = serializers.CharField(source='get_type_instruction_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    
    class Meta:
        model = InstructionCourrier
        fields = [
            'id', 'courrier', 'courrier_reference', 'courrier_objet',
            'type_instruction', 'type_instruction_display', 'instruction',
            'agent_assignee', 'agent_assignee_detail', 'date_assignation',
            'date_echeance', 'date_accomplie', 'statut', 'statut_display',
            'resultat', 'documents_produits'
        ]
        read_only_fields = ['date_assignation']


class WorkflowValidationSerializer(serializers.ModelSerializer):
    service_associe_detail = ServiceSerializer(source='service_associe', read_only=True)
    category_associee_detail = CategorySerializer(source='category_associee', read_only=True)
    type_courrier_display = serializers.CharField(source='get_type_courrier_display', read_only=True)
    
    class Meta:
        model = WorkflowValidation
        fields = [
            'id', 'nom', 'description', 'type_courrier', 'type_courrier_display',
            'service_associe', 'service_associe_detail', 'category_associee',
            'category_associee_detail', 'etapes_validation', 'actif',
            'date_creation', 'date_modification'
        ]
        read_only_fields = ['date_creation', 'date_modification']


class CourrierTraitementDetailSerializer(serializers.ModelSerializer):
    """Serializer pour les détails du traitement d'un courrier"""
    agent_traitant_detail = UserSerializer(source='agent_traitant', read_only=True)
    traitement_statut_display = serializers.CharField(source='get_traitement_statut_display', read_only=True)
    
    # Relations pour le traitement
    traitement_etapes = TraitementEtapeSerializer(many=True, read_only=True)
    validations = ValidationCourrierSerializer(many=True, read_only=True)
    reponses = CourrierReponseSerializer(many=True, read_only=True, source='reponses_associees')
    instructions = InstructionCourrierSerializer(many=True, read_only=True)
    
    # Calculs
    delai_restant = serializers.SerializerMethodField()
    est_en_retard_traitement = serializers.SerializerMethodField()
    progression_traitement = serializers.SerializerMethodField()
    
    class Meta:
        model = Courrier
        fields = [
            'id', 'reference', 'objet', 'traitement_statut', 'traitement_statut_display',
            'date_debut_traitement', 'date_fin_traitement', 'delai_traitement_jours',
            'agent_traitant', 'agent_traitant_detail', 'niveau_validation_requis',
            'niveau_validation_atteint', 'besoin_validation', 'reponse_associee',
            'delai_restant', 'est_en_retard_traitement', 'progression_traitement',
            'traitement_etapes', 'validations', 'reponses', 'instructions'
        ]
    

    def get_delai_restant(self, obj):
        if obj.date_debut_traitement and obj.delai_traitement_jours:
            date_fin_prevue = obj.date_debut_traitement + timedelta(days=obj.delai_traitement_jours)
            if date_fin_prevue > timezone.now():
                return (date_fin_prevue - timezone.now()).days
        return 0
    
    def get_est_en_retard_traitement(self, obj):
        if obj.date_debut_traitement and obj.delai_traitement_jours:
            date_fin_prevue = obj.date_debut_traitement + timedelta(days=obj.delai_traitement_jours)
            return date_fin_prevue < timezone.now()
        return False
    
    def get_progression_traitement(self, obj):
        """Calcule la progression du traitement en pourcentage"""
        total_etapes = obj.traitement_etapes.count()
        etapes_terminees = obj.traitement_etapes.filter(statut='termine').count()
        
        if total_etapes > 0:
            return int((etapes_terminees / total_etapes) * 100)
        
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
        
        return progression_map.get(obj.traitement_statut, 0)

class TraitementEtapeSerializer(serializers.ModelSerializer):
    agent_detail = UserSerializer(source='agent', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    type_etape_display = serializers.CharField(source='get_type_etape_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    
    class Meta:
        model = TraitementEtape
        fields = '__all__'
        read_only_fields = ['date_debut']


class ValidationCourrierSerializer(serializers.ModelSerializer):
    validateur_detail = UserSerializer(source='validateur', read_only=True)
    courrier_reference = serializers.CharField(source='courrier.reference', read_only=True)
    type_validation_display = serializers.CharField(source='get_type_validation_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    
    class Meta:
        model = ValidationCourrier
        fields = '__all__'
        read_only_fields = ['date_demande']


class CourrierReponseSerializer(serializers.ModelSerializer):
    redacteur_detail = UserSerializer(source='redacteur', read_only=True)
    validateur_detail = UserSerializer(source='validateur', read_only=True)
    signataire_detail = UserSerializer(source='signataire', read_only=True)
    courrier_origine_reference = serializers.CharField(source='courrier_origine.reference', read_only=True)
    type_reponse_display = serializers.CharField(source='get_type_reponse_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    canal_envoi_display = serializers.CharField(source='get_canal_envoi_display', read_only=True)
    
    class Meta:
        model = CourrierReponse
        fields = '__all__'
        read_only_fields = ['date_redaction', 'reference']


class CourrierTraitementSerializer(serializers.ModelSerializer):
    """Serializer spécial pour le traitement"""
    agent_traitant_detail = UserSerializer(source='agent_traitant', read_only=True)
    traitement_statut_display = serializers.CharField(source='get_traitement_statut_display', read_only=True)
    progression = serializers.SerializerMethodField()
    delai_restant = serializers.SerializerMethodField()
    est_en_retard = serializers.SerializerMethodField()
    
    class Meta:
        model = Courrier
        fields = [
            'id', 'reference', 'objet', 'expediteur_nom', 'date_reception',
            'traitement_statut', 'traitement_statut_display', 'agent_traitant',
            'agent_traitant_detail', 'date_debut_traitement', 'date_fin_traitement',
            'delai_traitement_jours', 'progression', 'delai_restant', 'est_en_retard',
            'priorite', 'service_impute', 'service_actuel'
        ]
    
    def get_progression(self, obj):
        """Calcule la progression du traitement"""
        etapes_total = obj.traitement_etapes.count()
        etapes_terminees = obj.traitement_etapes.filter(statut='termine').count()
        
        if etapes_total > 0:
            return int((etapes_terminees / etapes_total) * 100)
        
        # Basé sur le statut
        progression_map = {
            'prise_en_charge': 10,
            'analyse': 25,
            'instruction': 40,
            'redaction': 60,
            'validation': 75,
            'signature': 85,
            'envoi': 95,
            'cloture': 100,
        }
        
        return progression_map.get(obj.traitement_statut, 0)
    
    def get_delai_restant(self, obj):
        """Calcule le délai restant"""
        if obj.date_debut_traitement and obj.delai_traitement_jours:
            date_fin = obj.date_debut_traitement + timezone.timedelta(days=obj.delai_traitement_jours)
            delai = date_fin - timezone.now()
            return max(0, delai.days)
        return None
    
    def get_est_en_retard(self, obj):
        """Vérifie si le traitement est en retard"""
        if obj.date_debut_traitement and obj.delai_traitement_jours:
            date_fin = obj.date_debut_traitement + timezone.timedelta(days=obj.delai_traitement_jours)
            return date_fin < timezone.now()
        return False

class CourrierPriseEnChargeSerializer(serializers.Serializer):
    """Serializer pour la prise en charge d'un courrier"""
    commentaire = serializers.CharField(required=False, allow_blank=True)
    delai_jours = serializers.IntegerField(min_value=1, max_value=30, default=5)
    
    def validate(self, data):
        return data


class RedactionReponseSerializer(serializers.Serializer):
    """Serializer pour la rédaction d'une réponse"""
    type_reponse = serializers.ChoiceField(choices=CourrierReponse.TYPE_REPONSE_CHOICES)
    objet = serializers.CharField(max_length=500)
    contenu = serializers.CharField()
    destinataires = serializers.JSONField()
    copies = serializers.JSONField(required=False, default=list)
    modele_id = serializers.IntegerField(required=False, allow_null=True)
    pieces_jointes = serializers.JSONField(required=False, default=list)
    canal_envoi = serializers.ChoiceField(choices=CourrierReponse._meta.get_field('canal_envoi').choices)
    
    def validate(self, data):
        # Vérifier que les destinataires sont au bon format
        if not isinstance(data.get('destinataires'), list):
            raise serializers.ValidationError({"destinataires": "Doit être une liste"})
        return data


class ValidationActionSerializer(serializers.Serializer):
    """Serializer pour les actions de validation"""
    action = serializers.ChoiceField(choices=['valider', 'rejeter', 'modifier'])
    commentaire = serializers.CharField(required=False, allow_blank=True)
    modifications_requises = serializers.JSONField(required=False, default=dict)
    
    def validate(self, data):
        if data['action'] == 'modifier' and not data.get('modifications_requises'):
            raise serializers.ValidationError({
                "modifications_requises": "Requis pour l'action 'modifier'"
            })
        return data


class TimelineTraitementSerializer(serializers.Serializer):
    """Serializer pour la timeline du traitement"""
    type = serializers.CharField()  # 'etape', 'validation', 'instruction', 'reponse'
    date = serializers.DateTimeField()
    titre = serializers.CharField()
    description = serializers.CharField()
    auteur = serializers.DictField(required=False)
    statut = serializers.CharField(required=False)
    details = serializers.DictField(required=False)

class AnalyseCourrierSerializer(serializers.Serializer):
    """Serializer pour l'analyse d'un courrier"""
    analyse_notes = serializers.CharField(required=False, allow_blank=True)
    actions_requises = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    documents_necessaires = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    consultations = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )
    decision_preliminaire = serializers.CharField(required=False, allow_blank=True)
    prochaine_etape = serializers.ChoiceField(
        choices=['instruction', 'redaction', 'consultation', 'attente'],
        default='instruction'
    )