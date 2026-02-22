from django.db import models
from django.conf import settings
from core.models import Category, Service
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
import uuid



class TypeCourrier(models.TextChoices):
    ENTRANT = 'entrant', 'Entrant'
    SORTANT = 'sortant', 'Sortant'
    INTERNE = 'interne', 'Interne'


class StatusCourrier(models.TextChoices):
    RECU = 'recu', 'Reçu'
    IMPUTE = 'impute', 'Imputé'
    TRAITEMENT = 'traitement', 'En traitement'
    REPONDU = 'repondu', 'Répondu'
    ARCHIVE = 'archive', 'Archivé'

class PriorityLevel(models.TextChoices):
    BASSE = 'basse', 'Basse'
    NORMALE = 'normale', 'Normale'
    HAUTE = 'haute', 'Haute'
    URGENTE = 'urgente', 'Urgente'

# Ajoutez cette classe avec les autres choix (après PriorityLevel par exemple)

# Après les autres choix (TypeCourrier, StatusCourrier, etc.)
class TraitementStatus(models.TextChoices):
    PRISE_EN_CHARGE = 'prise_en_charge', 'Prise en charge'
    ANALYSE = 'analyse', 'Analyse en cours'
    INSTRUCTION = 'instruction', 'Instruction'
    REDACTION = 'redaction', 'Rédaction réponse'
    VALIDATION = 'validation', 'En validation'
    SIGNATURE = 'signature', 'À signature'
    ENVOI = 'envoi', 'À envoyer'
    CLOTURE = 'cloture', 'Clôturé'
    REJETE = 'rejete', 'Rejeté'
    
