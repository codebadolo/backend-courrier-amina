# users/migrations/0003_add_agent_service_role.py
from django.db import migrations

def update_role_choices(apps, schema_editor):
    """Fonction pour forcer l'ajout du rôle dans la base si nécessaire"""
    pass  # Pas de modification SQL, juste pour la migration

def reverse_update(apps, schema_editor):
    """Rollback"""
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(update_role_choices, reverse_update),
    ]