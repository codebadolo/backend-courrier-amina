import os
import logging
from datetime import datetime
from .file_storage import text_storage

logger = logging.getLogger(__name__)

class OCRService:
    """Service OCR amélioré avec stockage de fichiers"""
    
    def __init__(self, ocr_processor):
        self.ocr_processor = ocr_processor
        self.extracteur = extracteur_ocr  # Depuis extraction_ocr.py
    
    def process_document_with_storage(self, file_path, courrier=None, metadata=None):
        """
        Traite un document avec OCR et stocke le texte extrait
        
        Args:
            file_path (str): Chemin du fichier
            courrier (Courrier): Objet courrier (optionnel)
            metadata (dict): Métadonnées supplémentaires
            
        Returns:
            tuple: (texte_extrait, info_fichier)
        """
        try:
            # 1. Extraction OCR
            extracted_text = self.ocr_processor.process_ocr(file_path, courrier)
            
            if not extracted_text or not extracted_text.strip():
                logger.warning("Aucun texte extrait du document")
                return None, None
            
            # 2. Extraction d'informations structurées
            structured_info = self.extracteur.extraire_toutes_informations(extracted_text)
            
            # 3. Préparer les métadonnées
            file_metadata = {
                "source_file": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path),
                "extraction_date": datetime.now().isoformat(),
                "ocr_engine": "Tesseract",
                "language": "fra+eng",
                **structured_info
            }
            
            # Ajouter les métadonnées du courrier si disponibles
            if courrier:
                file_metadata.update({
                    "courrier_id": courrier.id,
                    "courrier_reference": courrier.reference,
                    "objet": courrier.objet,
                    "expediteur": courrier.expediteur_nom,
                    "service": str(courrier.service_impute) if courrier.service_impute else None
                })
            
            if metadata:
                file_metadata.update(metadata)
            
            # 4. Stocker dans un fichier texte
            file_info = text_storage.save_extracted_text(
                text=extracted_text,
                metadata=file_metadata,
                courrier_id=courrier.id if courrier else None,
                reference=courrier.reference if courrier else None
            )
            
            logger.info(f"OCR terminé - Texte stocké dans: {file_info['path'] if file_info else 'N/A'}")
            
            return extracted_text, file_info
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement OCR avec stockage: {str(e)}")
            raise
    
    def extract_and_analyze(self, file_path):
        """Extrait le texte et analyse le document (pour l'IA)"""
        try:
            # Extraire le texte
            extracted_text = self.ocr_processor.process_ocr(file_path, None)
            
            # Stocker temporairement pour analyse IA
            if extracted_text:
                metadata = {
                    "analysis_type": "ai_classification",
                    "status": "pending_analysis"
                }
                
                _, file_info = text_storage.save_extracted_text(
                    text=extracted_text,
                    metadata=metadata
                )
                
                # Extraire les informations structurées
                structured_info = self.extracteur.extraire_toutes_informations(extracted_text)
                structured_info["text_file_path"] = file_info["path"] if file_info else None
                
                return extracted_text, structured_info
            
            return None, None
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction pour analyse IA: {str(e)}")
            return None, None