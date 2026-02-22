# workflow/services/extracteur_ocr.py
import re
import logging
from datetime import datetime
import dateutil.parser

logger = logging.getLogger(__name__)

class ExtracteurOCR:
    """
    Service d'extraction avancé d'informations depuis le texte OCR
    """
    
    def extraire_toutes_informations(self, texte_ocr):
        """
        Extrait toutes les informations possibles du texte OCR
        """
        if not texte_ocr:
            return {}
        
        informations = {
            "objet": "",
            "expediteur": {
                "nom": "",
                "email": "",
                "telephone": "",
                "adresse": "",
                "institution": ""
            },
            "destinataire": "",
            "date": "",
            "references": [],
            "mots_cles": []
        }
        
        # Normaliser le texte
        texte = texte_ocr.replace('\n', ' ').replace('\r', ' ')
        
        # 1. Extraire l'objet
        informations["objet"] = self._extraire_objet(texte_ocr)
        
        # 2. Extraire l'expéditeur
        informations["expediteur"] = self._extraire_expediteur(texte_ocr)
        
        # 3. Extraire la date
        informations["date"] = self._extraire_date(texte_ocr)
        
        # 4. Extraire les références
        informations["references"] = self._extraire_references(texte_ocr)
        
        # 5. Extraire les mots-clés
        informations["mots_cles"] = self._extraire_mots_cles(texte_ocr)
        
        return informations
    
    def _extraire_objet(self, texte):
        """Extrait l'objet du courrier"""
        # Recherche des motifs courants
        patterns = [
            r'Objet\s*[:\-]\s*(.+?)(?:\n|$)',
            r'OBJET\s*[:\-]\s*(.+?)(?:\n|$)',
            r'Subject\s*[:\-]\s*(.+?)(?:\n|$)',
            r'SUBJECT\s*[:\-]\s*(.+?)(?:\n|$)',
            r'Re\s*:\s*(.+?)(?:\n|$)',
            r'RE\s*:\s*(.+?)(?:\n|$)',
            r'Objet\s*:\s*(.+?)(?=\n\s*\n)',
            r'OBJET\s*:\s*(.+?)(?=\n\s*\n)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, texte, re.IGNORECASE | re.DOTALL)
            if match:
                objet = match.group(1).strip()
                # Nettoyer l'objet
                objet = re.sub(r'^\s*[:\-]\s*', '', objet)
                # Enlever les retours à la ligne
                objet = objet.replace('\n', ' ').strip()
                return objet[:200]  # Limiter la longueur
        
        # Si pas trouvé, essayer de trouver dans les premières lignes
        lines = texte.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if ('demande' in line_lower or 'lettre' in line_lower or 
                'courrier' in line_lower or 'document' in line_lower or
                'proposition' in line_lower or 'offre' in line_lower):
                # Prendre la ligne suivante comme objet potentiel
                if i + 1 < len(lines):
                    return lines[i + 1].strip()[:200]
        
        return "Document administratif"
    
    def _extraire_expediteur(self, texte):
        """Extrait les informations de l'expéditeur"""
        expediteur = {
            "nom": "",
            "email": "",
            "telephone": "",
            "adresse": "",
            "institution": ""
        }
        
        # Extraire l'email
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', texte)
        if emails:
            expediteur["email"] = emails[0]
        
        # Extraire le téléphone
        phone_patterns = [
            r'(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}',
            r'\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}',
            r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, texte)
            if phones:
                expediteur["telephone"] = phones[0]
                break
        
        # Extraire l'adresse (chercher des motifs d'adresse)
        address_patterns = [
            r'\d+\s+[A-Za-z\s,]+(?:rue|avenue|boulevard|route|quartier)[A-Za-z\s,]+',
            r'(?:BP|B\.P\.)\s*\d+\s+[A-Za-z\s,]+',
            r'[A-Za-z\s]+,?\s+\d{5}\s+[A-Za-z\s]+'
        ]
        
        for pattern in address_patterns:
            addresses = re.findall(pattern, texte, re.IGNORECASE)
            if addresses:
                expediteur["adresse"] = addresses[0].strip()
                break
        
        # Extraire le nom de l'expéditeur (chercher après "De:" ou "From:")
        nom_patterns = [
            r'(?:De|From|Expéditeur)\s*[:\-]\s*(.+?)(?:\n|$)',
            r'À\s+l\'attention\s+de\s*(.+?)(?:\n|$)',
            r'Monsieur\s+(.+?)(?:\n|$)',
            r'Madame\s+(.+?)(?:\n|$)',
            r'Cher\s+(.+?)(?:\n|$)',
            # Nouveau: Chercher le nom de l'entreprise dans les premières lignes
            r'^(.*?(?:SARL|SA|SAS|ETS|GIE|SOCIÉTÉ|SOCIETE|ENTREPRISE|COMPAGNIE|COMPANY|INC|LTD|GMBH).*?)(?:\n|$)'
        ]
        
        for pattern in nom_patterns:
            match = re.search(pattern, texte, re.IGNORECASE)
            if match:
                expediteur["nom"] = match.group(1).strip()
                break
        
        # Si pas trouvé, chercher dans les premières lignes (haut du document)
        if not expediteur["nom"]:
            lines = texte.split('\n')
            for line in lines[:10]:
                line_stripped = line.strip()
                if (line_stripped and 
                    not any(word in line_stripped.lower() for word in 
                           ['objet', 'réf', 'date', 'page', 'destinataire', 'à', 'le', 'la', 'les']) and
                    len(line_stripped) < 100):
                    expediteur["nom"] = line_stripped
                    break
        
        # Extraire l'institution
        institution_keywords = ['université', 'école', 'entreprise', 'société', 
                               'ministère', 'direction', 'service', 'département',
                               'sarl', 'sa', 'sas', 'ets', 'gie', 'company', 'ltd']
        
        lines = texte.split('\n')
        for line in lines:
            line_lower = line.lower()
            for keyword in institution_keywords:
                if keyword in line_lower:
                    expediteur["institution"] = line.strip()
                    break
            if expediteur["institution"]:
                break
        
        # Si on a une institution mais pas de nom, utiliser l'institution
        if expediteur["institution"] and not expediteur["nom"]:
            expediteur["nom"] = expediteur["institution"]
        
        return expediteur
    
    def _extraire_date(self, texte):
        """Extrait la date du document"""
        date_patterns = [
            r'\d{2}/\d{2}/\d{4}',
            r'\d{2}-\d{2}-\d{4}',
            r'\d{4}-\d{2}-\d{2}',
            r'\d{1,2}\s+[A-Za-z]+\s+\d{4}',
            r'le\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}',
            r'Fait\s+à\s+.+,\s+le\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}',
            r'Date\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, texte, re.IGNORECASE)
            if matches:
                try:
                    # Essayer de parser la date
                    date_str = matches[0]
                    # Remplacer les mois français
                    mois_fr = {
                        'janvier': 'January', 'février': 'February', 'mars': 'March',
                        'avril': 'April', 'mai': 'May', 'juin': 'June',
                        'juillet': 'July', 'août': 'August', 'septembre': 'September',
                        'octobre': 'October', 'novembre': 'November', 'décembre': 'December'
                    }
                    
                    for fr, en in mois_fr.items():
                        date_str = date_str.replace(fr, en)
                    
                    date_obj = dateutil.parser.parse(date_str, fuzzy=True)
                    return date_obj.strftime('%Y-%m-%d')
                except:
                    continue
        
        return ""
    
    def _extraire_references(self, texte):
        """Extrait les références du document"""
        ref_patterns = [
            r'Réf\s*[:\-\.]\s*(.+?)(?:\n|$)',
            r'Reference\s*[:\-\.]\s*(.+?)(?:\n|$)',
            r'N[°o]\s*[:\-\.]\s*(.+?)(?:\n|$)',
            r'Dossier\s*[:\-\.]\s*(.+?)(?:\n|$)',
            r'Numéro\s*[:\-\.]\s*(.+?)(?:\n|$)',
            r'N°\s*(\d+[-/]\d+[/-]\d+)'
        ]
        
        references = []
        for pattern in ref_patterns:
            matches = re.findall(pattern, texte, re.IGNORECASE)
            references.extend(matches)
        
        return [ref.strip() for ref in references if ref.strip()]
    
    def _extraire_mots_cles(self, texte):
        """Extrait les mots-clés du document"""
        # Mots à exclure (stop words français)
        stop_words = {'le', 'la', 'les', 'de', 'du', 'des', 'et', 'à', 'au', 'aux',
                     'en', 'dans', 'pour', 'avec', 'sur', 'par', 'un', 'une', 'du',
                     'est', 'sont', 'que', 'qui', 'quoi', 'où', 'quand', 'comment',
                     'pourquoi', 'ce', 'cette', 'ces', 'son', 'sa', 'ses', 'notre',
                     'nos', 'votre', 'vos', 'leur', 'leurs', 'l', 'd', 'n', 's'}
        
        # Extraire les mots significatifs
        words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', texte.lower())
        
        # Filtrer les stop words et compter les occurrences
        word_counts = {}
        for word in words:
            if word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        # Prendre les 10 mots les plus fréquents
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:10]]

# Instance globale
extracteur_ocr = ExtracteurOCR()