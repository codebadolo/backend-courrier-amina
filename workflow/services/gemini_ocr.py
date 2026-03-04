import os
import io
import json
import re
import logging
import google.generativeai as genai
from pdf2image import convert_from_bytes
from django.conf import settings

logger = logging.getLogger(__name__)

class GeminiOCR:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def extraire_texte_et_infos(self, fichier_bytes, mime_type, nom_fichier=""):
        """
        Extrait le texte et les informations structurées d'un document (PDF ou image).
        Retourne un dict avec 'texte' et 'extraction'.
        """
        try:
            prompt_principal = """
Tu es un assistant expert en analyse de courriers administratifs.
Voici le contenu d'un document scanné. Ta tâche est double :
1. Transcrire intégralement le texte du document, en respectant les paragraphes et la mise en page.
2. Extraire les informations suivantes au format JSON.

Informations à extraire :
- objet : le sujet principal du courrier (chaîne)
- expediteur_nom : nom complet de l'expéditeur (chaîne, "Non spécifié" si absent)
- expediteur_email : adresse email (chaîne, "Non spécifié" si absent)
- expediteur_telephone : numéro de téléphone (chaîne, "Non spécifié" si absent)
- expediteur_adresse : adresse postale (chaîne, "Non spécifié" si absent)
- date_courrier : date du document au format YYYY-MM-DD (chaîne, "Non spécifié" si absente)
- destinataire_nom : nom du destinataire principal (chaîne, "Non spécifié" si absent)
- categorie_suggeree : parmi ["RH", "FINANCE", "JURIDIQUE", "TECHNIQUE", "COMMERCIAL", "ADMINISTRATIF"]
- priorite_niveau : parmi ["URGENTE", "HAUTE", "NORMALE", "BASSE"]
- priorite_raison : brève justification (chaîne)
- mots_cles : liste de 5 à 10 mots-clés pertinents

Format de réponse : UNIQUEMENT un objet JSON valide avec deux clés : "texte" et "extraction".
{
  "texte": "...",
  "extraction": {
    "objet": "...",
    "expediteur_nom": "...",
    "expediteur_email": "...",
    "expediteur_telephone": "...",
    "expediteur_adresse": "...",
    "date_courrier": "YYYY-MM-DD",
    "destinataire_nom": "...",
    "categorie_suggeree": "...",
    "priorite_niveau": "...",
    "priorite_raison": "...",
    "mots_cles": ["...", "..."]
  }
}
"""

            if mime_type == 'application/pdf':
                images = convert_from_bytes(fichier_bytes, dpi=200)
                if not images:
                    raise Exception("Impossible de convertir le PDF en images")

                # --- Première page : prompt complet pour obtenir le JSON ---
                img_bytes = io.BytesIO()
                images[0].save(img_bytes, format='JPEG')
                response = self.model.generate_content([
                    prompt_principal,
                    {"mime_type": "image/jpeg", "data": img_bytes.getvalue()}
                ])
                first_text = response.text

                # Extraction du JSON
                match = re.search(r'```json\n(.*?)\n```', first_text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        texte_complet = data.get("texte", "")
                        extraction = data.get("extraction", {})
                    except json.JSONDecodeError:
                        texte_complet = first_text
                        extraction = {}
                else:
                    texte_complet = first_text
                    extraction = {}

                # --- Pages suivantes : seulement la transcription ---
                for i in range(1, len(images)):
                    img_bytes = io.BytesIO()
                    images[i].save(img_bytes, format='JPEG')
                    response = self.model.generate_content([
                        "Continue la transcription de la page suivante. Ne répète pas les informations déjà extraites. Retourne uniquement le texte de cette page.",
                        {"mime_type": "image/jpeg", "data": img_bytes.getvalue()}
                    ])
                    texte_complet += f"\n--- Page {i+1} ---\n{response.text}\n"

                return {"texte": texte_complet, "extraction": extraction}

            else:
                # Image seule
                response = self.model.generate_content([
                    prompt_principal,
                    {"mime_type": mime_type, "data": fichier_bytes}
                ])
                text = response.text
                match = re.search(r'```json\n(.*?)\n```', text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        return data
                    except json.JSONDecodeError:
                        pass
                return {"texte": text, "extraction": {}}

        except Exception as e:
            logger.error(f"Erreur Gemini OCR: {str(e)}", exc_info=True)
            raise Exception(f"Erreur API Gemini: {str(e)}")