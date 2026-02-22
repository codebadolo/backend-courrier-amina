from django.core.management.base import BaseCommand
from users.models import User, Service

class Command(BaseCommand):
    help = 'Crée les données de base : services et utilisateurs avec FK valides'

    def handle(self, *args, **options):
        # Création services sans chef
        service_rh = Service.objects.create(nom='Ressources Humaines')
        service_it = Service.objects.create(nom='Informatique')
        service_dir = Service.objects.create(nom='Direction')

        self.stdout.write(self.style.SUCCESS('Services créés'))

        # Création utilisateurs (sans service pour l’instant)
        admin = User.objects.create_superuser(
            email='admin@example.com', password='adminpass', nom='Admin', prenom='Super', role='admin'
        )
        chef_rh = User.objects.create_user(
            email='chef.rh@example.com', password='chefpass', nom='Chef', prenom='RH', role='chef'
        )
        chef_it = User.objects.create_user(
            email='chef.it@example.com', password='chefpass', nom='Chef', prenom='IT', role='chef'
        )
        directeur = User.objects.create_user(
            email='directeur@example.com', password='dirpass', nom='Directeur', prenom='Général', role='direction'
        )

        self.stdout.write(self.style.SUCCESS('Utilisateurs créés'))

        # Assigner service aux chefs et chef aux services
        chef_rh.service = service_rh
        chef_rh.save()
        service_rh.chef = chef_rh
        service_rh.save()

        chef_it.service = service_it
        chef_it.save()
        service_it.chef = chef_it
        service_it.save()

        directeur.service = service_dir
        directeur.save()
        service_dir.chef = directeur
        service_dir.save()

        self.stdout.write(self.style.SUCCESS('Relations chefs/services affectées'))

        # Création collaborateurs dans un service
        User.objects.create_user(email='collab1@example.com', password='collabpass', nom='Collab', prenom='One', role='collaborateur', service=service_rh)
        User.objects.create_user(email='collab2@example.com', password='collabpass', nom='Collab', prenom='Two', role='collaborateur', service=service_it)

        self.stdout.write(self.style.SUCCESS('Collaborateurs créés et affectés'))

        self.stdout.write(self.style.SUCCESS('Initialisation terminée avec succès'))

