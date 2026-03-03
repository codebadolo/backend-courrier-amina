# workflow/services/gemini_courrier_service.py
import json
import logging
import re
from django.conf import settings
from .gemini_base import GeminiService
from core.models import Category, Service
from courriers.models import ActionHistorique

logger = logging.getLogger(__name__)

class CourrierGeminiService:
    """
    Service d'analyse de courrier avec Gemini AI - Version corrigée et optimisée
    """
    
    def __init__(self):
        try:
            # Initialiser le service Gemini
            self.gemini_service = GeminiService()
            logger.info("Service Gemini initialisé avec succès")
        except Exception as e:
            logger.error(f"Erreur initialisation Gemini: {e}")
            self.gemini_service = None
    
    def analyser_courrier(self, courrier):
        """
        Analyse complète d'un courrier avec Gemini
        """
        if not self.gemini_service:
            logger.error("Service Gemini non disponible")
            return self._get_fallback_analysis(courrier)
        
        try:
            # Préparer le texte du courrier
            texte_courrier = self._preparer_texte_courrier(courrier)
            
            # Construire le prompt optimisé
            prompt = self._construire_prompt_optimise(texte_courrier)
            
            # Appeler Gemini
            logger.info(f"Appel à Gemini avec prompt de {len(prompt)} caractères")
            result = self.gemini_service.generate_content(prompt)
            
            if not result.get("success"):
                logger.error(f"Erreur Gemini: {result.get('error')}")
                return self._get_fallback_analysis(courrier)
            
            # Parser la réponse
            response_text = result["text"]
            logger.debug(f"Réponse Gemini brute: {response_text[:500]}...")
            
            # Extraire le JSON de la réponse
            analyse_data = self._extraire_json_reponse(response_text)
            
            # Enrichir avec les IDs de catégorie et service
            analyse_enrichie = self._enrichir_avec_ids(analyse_data, courrier)
            
            # Ajouter le texte OCR au résultat
            if courrier.contenu_texte:
                analyse_enrichie["texte_ocr"] = courrier.contenu_texte[:1000]
            
            return analyse_enrichie
            
        except Exception as e:
            logger.error(f"Erreur analyse courrier: {e}", exc_info=True)
            return self._get_fallback_analysis(courrier)
    
    def _preparer_texte_courrier(self, courrier):
        """Prépare le texte du courrier pour l'analyse"""
        texte_parts = []
        
        if courrier.objet:
            texte_parts.append(f"OBJET: {courrier.objet}")
        
        if courrier.expediteur_nom:
            texte_parts.append(f"EXPÉDITEUR: {courrier.expediteur_nom}")
        
        if courrier.expediteur_email:
            texte_parts.append(f"EMAIL: {courrier.expediteur_email}")
        
        if courrier.expediteur_telephone:
            texte_parts.append(f"TÉLÉPHONE: {courrier.expediteur_telephone}")
        
        if courrier.expediteur_adresse:
            texte_parts.append(f"ADRESSE: {courrier.expediteur_adresse}")
        
        if courrier.date_reception:
            texte_parts.append(f"DATE: {courrier.date_reception}")
        
        if courrier.contenu_texte:
            # Limiter la taille pour éviter les tokens excessifs
            texte_contenu = courrier.contenu_texte
            if len(texte_contenu) > 5000:
                texte_contenu = texte_contenu[:2500] + " [...] " + texte_contenu[-2500:]
            texte_parts.append(f"CONTENU:\n{texte_contenu}")
        
        return "\n\n".join(texte_parts)
    
    def _construire_prompt_optimise(self, texte_courrier):
        # Récupérer les catégories et services disponibles
        try:
            categories = list(Category.objects.values_list('name', flat=True))
            services = list(Service.objects.values_list('nom', flat=True))
        except:
            categories = ["Administratif", "RH", "Finances", "Juridique", "Technique", "Commercial"]
            services = ["Secrétariat Général", "Ressources Humaines", "Finances", "Juridique", "Service Technique", "Direction Commerciale"]

        prompt = f"""Tu es un assistant expert en analyse de courriers administratifs pour une organisation africaine.
    Analyse le texte OCR ci-dessous et retourne UNIQUEMENT un JSON valide avec les informations suivantes.

    TEXTE OCR :
    {texte_courrier[:6000]}

    INSTRUCTIONS DÉTAILLÉES :
    - **objet** : Extrais l'objet principal du courrier (titre concis)
    - **expediteur** : Objet JSON avec nom, email, téléphone, adresse, organisation
    - **destinataire** : Nom du destinataire si trouvé
    - **date** : Date du document au format YYYY-MM-DD
    - **categorie_suggeree** : Parmi [{', '.join(categories)}] (choisis la plus pertinente)
    - **service_suggere** : Parmi [{', '.join(services)}] (service destinataire probable)
    - **priorite_niveau** : URGENTE, HAUTE, NORMALE, ou BASSE
    - **priorite_raison** : Brève justification (10-15 mots)
    - **confidentialite_suggestion** : CONFIDENTIELLE, RESTREINTE, ou NORMALE
    - **resume** : Résumé du document en 2-3 phrases (40-60 mots)
    - **mots_cles** : Liste de 5-8 mots-clés pertinents
    - **references** : Liste des références trouvées (numéros de dossier, etc.)
    - **confiance_categorie** : Score entre 0 et 1
    - **confiance_service** : Score entre 0 et 1
    - **type_courrier** : "demande", "plainte", "information", "facture", "contrat", "autre"

    FORMAT DE RÉPONSE (JSON strict, sans texte avant/après) :
    {{
        "objet": "...",
        "expediteur": {{
            "nom": "...",
            "email": "...",
            "telephone": "...",
            "adresse": "...",
            "organisation": "..."
        }},
        "destinataire": "...",
        "date": "YYYY-MM-DD",
        "categorie_suggeree": "...",
        "service_suggere": "...",
        "priorite_niveau": "...",
        "priorite_raison": "...",
        "confidentialite_suggestion": "...",
        "resume": "...",
        "mots_cles": ["...", "..."],
        "references": ["...", "..."],
        "confiance_categorie": 0.0,
        "confiance_service": 0.0,
        "type_courrier": "..."
    }}

    RÈGLES IMPORTANTES :
    - Utilise EXACTEMENT les catégories et services listés
    - Si une info n'existe pas, mets une chaîne vide ou null
    - Pour les scores de confiance, sois honnête (0.3 si incertain, 0.9 si très sûr)
    - Le JSON doit être valide et complet
    - Ne mets AUCUN texte avant ou après le JSON
    """
        return prompt
    
    def _extraire_json_reponse(self, response_text):
        """Extrait et parse le JSON de la réponse Gemini"""
        try:
            # Nettoyer la réponse
            cleaned = response_text.strip()
            
            # Retirer les balises de code markdown
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            cleaned = cleaned.strip()
            
            # Chercher le JSON avec regex
            json_pattern = r'\{[\s\S]*\}'
            match = re.search(json_pattern, cleaned, re.DOTALL)
            
            if match:
                json_str = match.group()
                return json.loads(json_str)
            else:
                # Essayer de parser directement
                return json.loads(cleaned)
                
        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON: {e}")
            logger.debug(f"Texte problématique: {response_text[:500]}")
            
            # Essayer de réparer le JSON
            return self._reparer_json(cleaned)
        except Exception as e:
            logger.error(f"Erreur extraction JSON: {e}")
            return self._get_structure_par_defaut()
    
    def _reparer_json(self, json_str):
        """Tente de réparer un JSON malformé"""
        try:
            # Nettoyer les caractères problématiques
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            json_str = re.sub(r'\\\'', "'", json_str)
            
            # Compter les guillemets et ajouter si nécessaire
            quotes_count = json_str.count('"')
            if quotes_count % 2 != 0:
                json_str += '"'
            
            return json.loads(json_str)
        except:
            return self._get_structure_par_defaut()
    
    def _enrichir_avec_ids(self, analyse_data, courrier):
        """Ajoute les IDs de catégorie et service basés sur les noms"""
        try:
            # Chercher la catégorie
            categorie_nom = analyse_data.get("classification", {}).get("categorie_suggeree", "")
            if categorie_nom:
                categorie = Category.objects.filter(
                    nom__icontains=categorie_nom
                ).first()
                if categorie:
                    analyse_data["classification"]["categorie_id"] = categorie.id
            
            # Chercher le service
            service_nom = analyse_data.get("classification", {}).get("service_suggere", "")
            if service_nom:
                service = Service.objects.filter(
                    nom__icontains=service_nom
                ).first()
                if service:
                    analyse_data["classification"]["service_id"] = service.id
            
            return analyse_data
        except Exception as e:
            logger.error(f"Erreur enrichissement IDs: {e}")
            return analyse_data
    
    def _get_fallback_analysis(self, courrier):
        """Analyse de fallback quand Gemini n'est pas disponible"""
        logger.info("Utilisation de l'analyse de fallback")
        
        from .classifier import classifier_courrier
        result = classifier_courrier(courrier)
        
        # Construire la structure attendue
        return {
            "classification": {
                "categorie_suggeree": result.get('category', 'ADMINISTRATIF'),
                "service_suggere": result.get('service_impute', 'Secrétariat Général'),
                "confiance_categorie": result.get('confidence', 0.3),
                "confiance_service": result.get('confidence', 0.3),
                "categorie_id": result.get('category_id', None),
                "service_id": result.get('service_id', None)
            },
            "priorite": {
                "niveau": result.get('priorite', 'NORMALE'),
                "raison": "Analyse locale (Gemini indisponible)",
                "confiance": 0.5
            },
            "confidentialite_suggestion": "NORMALE",
            "analyse": {
                "resume": "Document analysé avec le système de fallback",
                "mots_cles": ["document", "administratif"]
            },
            "expediteur": {
                "nom": courrier.expediteur_nom or "",
                "email": courrier.expediteur_email or "",
                "telephone": courrier.expediteur_telephone or "",
                "adresse": courrier.expediteur_adresse or ""
            },
            "objet": courrier.objet or "Document analysé",
            "ia_disponible": False
        }
    
    def _get_structure_par_defaut(self):
        """Structure par défaut en cas d'erreur critique"""
        return {
            "classification": {
                "categorie_suggeree": "ADMINISTRATIF",
                "service_suggere": "Secrétariat Général",
                "confiance_categorie": 0.3,
                "confiance_service": 0.3,
                "categorie_id": None,
                "service_id": None
            },
            "priorite": {
                "niveau": "NORMALE",
                "raison": "Erreur d'analyse IA",
                "confiance": 0.1
            },
            "confidentialite_suggestion": "NORMALE",
            "analyse": {
                "resume": "L'analyse IA a rencontré une erreur",
                "mots_cles": ["erreur", "analyse"]
            },
            "expediteur": {},
            "objet": "Document analysé",
            "ia_disponible": False
        }

# Instance globale
gemini_courrier_service = CourrierGeminiService()