from rest_framework import serializers
from .models import Service, Category, ClassificationRule, AuditLog

from users.models import User


class MiniUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "prenom", "nom", "email"]
        read_only_fields = fields


class ServiceSerializer(serializers.ModelSerializer):
    chef_detail = MiniUserSerializer(source="chef", read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "nom",
            "description",
            "chef",          # ID du chef → pour l'édition
            "chef_detail",   # Détails du chef → pour l'affichage
            "created_at",
        ]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description", "created_at"]


class ClassificationRuleSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.nom", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ClassificationRule
        fields = [
            "id",
            "keyword",
            "service", "service_name",
            "category", "category_name",
            "priority",
            "active"
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user", "user_email",
            "action",
            "timestamp",
            "metadata"
        ]
        read_only_fields = ["timestamp"]


# core/serializers.py - Ajouter cette classe
class ServiceStatsSerializer(serializers.ModelSerializer):
    """Serializer pour les statistiques d'un service"""
    nombre_membres = serializers.SerializerMethodField()
    nombre_courriers_actifs = serializers.SerializerMethodField()
    nombre_courriers_en_retard = serializers.SerializerMethodField()
    chef_nom_complet = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            "id", "nom", "description", "chef", "created_at",
            "nombre_membres", "nombre_courriers_actifs",
            "nombre_courriers_en_retard", "chef_nom_complet"
        ]
    
    def get_nombre_membres(self, obj):
        return obj.membres.count()
    
    def get_nombre_courriers_actifs(self, obj):
        from courriers.models import Courrier
        return Courrier.objects.filter(
            service_impute=obj,
            archived=False,
            statut__in=['recu', 'impute', 'traitement']
        ).count()
    
    def get_nombre_courriers_en_retard(self, obj):
        from courriers.models import Courrier
        from django.utils import timezone
        return Courrier.objects.filter(
            service_impute=obj,
            archived=False,
            date_echeance__lt=timezone.now().date(),
            statut__in=['recu', 'impute', 'traitement']
        ).count()
    
    def get_chef_nom_complet(self, obj):
        if obj.chef:
            return f"{obj.chef.prenom} {obj.chef.nom}"
        return None