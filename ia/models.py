from django.db import models
from django.conf import settings
from courriers.models import Courrier
from core.models import Category, Service


class IAResult(models.Model):
    courrier = models.OneToOneField(Courrier, on_delete=models.CASCADE, related_name='ia_result')
    texte_extrait = models.TextField(blank=True, null=True)
    categorie_predite = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    service_suggere = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    fiabilite = models.FloatField(default=0.0)  # 0.0 -> 1.0
    meta = models.JSONField(default=dict, blank=True)  # stockage des scores, tokens, highlights...
    processed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ia_result'
        verbose_name = "Résultat IA"
        verbose_name_plural = "Résultats IA"

    def __str__(self):
        return f"IA - {self.courrier.reference} ({self.fiabilite:.2f})"
