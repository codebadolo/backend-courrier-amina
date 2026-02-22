from django.contrib import admin
from .models import Courrier, PieceJointe, Imputation, ActionHistorique


class PieceJointeInline(admin.TabularInline):
    model = PieceJointe
    extra = 0


class ImputationInline(admin.TabularInline):
    model = Imputation
    extra = 0


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = ("reference", "type", "statut", "service_impute", "created_at")
    list_filter = ("type", "statut", "service_impute", "category")
    search_fields = ("reference", "objet", "expediteur_nom")
    inlines = [PieceJointeInline, ImputationInline]
    ordering = ("-created_at",)


@admin.register(PieceJointe)
class PieceJointeAdmin(admin.ModelAdmin):
    list_display = ("courrier", "description", "uploaded_by", "uploaded_at")
    search_fields = ("courrier__reference", "description")


@admin.register(Imputation)
class ImputationAdmin(admin.ModelAdmin):
    list_display = ("courrier", "service", "responsable", "suggestion_ia", "date_imputation")
    list_filter = ("service", "responsable", "suggestion_ia")
    search_fields = ("courrier__reference", "service__nom")


@admin.register(ActionHistorique)
class ActionHistoriqueAdmin(admin.ModelAdmin):
    list_display = ("courrier", "user", "action", "date")
    list_filter = ("action", "date")
    search_fields = ("courrier__reference", "user__email", "action")
