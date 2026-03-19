# courriers/workflow_traitement.py
#
# Définit les circuits de traitement selon le TYPE du courrier.
# Chaque type a ses propres étapes — on ne force plus un flux unique à 8 étapes.
#
# CIRCUITS :
#   entrant  → prise_en_charge → analyse → instruction → redaction → validation → signature → envoi → cloture
#   sortant  → redaction → validation → signature → envoi → cloture
#   interne  → prise_en_charge → transmission → cloture

from .models import TraitementStatus

# ─────────────────────────────────────────────────────────────────────────────
# Définition des circuits
# ─────────────────────────────────────────────────────────────────────────────

CIRCUITS = {
    'entrant': [
        'prise_en_charge',
        'analyse',
        'instruction',
        'redaction',
        'validation',
        'signature',
        'envoi',
        'cloture',
    ],
    'sortant': [
        'redaction',
        'validation',
        'signature',
        'envoi',
        'cloture',
    ],
    'interne': [
        'prise_en_charge',
        'transmission',
        'cloture',
    ],
}

# Étape initiale par type (état du courrier à la création)
ETAPE_INITIALE = {
    'entrant': 'prise_en_charge',
    'sortant': 'redaction',
    'interne': 'prise_en_charge',
}

# Libellés des étapes
ETAPE_LABELS = {
    'prise_en_charge': 'Prise en charge',
    'analyse':         'Analyse',
    'instruction':     'Instruction',
    'redaction':       'Rédaction',
    'validation':      'Validation',
    'signature':       'Signature',
    'envoi':           'Envoi',
    'cloture':         'Clôturé',
    'transmission':    'Transmission',
    'rejete':          'Rejeté',
}


def get_circuit(type_courrier):
    """Retourne la liste ordonnée des étapes pour un type de courrier."""
    return CIRCUITS.get(type_courrier, CIRCUITS['entrant'])


def get_etape_initiale(type_courrier):
    """Retourne l'étape de démarrage selon le type."""
    return ETAPE_INITIALE.get(type_courrier, 'prise_en_charge')


def get_etape_suivante(type_courrier, etape_actuelle):
    """
    Retourne l'étape suivante dans le circuit.
    Retourne None si on est déjà à la dernière étape.
    """
    circuit = get_circuit(type_courrier)
    try:
        idx = circuit.index(etape_actuelle)
        if idx + 1 < len(circuit):
            return circuit[idx + 1]
    except ValueError:
        pass
    return None


def peut_avancer(courrier, user):
    """
    Vérifie si l'utilisateur peut faire avancer ce courrier
    à l'étape suivante.
    """
    role = getattr(user, 'role', '')

    # Admin et direction peuvent tout faire
    if role in ('admin', 'direction'):
        return True, None

    statut = courrier.traitement_statut
    agent_id = getattr(courrier.agent_traitant, 'id', courrier.agent_traitant)
    resp_id  = getattr(courrier.responsable_actuel, 'id', courrier.responsable_actuel)
    est_agent = user.id in (agent_id, resp_id)

    # Règles par étape
    if statut == 'prise_en_charge':
        if role in ('agent_service', 'collaborateur', 'chef') or est_agent:
            return True, None
        return False, "Seul l'agent assigné peut prendre en charge ce courrier."

    if statut == 'analyse':
        if role in ('agent_service', 'collaborateur', 'chef') or est_agent:
            return True, None
        return False, "Seul l'agent traitant peut valider l'analyse."

    if statut == 'instruction':
        if role in ('agent_service', 'collaborateur', 'chef') or est_agent:
            return True, None
        return False, "Seul l'agent traitant peut valider l'instruction."

    if statut == 'redaction':
        if role in ('agent_service', 'collaborateur', 'chef') or est_agent:
            return True, None
        return False, "Seul l'agent rédacteur peut soumettre la réponse."

    if statut == 'validation':
        # Le validateur est le chef du service ou un validateur désigné
        if role in ('chef', 'direction', 'admin'):
            return True, None
        return False, "Seul un chef de service ou la direction peut valider."

    if statut == 'signature':
        if role in ('chef', 'direction', 'admin') or est_agent:
            return True, None
        return False, "Vous n'êtes pas autorisé à signer ce courrier."

    if statut == 'envoi':
        if role in ('agent_courrier', 'chef', 'direction', 'admin') or est_agent:
            return True, None
        return False, "Vous n'êtes pas autorisé à confirmer l'envoi."

    if statut == 'transmission':
        if role in ('agent_service', 'collaborateur', 'chef', 'admin') or est_agent:
            return True, None
        return False, "Vous n'êtes pas autorisé à transmettre ce courrier."

    return True, None


def progression_pct(type_courrier, etape_actuelle):
    """Calcule le pourcentage de progression dans le circuit."""
    circuit = get_circuit(type_courrier)
    try:
        idx = circuit.index(etape_actuelle)
        return round(idx / (len(circuit) - 1) * 100)
    except (ValueError, ZeroDivisionError):
        return 0


def build_historique_cloture(courrier):
    """
    Construit le récapitulatif complet du traitement pour un courrier clôturé.
    Utilisé pour afficher l'historique après clôture.
    """
    from .models import ActionHistorique, TraitementEtape, ValidationCourrier

    circuit    = get_circuit(courrier.type)
    etapes_db  = TraitementEtape.objects.filter(courrier=courrier).order_by('date_debut')
    histo_db   = ActionHistorique.objects.filter(courrier=courrier).order_by('date')
    validations= ValidationCourrier.objects.filter(courrier=courrier).order_by('ordre')

    recap = {
        'reference':    courrier.reference,
        'objet':        courrier.objet,
        'type':         courrier.type,
        'priorite':     courrier.priorite,
        'date_creation':str(courrier.created_at.date()) if courrier.created_at else None,
        'date_cloture': str(courrier.date_cloture) if courrier.date_cloture else None,
        'circuit':      circuit,
        'etapes': [],
        'validations': [],
        'historique': [],
    }

    # Étapes réalisées
    for etape in etapes_db:
        agent = etape.agent
        recap['etapes'].append({
            'type_etape':    etape.type_etape,
            'label':         ETAPE_LABELS.get(etape.type_etape, etape.type_etape),
            'statut':        etape.statut,
            'agent':         f"{agent.prenom} {agent.nom}" if agent else 'Système',
            'date_debut':    str(etape.date_debut) if etape.date_debut else None,
            'date_fin':      str(etape.date_fin)   if etape.date_fin   else None,
            'description':   etape.description or '',
            'commentaire':   etape.commentaire or '',
        })

    # Validations
    for v in validations:
        val = v.validateur
        recap['validations'].append({
            'type':        v.type_validation,
            'label':       v.get_type_validation_display() if hasattr(v, 'get_type_validation_display') else v.type_validation,
            'statut':      v.statut,
            'validateur':  f"{val.prenom} {val.nom}" if val else '—',
            'commentaire': v.commentaire or '',
            'date_action': str(v.date_action) if v.date_action else None,
        })

    # Historique des actions
    for h in histo_db:
        u = h.user
        recap['historique'].append({
            'action':     h.action,
            'label':      h.action.replace('_', ' ').title(),
            'auteur':     f"{u.prenom} {u.nom}" if u else 'Système',
            'date':       str(h.date),
            'commentaire':h.commentaire or '',
        })

    return recap