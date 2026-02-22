from django.contrib import admin
from .models import RapportStatistique


@admin.register(RapportStatistique)
class RapportAdmin(admin.ModelAdmin):
    list_display = ("titre", "periode_debut", "periode_fin", "created_at", "generated_by")
    search_fields = ("titre", "generated_by")
    list_filter = ("periode_debut", "periode_fin")
    ordering = ("-created_at",)
