# workflow/services/file_storage.py
import os
import uuid
from datetime import datetime
import logging
from pathlib import Path
import json
from django.conf import settings

logger = logging.getLogger(__name__)

class TextFileStorage:
    """Service professionnel de stockage des textes extraits"""
    
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir or settings.MEDIA_ROOT) / "text_extracts"
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Crée les répertoires nécessaires"""
        directories = [
            self.base_dir,
            self.base_dir / "courriers",
            self.base_dir / "temp",
            self.base_dir / "logs"
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _generate_filename(self, courrier_id=None, reference=None):
        """Génère un nom de fichier unique"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        if reference:
            safe_ref = reference.replace("/", "_").replace("\\", "_").replace(" ", "_")[:50]
            filename = f"{timestamp}_{safe_ref}_{unique_id}"
        elif courrier_id:
            filename = f"courrier_{courrier_id}_{timestamp}_{unique_id}"
        else:
            filename = f"extrait_{timestamp}_{unique_id}"
        
        return f"{filename}.txt"
    
    def _get_storage_path(self, courrier_id=None):
        """Détermine le chemin de stockage"""
        if courrier_id:
            # Organisation par ID de courrier
            dir_path = self.base_dir / "courriers" / str(courrier_id)
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        else:
            # Stockage temporaire
            return self.base_dir / "temp"
    
    def save_extracted_text(self, text, metadata=None, courrier_id=None, reference=None):
        """
        Sauvegarde le texte extrait avec métadonnées
        """
        try:
            # Validation du texte
            if not text or not isinstance(text, str):
                logger.warning("Texte invalide ou vide")
                return None
            
            text = text.strip()
            if not text:
                logger.warning("Texte vide après nettoyage")
                return None
            
            # Générer le nom de fichier
            filename = self._generate_filename(courrier_id, reference)
            storage_path = self._get_storage_path(courrier_id)
            file_path = storage_path / filename
            
            # Formater le contenu
            content = self._format_content(text, metadata, file_path)
            
            # Écrire le fichier
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Sauvegarder les métadonnées JSON
            if metadata:
                self._save_metadata(file_path, metadata)
            
            # Informations sur le fichier
            file_info = {
                "path": str(file_path),
                "filename": filename,
                "relative_path": str(file_path.relative_to(settings.MEDIA_ROOT)),
                "url": f"/media/{file_path.relative_to(settings.MEDIA_ROOT)}",
                "size": os.path.getsize(file_path),
                "created_at": datetime.now().isoformat(),
                "courrier_id": courrier_id,
                "reference": reference
            }
            
            logger.info(f"✅ Fichier texte créé: {file_path} ({file_info['size']} octets)")
            return file_info
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde texte: {str(e)}")
            return None
    
    def _format_content(self, text, metadata, file_path):
        """Formate le contenu du fichier"""
        lines = []
        
        # En-tête
        lines.append("=" * 80)
        lines.append("EXTRACTION DE TEXTE OCR - SYSTÈME DE GESTION DE COURRIER")
        lines.append("=" * 80)
        lines.append(f"Fichier : {file_path.name}")
        lines.append(f"Date de création : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Généré automatiquement par le système")
        lines.append("-" * 80)
        
        # Métadonnées
        if metadata:
            lines.append("\n[MÉTADONNÉES DU COURRIER]")
            lines.append("-" * 40)
            
            # Champs prioritaires
            priority_fields = ['reference', 'objet', 'expediteur_nom', 'date_reception']
            for field in priority_fields:
                if field in metadata and metadata[field]:
                    lines.append(f"{field.upper()}: {metadata[field]}")
            
            # Autres champs
            for key, value in metadata.items():
                if key not in priority_fields and value:
                    lines.append(f"{key.upper()}: {value}")
        
        # Contenu OCR
        lines.append("\n" + "=" * 80)
        lines.append("[CONTENU EXTRIT PAR OCR]")
        lines.append("=" * 80 + "\n")
        lines.append(text)
        
        # Pied de page
        lines.append("\n" + "=" * 80)
        lines.append("FIN DU DOCUMENT")
        lines.append(f"Longueur : {len(text)} caractères")
        lines.append(f"Lignes : {text.count(chr(10)) + 1}")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def _save_metadata(self, file_path, metadata):
        """Sauvegarde les métadonnées en JSON"""
        try:
            metadata_file = file_path.parent / f"{file_path.stem}_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder les métadonnées JSON: {e}")
    
    def get_courrier_text_file(self, courrier_id):
        """Récupère le fichier texte d'un courrier"""
        courrier_dir = self.base_dir / "courriers" / str(courrier_id)
        if courrier_dir.exists():
            # Cherche le dernier fichier .txt créé
            txt_files = list(courrier_dir.glob("*.txt"))
            if txt_files:
                return sorted(txt_files, key=os.path.getmtime, reverse=True)[0]
        return None
    
    def read_courrier_text(self, courrier_id):
        """Lit le contenu du fichier texte d'un courrier"""
        file_path = self.get_courrier_text_file(courrier_id)
        if file_path and file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Erreur lecture fichier {file_path}: {e}")
        return None

# Instance globale
text_storage = TextFileStorage()