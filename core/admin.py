from django.contrib import admin
from .models import Service, Category, ClassificationRule, AuditLog


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("nom", "chef", "created_at")
    search_fields = ("nom", "chef__email")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(ClassificationRule)
class ClassificationRuleAdmin(admin.ModelAdmin):
    list_display = ("keyword", "service", "category", "priority", "active")
    list_editable = ("priority", "active")
    search_fields = ("keyword", "service__nom", "category__name")
    list_filter = ("active", "service", "category")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = ("action", "user__email")
    ordering = ("-timestamp",)
