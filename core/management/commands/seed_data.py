# core/management/commands/load_initial_data.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Service, Category, Courrier
from django.db import transaction

User = get_user_model()

class Command(BaseCommand):
    help = "Load initial demo data into the database."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("⚠️ Resetting existing data..."))

        # Supprime les courriers, services et catégories existants
        Courrier.objects.all().delete()
        Service.objects.all().delete()
        Category.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()  # garde le superuser si nécessaire

        self.stdout.write(self.style.WARNING("Loading initial data..."))

        # --- USERS ---
        self.stdout.write("Creating users...")
        users_data = [
            {"username": "admin", "email": "admin@example.com", "is_staff": True, "is_superuser": True, "password": "admin123"},
            {"username": "john", "email": "john@example.com", "is_staff": False, "password": "pass123"},
            {"username": "mary", "email": "mary@example.com", "is_staff": False, "password": "pass123"},
        ]

        created_users = []
        for u in users_data:
            user, created = User.objects.get_or_create(
                username=u["username"],
                defaults={
                    "email": u["email"],
                    "is_staff": u.get("is_staff", False),
                    "is_superuser": u.get("is_superuser", False),
                }
            )
            user.set_password(u["password"])
            user.save()
            created_users.append(user)

        self.stdout.write(self.style.SUCCESS(f"✔ {len(created_users)} users created."))

        # --- SERVICES ---
        self.stdout.write("Creating services...")
        services_data = [
            {"name": "Informatique", "description": "Service IT & support"},
            {"name": "Finances", "description": "Gestion financière"},
            {"name": "Ressources humaines", "description": "RH & gestion du personnel"},
        ]

        services = []
        for s in services_data:
            service, _ = Service.objects.get_or_create(name=s["name"], defaults={"description": s["description"]})
            services.append(service)

        self.stdout.write(self.style.SUCCESS(f"✔ {len(services)} services created."))

        # --- CATEGORIES ---
        self.stdout.write("Creating categories...")
        categories_data = [
            {"name": "Réclamation"},
            {"name": "Demande Administrative"},
            {"name": "Transmission"},
        ]

        categories = []
        for c in categories_data:
            category, _ = Category.objects.get_or_create(name=c["name"])
            categories.append(category)

        self.stdout.write(self.style.SUCCESS(f"✔ {len(categories)} categories created."))

        # --- COURRIERS ---
        self.stdout.write("Creating courriers...")
        courriers_data = [
            {
                "title": "Demande de matériel",
                "content": "Besoin d’un ordinateur portable.",
                "sender": created_users[1],
                "service": services[0],
                "category": categories[1],
            },
            {
                "title": "Plainte sur une erreur de paiement",
                "content": "Je souhaite signaler une erreur dans mon salaire.",
                "sender": created_users[2],
                "service": services[1],
                "category": categories[0],
            },
        ]

        for c in courriers_data:
            Courrier.objects.get_or_create(
                title=c["title"],
                defaults={
                    "content": c["content"],
                    "sender": c["sender"],
                    "service": c["service"],
                    "category": c["category"],
                }
            )

        self.stdout.write(self.style.SUCCESS(f"✔ {len(courriers_data)} courriers created."))

        self.stdout.write(self.style.SUCCESS("🎉 Initial data successfully loaded!"))
