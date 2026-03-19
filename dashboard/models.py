from django.db import models


class RapportStatistique(models.Model):
    titre = models.CharField(max_length=255)
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    data = models.JSONField(default=dict)  # structure libre pour charts / métriques
    created_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.CharField(max_length=255, blank=True, null=True)  # nom de l'utilisateur ou service

    class Meta:
        db_table = 'dashboard_rapport'
        verbose_name = "Rapport statistique"
        verbose_name_plural = "Rapports statistiques"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.titre} ({self.periode_debut} → {self.periode_fin})"