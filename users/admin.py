from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Role, Permission, RolePermission


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("nom", "description", "created_at")
    search_fields = ("nom",)
    ordering = ("nom",)

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "description", "created_at")
    search_fields = ("nom", "code")
    ordering = ("nom",)

@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    list_filter = ("role",)
    search_fields = ("role__nom", "permission__code")


class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "nom", "prenom", "role", "service", "actif", "is_staff")
    list_filter = ("role", "service", "actif", "is_staff")
    search_fields = ("email", "nom", "prenom")

    fieldsets = (
        ("Informations personnelles", {
            "fields": ("email", "password", "nom", "prenom", "role", "service"),
        }),
        ("Permissions", {
            "fields": ("is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("État", {
            "fields": ("actif",),
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "nom", "prenom", "password1", "password2", "role", "service"),
        }),
    )

    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")


admin.site.register(User, UserAdmin)
