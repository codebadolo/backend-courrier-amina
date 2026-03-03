import os
import io
import logging
import google.generativeai as genai
from pdf2image import convert_from_bytes
from django.conf import settings

logger = logging.getLogger(__name__)

class GeminiOCR:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Utiliser un modèle plus stable
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def extraire_texte(self, fichier_bytes, mime_type, nom_fichier=""):
        """
        Extrait le texte d'un fichier (PDF ou image) via Gemini.
        Retourne le texte complet.
        """
        try:
            if mime_type == 'application/pdf':
                # Convertir le PDF en images
                images = convert_from_bytes(fichier_bytes, dpi=200)
                texte_complet = ""
                for i, img in enumerate(images):
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG')
                    img_bytes = img_byte_arr.getvalue()
                    prompt = "Transcris intégralement le texte de cette page de document. Ne résume pas, ne commente pas, donne exactement le texte visible, en respectant les paragraphes et la mise en page."
                    response = self.model.generate_content([
                        prompt,
                        {"mime_type": "image/jpeg", "data": img_bytes}
                    ])
                    texte_complet += f"\n--- Page {i+1} ---\n{response.text}\n"
                return texte_complet.strip()
            else:
                # Image seule (JPEG, PNG, etc.)
                prompt = "Transcris intégralement le texte de ce document. Ne résume pas, ne commente pas, donne exactement le texte visible, en respectant les paragraphes et la mise en page."
                response = self.model.generate_content([
                    prompt,
                    {"mime_type": mime_type, "data": fichier_bytes}
                ])
                return response.text
        except Exception as e:
            logger.error(f"Erreur Gemini OCR: {str(e)}", exc_info=True)
            raise Exception(f"Erreur API Gemini: {str(e)}")