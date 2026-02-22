from django.contrib import admin
from .models import Workflow, WorkflowStep, WorkflowAction


class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 0


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("courrier", "current_step", "created_at")
    ordering = ("-created_at",)
    inlines = [WorkflowStepInline]


class WorkflowActionInline(admin.TabularInline):
    model = WorkflowAction
    extra = 0


@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ("workflow", "step_number", "label", "statut", "validator", "approbateur_service")
    list_filter = ("statut", "validator", "approbateur_service")
    search_fields = ("workflow__courrier__reference", "label")
    inlines = [WorkflowActionInline]


@admin.register(WorkflowAction)
class WorkflowActionAdmin(admin.ModelAdmin):
    list_display = ("step", "user", "action", "date")
    list_filter = ("action", "date")
    search_fields = ("step__workflow__courrier__reference", "user__email")
    ordering = ("-date",)
