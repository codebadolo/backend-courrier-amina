from django.db import models
from django.conf import settings


class Service(models.Model):
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    chef = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='services_diriges')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_service'
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.nom


class Category(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_category'
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.name


class ClassificationRule(models.Model):
    keyword = models.CharField(max_length=200)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    priority = models.IntegerField(default=1)  # plus c'est petit plus la règle est prioritaire
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'core_classification_rule'
        verbose_name = "Règle de classification"
        verbose_name_plural = "Règles de classification"
        indexes = [models.Index(fields=['keyword']), models.Index(fields=['priority'])]

    def __str__(self):
        return f"{self.keyword} -> {self.service.nom}"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'core_auditlog'
        verbose_name = "Audit"
        verbose_name_plural = "Logs d'audit"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.action}"
