# workflow/services/classifier.py
import logging
import re
from datetime import datetime
from .extracteur_ocr import extracteur_ocr

logger = logging.getLogger(__name__)

def classifier_courrier(courrier):
    """
    Classification IA améliorée du courrier avec extraction OCR
    """
    try:
        # Extraire toutes les informations du texte OCR
        texte_ocr = courrier.contenu_texte or ""
        infos_extrait = extracteur_ocr.extraire_toutes_informations(texte_ocr)
        
        # Construire le texte pour la classification
        texte_parts = []
        
        # Utiliser l'objet extrait en priorité, sinon celui du courrier
        objet = infos_extrait.get("objet") or courrier.objet or ""
        if objet:
            texte_parts.append(objet)
        
        # Ajouter le contenu OCR
        if texte_ocr:
            texte_parts.append(texte_ocr)
        
        # Ajouter l'expéditeur extrait
        expediteur_nom = infos_extrait.get("expediteur", {}).get("nom") or courrier.expediteur_nom or ""
        if expediteur_nom:
            texte_parts.append(expediteur_nom)
        
        texte_complet = " ".join(texte_parts)
        texte_lower = texte_complet.lower()
        
        # Dictionnaire de mots-clés amélioré
        categories_mots_cles = {
            'RH': {
                'mots': ['emploi', 'salaire', 'contrat', 'congé', 'recrutement', 
                        'personnel', 'formation', 'paie', 'employé', 'embauche',
                        'démission', 'retraite', 'candidature', 'cv', 'entretien',
                        'grh', 'ressources humaines', 'stage', 'stagiaire'],
                'score': 0,
                'services': ['Service des Ressources Humaines', 'Direction des RH']
            },
            'FINANCE': {
                'mots': ['facture', 'paiement', 'budget', 'compte', 'financier',
                        'fiscal', 'impôt', 'trésorerie', 'comptabilité', 'dépense',
                        'remboursement', 'décaissement', 'virement', 'bancaire',
                        'finances', 'argent', 'frais', 'coût', 'prix'],
                'score': 0,
                'services': ['Service Financier', 'Comptabilité', 'Trésorerie']
            },
            'JURIDIQUE': {
                'mots': ['contrat', 'loi', 'juridique', 'avocat', 'tribunal',
                        'litige', 'droit', 'justice', 'procès', 'jurisprudence',
                        'convention', 'règlement', 'légal', 'notaire', 'procédure',
                        'plainte', 'dossier', 'affaire'],
                'score': 0,
                'services': ['Service Juridique', 'Direction Juridique']
            },
            'TECHNIQUE': {
                'mots': ['maintenance', 'réparation', 'technique', 'logiciel',
                        'informatique', 'système', 'réseau', 'développement',
                        'bug', 'installation', 'matériel', 'équipement',
                        'technologie', 'si', 'it', 'ordinateur', 'serveur',
                        'programme', 'application'],
                'score': 0,
                'services': ['Service Technique', 'Service Informatique', 'Direction Technique']
            },
            'COMMERCIAL': {
                'mots': ['client', 'vente', 'commercial', 'marché', 'offre',
                        'devis', 'proposition', 'négociation', 'partenaire',
                        'fournisseur', 'achat', 'approvisionnement', 'contrat',
                        'commande', 'facturation', 'livraison'],
                'score': 0,
                'services': ['Service Commercial', 'Service Achats', 'Direction Commerciale']
            },
            'FORMATION': {
                'mots': ['formation', 'stage', 'cours', 'apprentissage', 'enseignant',
                        'professeur', 'étudiant', 'école', 'université', 'diplôme',
                        'certification', 'pédagogie', 'apprendre', 'enseignement',
                        'séminaire', 'atelier', 'conférence'],
                'score': 0,
                'services': ['Service de Formation', 'Direction des Études', 'Service des Études']
            },
            'ADMINISTRATIF': {
                'mots': ['administration', 'document', 'archive', 'bureau',
                        'secrétariat', 'courrier', 'réunion', 'procédure',
                        'formulaire', 'demande', 'autorisation', 'approbation',
                        'lettre', 'note', 'mémorandum', 'circulaire'],
                'score': 1,
                'services': ['Secrétariat Général', 'Service Administratif']
            }
        }
        
        # Calcul des scores par catégorie
        for categorie, data in categories_mots_cles.items():
            for mot in data['mots']:
                if mot in texte_lower:
                    data['score'] += 1
        
        # Trouver la meilleure catégorie
        meilleure_categorie = max(categories_mots_cles.items(), 
                                  key=lambda x: x[1]['score'])[0]
        meilleur_score = categories_mots_cles[meilleure_categorie]['score']
        
        # Calcul de la confiance
        total_mots_possibles = len(categories_mots_cles[meilleure_categorie]['mots'])
        confiance = min(meilleur_score / max(total_mots_possibles, 1), 0.95)
        
        # Si la confiance est trop basse, utiliser la catégorie par défaut
        if confiance < 0.3:
            meilleure_categorie = 'ADMINISTRATIF'
            confiance = 0.3
        
        # Déterminer la priorité
        priorite = determiner_priorite(texte_complet, infos_extrait)
        
        # Service correspondant
        service = categories_mots_cles[meilleure_categorie]['services'][0]
        
        # Construire le résultat avec toutes les informations
        result = {
            'category': meilleure_categorie,
            'service_impute': service,
            'confidence': float(confiance),
            'priorite': priorite['niveau'],
            'priorite_raison': priorite['raison'],
            'objet_extrait': objet,
            'expediteur': infos_extrait.get('expediteur', {}),
            'date_extrait': infos_extrait.get('date', ''),
            'mots_cles': infos_extrait.get('mots_cles', [])[:5]
        }
        
        logger.info(f"Classification: {meilleure_categorie} ({confiance:.2f}), "
                   f"Priorité: {priorite['niveau']}, Objet: {objet[:50]}...")
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur classification: {e}", exc_info=True)
        return {
            'category': 'ADMINISTRATIF',
            'service_impute': 'Secrétariat Général',
            'confidence': 0.3,
            'priorite': 'NORMALE',
            'priorite_raison': 'Erreur de classification',
            'objet_extrait': '',
            'expediteur': {},
            'date_extrait': '',
            'mots_cles': []
        }

