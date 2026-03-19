# workflow/models.py

from django.db import models
from django.conf import settings
from courriers.models import Courrier
from courriers.models import Category, TypeCourrier




class Workflow(models.Model):
    courrier = models.OneToOneField(Courrier, on_delete=models.CASCADE, related_name='workflow')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    current_step = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'workflow_workflow'
        verbose_name = "Workflow"
        verbose_name_plural = "Workflows"

    def __str__(self):
        return f"Workflow - {self.courrier.reference}"
    
class WorkflowTemplate(models.Model):
    """Modèles de workflow prédéfinis"""
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    type_courrier = models.CharField(max_length=20, choices=TypeCourrier.choices)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    active = models.BooleanField(default=True)
    # ── BUG 4 : champ manquant — référencé par views.py et serializers.py ──
    steps_config = models.JSONField(
        default=list,
        blank=True,
        help_text="Config des étapes : [{'label': 'Validation chef', 'role': 'chef', 'actions': ['valider']}, ...]"
    )
    
    class Meta:
        db_table = 'workflow_template'
        
    def __str__(self):
        return self.nom


class WorkflowStep(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField()
    label = models.CharField(max_length=200)
    validator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    approbateur_service = models.ForeignKey('core.Service', on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField(
        max_length=30,
        choices=[
            ('en_attente', 'En attente'),
            ('valide', 'Validé'),
            ('rejete', 'Rejeté'),
            ('brouillon', 'Brouillon'),
        ],
        default='en_attente'
    )
    commentaire = models.TextField(blank=True, null=True)
    date_action = models.DateTimeField(null=True, blank=True)
      # Ajouter pour les délais
    delai_attente_max = models.IntegerField(default=48)  # heures
    actions_requises = models.JSONField(default=list, blank=True)  # ["signature", "visa", "commentaire"]
    
    # Notifications
    notifier_avant_expiration = models.BooleanField(default=True)
    heures_avant_notification = models.IntegerField(default=24)

    class Meta:
        db_table = 'workflow_step'
        unique_together = ('workflow', 'step_number')
        ordering = ['step_number']

    def __str__(self):
        return f"{self.workflow.courrier.reference} - Step {self.step_number} ({self.statut})"


class WorkflowAction(models.Model):
    step = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name='actions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50, choices=[('valider', 'Valider'), ('rejeter', 'Rejeter'), ('commenter', 'Commenter')])
    commentaire = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workflow_action'
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.action}"

class Accuse(models.Model):
    TYPE_CHOICES = [
        ('reception', 'Accusé de réception'),
        ('imputation', 'Accusé d\'imputation'),
        ('traitement', 'Accusé de traitement'),
    ]
    
    courrier = models.ForeignKey(Courrier, on_delete=models.CASCADE, related_name='accuses')
    type_accuse = models.CharField(max_length=20, choices=TYPE_CHOICES)
    destinataire_email = models.EmailField()
    envoye_le = models.DateTimeField(auto_now_add=True)
    message_id = models.CharField(max_length=255, blank=True, null=True)  # Pour tracking email
    status = models.CharField(max_length=20, default='envoye')  # envoye, echec, lu
    
    class Meta:
        db_table = 'courrier_accuse'