class Courrier(models.Model):
    # Champs pour l'IA
    meta_analyse = models.JSONField(default=dict, blank=True, null=True)  # Stocke l'analyse Gemini
    reponse_suggeree = models.TextField(blank=True, null=True)  # Réponse suggérée par IA
    contenu_texte = models.TextField(blank=True, null=True)
    analyse_ia = models.TextField(blank=True, null=True)
    # instructions = models.JSONField(default=list, blank=True, verbose_name="Instructions")
    
    priorite = models.CharField(
        max_length=20,
        choices=[
            ('basse', 'Basse'),
            ('normale', 'Normale'),
            ('haute', 'Haute'),
            ('urgente', 'Urgente'),
        ],
        default='normale'
    )
    
    reference = models.CharField(max_length=100, unique=True, blank=True)
    type = models.CharField(max_length=20, choices=TypeCourrier.choices)

    # texte_extrait_path = models.CharField(
    #     max_length=500,
    #     blank=True,
    #     null=True,
    #     verbose_name="Chemin du fichier texte extrait"
    # )
    
    objet = models.CharField(max_length=500)
    contenu_texte = models.TextField(blank=True, null=True)  # texte extrait via OCR/IA
    
    expediteur_nom = models.CharField(max_length=255, blank=True, null=True)
    expediteur_adresse = models.TextField(blank=True, null=True)
    expediteur_email = models.EmailField(blank=True, null=True)
    expediteur_telephone = models.CharField(max_length=20, blank=True, null=True)
    destinataire_nom = models.CharField(max_length=255, blank=True, null=True)

    analyse_notes = models.TextField(blank=True, null=True, verbose_name="Notes d'analyse")
    analyse_date = models.DateTimeField(null=True, blank=True, verbose_name="Date d'analyse")
    analyse_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='courriers_analyses'
    )
    
    # Champs pour les actions à mener
    actions_requises = models.JSONField(default=list, blank=True, verbose_name="Actions requises")
    documents_necessaires = models.JSONField(default=list, blank=True, verbose_name="Documents nécessaires")
    
    # Consultation d'autres services
    consultations = models.JSONField(default=list, blank=True, verbose_name="Consultations externes")
    
    # Décision préliminaire
    decision_preliminaire = models.TextField(blank=True, null=True)

    traitement_statut = models.CharField(
        max_length=20,
        choices=TraitementStatus.choices,
        default=TraitementStatus.PRISE_EN_CHARGE
    )

    date_debut_traitement = models.DateTimeField(null=True, blank=True)
    date_fin_traitement = models.DateTimeField(null=True, blank=True)
    delai_traitement_jours = models.IntegerField(default=5)
    # Agent en charge du traitement
    agent_traitant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courriers_traitant'
    )

    # Workflow de validation
    workflow_validation = models.ForeignKey(
        'WorkflowValidation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Pour le suivi de validation
    niveau_validation_requis = models.IntegerField(default=1)
    niveau_validation_atteint = models.IntegerField(default=0)
    besoin_validation = models.BooleanField(default=False)

    # Réponse liée (pour les courriers entrants)
    reponse_associee = models.ForeignKey(
        'CourrierReponse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courrier_source'
    )
    
    # Canal de réception/émission
    CANAL_CHOICES = [
        ('physique', 'Physique'),
        ('email', 'Email'),
        ('portail', 'Portail'),
        ('telephone', 'Téléphone'),
        ('autre', 'Autre'),
    ]
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES, default='physique')
    
    # Confidentialité
    CONFIDENTIALITE_CHOICES = [
        ('normale', 'Normale'),
        ('restreinte', 'Restreinte'),
        ('confidentielle', 'Confidentielle'),
    ]
    confidentialite = models.CharField(
        max_length=20, 
        choices=CONFIDENTIALITE_CHOICES, 
        default='normale'
    )
    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    service_impute = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    
    statut = models.CharField(max_length=30, choices=StatusCourrier.choices, default=StatusCourrier.RECU)
    
    date_reception = models.DateField(null=True, blank=True)
    date_echeance = models.DateField(null=True, blank=True)
    date_envoi = models.DateField(null=True, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='courriers_crees')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    archived = models.BooleanField(default=False)
    date_archivage = models.DateField(null=True, blank=True)
    date_limite_traitement = models.DateField(null=True, blank=True)
    date_cloture = models.DateField(null=True, blank=True)
    
    qr_code = models.CharField(max_length=100, blank=True, null=True, unique=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    
    # Pour l'imputation multiple (un courrier peut passer par plusieurs services)
    service_actuel = models.ForeignKey(
        Service, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='courriers_actuels'
    )
    responsable_actuel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courriers_encours'
    )

    class Meta:
        db_table = 'courrier_courrier'
        verbose_name = "Courrier"
        verbose_name_plural = "Courriers"
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['statut']),
            models.Index(fields=['created_at']),
            models.Index(fields=['priorite']),
        ]

    def __str__(self):
        return self.reference
    
    exte_extrait_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Chemin du fichier texte extrait"
    )

    def save_text_to_file(self, text, metadata=None):
            """Méthode utilitaire pour sauvegarder le texte"""
            try:
                from workflow.services.file_storage import text_storage
                
                # Préparer les métadonnées du courrier
                courrier_metadata = {
                    "courrier_id": self.id,
                    "reference": self.reference,
                    "objet": self.objet,
                    "expediteur_nom": self.expediteur_nom,
                    "expediteur_email": self.expediteur_email,
                    "date_reception": str(self.date_reception),
                    "service_impute": str(self.service_impute) if self.service_impute else "",
                    "category": str(self.category) if self.category else "",
                    "priorite": self.priorite,
                    "confidentialite": self.confidentialite,
                    "canal": self.canal
                }
                
                # Fusionner avec les métadonnées supplémentaires
                if metadata:
                    courrier_metadata.update(metadata)
                
                # Sauvegarder le texte
                file_info = text_storage.save_extracted_text(
                    text=text,
                    metadata=courrier_metadata,
                    courrier_id=self.id,
                    reference=self.reference
                )
                
                if file_info:
                    self.texte_extrait_path = file_info['path']
                    self.save(update_fields=['texte_extrait_path'])
                    return file_info
                
                return None
                
            except Exception as e:
                print(f"Erreur save_text_to_file: {str(e)}")
                return None
        