def determiner_priorite(texte, infos_extrait):
    """Détermine la priorité basée sur le contenu"""
    texte_lower = texte.lower()
    
    # Mots indiquant l'urgence
    mots_urgents = ['urgent', 'immédiat', 'dès que possible', 'asap', 'important',
                    'délai', 'échéance', 'date limite', 'dernier délai', 'rapide',
                    'prioritaire', 'critique', 'impératif', 'essentiel']
    
    score_urgence = 0
    for mot in mots_urgents:
        if mot in texte_lower:
            score_urgence += 2
    
    # Vérifier les dates proches
    aujourdhui = datetime.now()
    if infos_extrait.get('date'):
        try:
            date_obj = datetime.strptime(infos_extrait['date'], '%Y-%m-%d')
            jours_diff = (date_obj - aujourdhui).days
            if 0 <= jours_diff <= 3:  # Moins de 3 jours
                score_urgence += 3
            elif jours_diff < 0:  # Dépassé
                score_urgence += 4
        except:
            pass
    
    # Déterminer le niveau
    if score_urgence >= 5:
        return {'niveau': 'URGENTE', 'raison': 'Termes urgents et délai court détectés'}
    elif score_urgence >= 3:
        return {'niveau': 'HAUTE', 'raison': 'Termes importants ou délai proche'}
    elif score_urgence >= 1:
        return {'niveau': 'NORMALE', 'raison': 'Document standard'}
    else:
        return {'niveau': 'BASSE', 'raison': 'Document non prioritaire'}