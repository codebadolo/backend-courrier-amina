# scripts/assign_agents_to_services.py
import os
import django
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'votre_projet.settings')
django.setup()

from users.models import User
from core.models import Service

def assign_agents_to_services():
    """
    Script pour assigner les agents de service existants à des services
    """
    # Récupérer tous les agents sans service
    agents = User.objects.filter(
        role='agent_service',
        service__isnull=True,
        actif=True
    )
    
    # Assigner chaque agent au premier service disponible
    for agent in agents:
        # Trouver un service sans chef (ou avec le moins de membres)
        service = Service.objects.annotate(
            num_members=Count('membres')
        ).order_by('num_members').first()
        
        if service:
            agent.service = service
            agent.save()
            print(f"✅ Agent {agent.email} assigné au service {service.nom}")
        else:
            print(f"❌ Aucun service disponible pour {agent.email}")

if __name__ == "__main__":
    assign_agents_to_services()