class PieceJointe(models.Model):
    courrier = models.ForeignKey(Courrier, on_delete=models.CASCADE, related_name='pieces_jointes')
    fichier = models.FileField(upload_to='courriers/pieces/')
    description = models.CharField(max_length=255, blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'courrier_piecejointe'
        verbose_name = "Pièce jointe"
        verbose_name_plural = "Pièces jointes"

    def __str__(self):
        return f"PJ - {self.courrier.reference}"


class Imputation(models.Model):
    courrier = models.ForeignKey(Courrier, on_delete=models.CASCADE, related_name='imputations')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    commentaire = models.TextField(blank=True, null=True)
    suggestion_ia = models.BooleanField(default=False)
    score_ia = models.FloatField(null=True, blank=True)  # confiance de la suggestion IA
    date_imputation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'courrier_imputation'
        verbose_name = "Imputation"
        verbose_name_plural = "Imputations"

    def __str__(self):
        return f"Imputation {self.courrier.reference} -> {self.service and self.service.nom}"


class ActionHistorique(models.Model):
    courrier = models.ForeignKey(Courrier, on_delete=models.CASCADE, related_name='historiques')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    anciens_valeurs = models.TextField(blank=True, null=True)
    nouvelles_valeurs = models.TextField(blank=True, null=True)
    commentaire = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'courrier_historique'
        verbose_name = "Historique action"
        verbose_name_plural = "Historique actions"

    def __str__(self):
        return f"{self.date} - {self.action}"


# dans courriers/models.py ou créer templates/models.py

class ModeleCourrier(models.Model):
    TYPE_CHOICES = [
        ('entrant', 'Réponse à courrier entrant'),
        ('sortant', 'Courrier sortant standard'),
        ('interne', 'Note interne'),
    ]
    
    nom = models.CharField(max_length=200)
    type_modele = models.CharField(max_length=20, choices=TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    contenu = models.TextField()  # Template avec variables {{ }}
    variables = models.JSONField(default=list)  # Liste des variables disponibles
    entete = models.TextField(blank=True, null=True)
    pied_page = models.TextField(blank=True, null=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'courrier_modele'
        
    def __str__(self):
        return self.nom
    

class CourrierService:
    @staticmethod
    def get_courrier_stats(service_id):
        cache_key = f'courrier_stats_{service_id}'
        stats = cache.get(cache_key)
        if not stats:
            stats = Courrier.objects.filter(
                service_impute_id=service_id,
                date_reception__gte=timezone.now() - timedelta(days=30)
            ).aggregate(
                total=Count('id'),
                en_cours=Count('id', filter=Q(statut='traitement')),
                en_retard=Count('id', filter=Q(date_echeance__lt=timezone.now()))
            )
            cache.set(cache_key, stats, timeout=300)  # 5 minutes
        return stats
    
class TraitementStatus(models.TextChoices):
    PRISE_EN_CHARGE = 'prise_en_charge', 'Prise en charge'
    ANALYSE = 'analyse', 'Analyse en cours'
    INSTRUCTION = 'instruction', 'Instruction'
    REDACTION = 'redaction', 'Rédaction réponse'
    VALIDATION = 'validation', 'En validation'
    SIGNATURE = 'signature', 'À signature'
    ENVOI = 'envoi', 'À envoyer'
    CLOTURE = 'cloture', 'Clôturé'
    REJETE = 'rejete', 'Rejeté'


class TraitementEtape(models.Model):
    """Suivi des étapes de traitement d'un courrier"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    courrier = models.ForeignKey('Courrier', on_delete=models.CASCADE, related_name='traitement_etapes')
    
    ETAPE_TYPE_CHOICES = [
        ('prise_en_charge', 'Prise en charge'),
        ('lecture', 'Lecture et analyse'),
        ('instruction', 'Instruction du dossier'),
        ('redaction', 'Rédaction de la réponse'),
        ('avis', 'Avis technique'),
        ('validation', 'Validation hiérarchique'),
        ('signature', 'Signature'),
        ('envoi', 'Envoi/Réponse'),
        ('cloture', 'Clôture'),
        ('rejet', 'Rejet'),
        ('transfert', 'Transfert à un autre service'),
    ]
    
    type_etape = models.CharField(max_length=50, choices=ETAPE_TYPE_CHOICES)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    description = models.TextField()
    commentaire = models.TextField(blank=True, null=True)
    
    date_debut = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    duree_minutes = models.IntegerField(null=True, blank=True)
    
    STATUT_ETAPE_CHOICES = [
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('en_attente', 'En attente'),
        ('bloque', 'Bloqué'),
        ('annule', 'Annulé'),
    ]
    statut = models.CharField(max_length=20, choices=STATUT_ETAPE_CHOICES, default='en_cours')
    
    documents_associes = models.JSONField(default=list, blank=True)  # Liste des documents liés
    
    # Pour les validations
    validation_requise = models.BooleanField(default=False)
    validateurs = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='validations_a_realiser', blank=True)
    
    class Meta:
        db_table = 'courrier_traitement_etape'
        verbose_name = "Étape de traitement"
        verbose_name_plural = "Étapes de traitement"
        ordering = ['date_debut']

    def __str__(self):
        return f"{self.get_type_etape_display()} - {self.courrier.reference}"


class ValidationCourrier(models.Model):
    """Modèle pour gérer les validations hiérarchiques"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    courrier = models.ForeignKey('Courrier', on_delete=models.CASCADE, related_name='validations')
    
    TYPE_VALIDATION_CHOICES = [
        ('technique', 'Validation technique'),
        ('hierarchique', 'Validation hiérarchique'),
        ('juridique', 'Validation juridique'),
        ('financiere', 'Validation financière'),
        ('signature', 'Signature'),
    ]
    
    type_validation = models.CharField(max_length=50, choices=TYPE_VALIDATION_CHOICES)
    validateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Ordre de validation (1, 2, 3...)
    ordre = models.IntegerField(default=1)
    
    # Statut de la validation
    STATUT_VALIDATION_CHOICES = [
        ('en_attente', 'En attente'),
        ('valide', 'Validé'),
        ('rejete', 'Rejeté'),
        ('modification', 'Modifications requises'),
        ('signe', 'Signé'),
    ]
    statut = models.CharField(max_length=20, choices=STATUT_VALIDATION_CHOICES, default='en_attente')
    
    commentaire = models.TextField(blank=True, null=True)
    date_demande = models.DateTimeField(auto_now_add=True)
    date_action = models.DateTimeField(null=True, blank=True)
    
    # Pour la signature électronique
    signature_data = models.JSONField(null=True, blank=True)
    signature_image = models.TextField(blank=True, null=True)  # Base64 ou chemin
    certificat_info = models.JSONField(null=True, blank=True)
    
    class Meta:
        db_table = 'courrier_validation'
        verbose_name = "Validation de courrier"
        verbose_name_plural = "Validations de courrier"
        ordering = ['ordre', 'date_demande']
        unique_together = ['courrier', 'ordre']

    def __str__(self):
        return f"Validation {self.get_type_validation_display()} - {self.courrier.reference}"


class CourrierReponse(models.Model):
    """Modèle pour les réponses aux courriers entrants"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    courrier_origine = models.ForeignKey('Courrier', on_delete=models.CASCADE, related_name='reponses')
    
    TYPE_REPONSE_CHOICES = [
        ('lettre', 'Lettre officielle'),
        ('email', 'Email'),
        ('note_interne', 'Note interne'),
        ('decision', 'Décision'),
        ('avis_technique', 'Avis technique'),
        ('accuse_reception', 'Accusé de réception'),
    ]
    
    type_reponse = models.CharField(max_length=50, choices=TYPE_REPONSE_CHOICES, default='lettre')
    reference = models.CharField(max_length=100, unique=True)
    
    objet = models.CharField(max_length=500)
    contenu = models.TextField()
    
    # Utilisation d'un modèle de courrier
    modele_utilise = models.ForeignKey('ModeleCourrier', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Destinataires et copies
    destinataires = models.JSONField()  # Liste des destinataires avec leurs coordonnées
    copies = models.JSONField(default=list, blank=True)  # Liste des copies
    
    # Dates importantes
    date_redaction = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_signature = models.DateTimeField(null=True, blank=True)
    date_envoi = models.DateTimeField(null=True, blank=True)
    
    # Statut de la réponse
    STATUT_REPONSE_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('a_valider', 'À valider'),
        ('a_corriger', 'À corriger'),
        ('a_signature', 'À signature'),
        ('a_envoyer', 'À envoyer'),
        ('envoye', 'Envoyé'),
        ('archive', 'Archivé'),
    ]
    statut = models.CharField(max_length=20, choices=STATUT_REPONSE_CHOICES, default='brouillon')
    
    # Responsables
    redacteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, 
                                  related_name='reponses_redigees')
    validateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, 
                                   related_name='reponses_validees', blank=True)
    signataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, 
                                   related_name='reponses_signees', blank=True)
    
    # Documents joints
    pieces_jointes_reponse = models.JSONField(default=list, blank=True)  # Pour stocker les PJ liées à la réponse
    
    # Paramètres d'envoi
    canal_envoi = models.CharField(max_length=50, choices=[
        ('email', 'Email'),
        ('courrier', 'Courrier physique'),
        ('portail', 'Portail web'),
        ('fax', 'Fax'),
        ('messagerie', 'Messagerie interne'),
    ], default='email')
    
    # Suivi
    confirmation_reception = models.BooleanField(default=False)
    date_confirmation = models.DateTimeField(null=True, blank=True)
    
    # Template et mise en forme
    template_html = models.TextField(blank=True, null=True)
    entete = models.TextField(blank=True, null=True)
    pied_page = models.TextField(blank=True, null=True)
    signature_html = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'courrier_reponse'
        verbose_name = "Réponse de courrier"
        verbose_name_plural = "Réponses de courrier"
        ordering = ['-date_redaction']

    def __str__(self):
        return f"{self.reference} - {self.objet}"

    def save(self, *args, **kwargs):
        # Générer une référence si elle n'existe pas
        if not self.reference:
            prefix = {
                'lettre': 'LET',
                'email': 'EML',
                'note_interne': 'NOT',
                'decision': 'DEC',
                'avis_technique': 'AVI',
                'accuse_reception': 'ACC'
            }.get(self.type_reponse, 'REP')
            
            self.reference = f"{prefix}/{timezone.now().strftime('%Y%m%d')}/{uuid.uuid4().hex[:6].upper()}"
        
        super().save(*args, **kwargs)


class InstructionCourrier(models.Model):
    """Instructions pour le traitement d'un courrier"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    courrier = models.ForeignKey('Courrier', on_delete=models.CASCADE, related_name='instructions')
    
    TYPE_INSTRUCTION_CHOICES = [
        ('analyse', 'Analyse préliminaire'),
        ('recherche', 'Recherche d\'informations'),
        ('consultation', 'Consultation d\'expert'),
        ('verification', 'Vérification réglementaire'),
        ('calcul', 'Calculs nécessaires'),
        ('recommandation', 'Recommandation'),
    ]
    
    type_instruction = models.CharField(max_length=50, choices=TYPE_INSTRUCTION_CHOICES)
    instruction = models.TextField()
    
    agent_assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                       null=True, blank=True, related_name='instructions_assignees')
    
    date_assignation = models.DateTimeField(auto_now_add=True)
    date_echeance = models.DateTimeField(null=True, blank=True)
    date_accomplie = models.DateTimeField(null=True, blank=True)
    
    STATUT_INSTRUCTION_CHOICES = [
        ('en_attente', 'En attente'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('reporte', 'Reporté'),
        ('annule', 'Annulé'),
    ]
    statut = models.CharField(max_length=20, choices=STATUT_INSTRUCTION_CHOICES, default='en_attente')
    
    resultat = models.TextField(blank=True, null=True)
    documents_produits = models.JSONField(default=list, blank=True)
    
    class Meta:
        db_table = 'courrier_instruction'
        verbose_name = "Instruction de traitement"
        verbose_name_plural = "Instructions de traitement"
        ordering = ['date_assignation']

    def __str__(self):
        return f"Instruction {self.get_type_instruction_display()} - {self.courrier.reference}"


class WorkflowValidation(models.Model):
    """Configuration du workflow de validation pour un type de courrier"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    TYPE_COURRIER_CHOICES = [
        ('entrant', 'Courrier entrant'),
        ('sortant', 'Courrier sortant'),
        ('interne', 'Courrier interne'),
    ]
    type_courrier = models.CharField(max_length=20, choices=TYPE_COURRIER_CHOICES)
    
    service_associe = models.ForeignKey('core.Service', on_delete=models.CASCADE, null=True, blank=True)
    category_associee = models.ForeignKey('core.Category', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Configuration des étapes de validation
    etapes_validation = models.JSONField()  # Liste des étapes avec rôles et ordres
    
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'courrier_workflow_validation'
        verbose_name = "Workflow de validation"
        verbose_name_plural = "Workflows de validation"
        unique_together = ['nom', 'type_courrier', 'service_associe']

    def __str__(self):
        return self.nom