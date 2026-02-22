from django.contrib import admin
from .models import IAResult


@admin.register(IAResult)
class IAResultAdmin(admin.ModelAdmin):
    list_display = ("courrier", "categorie_predite", "service_suggere", "fiabilite", "processed_at")
    list_filter = ("categorie_predite", "service_suggere")
    search_fields = ("courrier__reference",)
    ordering = ("-processed_at",)
