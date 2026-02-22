# workflow/services/gemini_base.py
import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class GeminiService:
    """
    Service de base pour appeler l'API Gemini - Version simplifiée avec modèles disponibles
    """
    
    def __init__(self):
        self.api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not self.api_key:
            logger.error("CLÉ API GEMINI NON CONFIGURÉE !")
            raise ValueError("La clé API Gemini n'est pas configurée.")
        
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        
        # Modèles disponibles dans l'API actuelle
        # Voir: https://ai.google.dev/models/gemini
        self.models_to_try = [
            "gemini-2.0-flash-exp", 
            "gemini-2.5-flash-exp",
            "gemini-pro",                # Modèle legacy
        ]
    
    def generate_content(self, prompt, model_name=None):
        """
        Génère du contenu avec Gemini - Version robuste avec essai de plusieurs modèles
        """
        if model_name:
            models_to_try = [model_name]
        else:
            models_to_try = self.models_to_try
        
        for model in models_to_try:
            try:
                result = self._call_gemini_api(prompt, model)
                if result.get("success"):
                    result["model_used"] = model
                    logger.info(f"Succès avec modèle: {model}")
                    return result
                else:
                    logger.warning(f"Modèle {model} échoué: {result.get('error')}")
            except Exception as e:
                logger.warning(f"Erreur avec modèle {model}: {str(e)}")
        
        # Aucun modèle n'a fonctionné
        return {
            "success": False,
            "error": "Tous les modèles Gemini ont échoué",
            "model_used": None
        }
    
    def _call_gemini_api(self, prompt, model):
        """Appel direct à l'API Gemini"""
        try:
            url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": str(prompt)
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 4000,  # Augmenté pour les longs documents
                    "topP": 0.8,
                    "topK": 40
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    }
                ]
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if "candidates" in data and data["candidates"]:
                    candidate = data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        text = candidate["content"]["parts"][0].get("text", "")
                        
                        return {
                            "success": True,
                            "text": text.strip(),
                            "prompt_tokens": data.get("usageMetadata", {}).get("promptTokenCount", 0),
                            "total_tokens": data.get("usageMetadata", {}).get("totalTokenCount", 0)
                        }
                
                return {
                    "success": False,
                    "error": "Structure de réponse invalide"
                }
            else:
                error_msg = f"Erreur API Gemini: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except:
                    pass
                
                # Si le modèle n'est pas trouvé, c'est une erreur spécifique
                if "not found" in error_msg.lower() or "not supported" in error_msg.lower():
                    raise ValueError(f"Modèle {model} non disponible")
                
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
                }
                
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": f"Timeout avec modèle {model}"
            }
        except ValueError as ve:
            raise ve
        except Exception as e:
            return {
                "success": False,
                "error": f"Exception: {str(e)}"
            }