from courriers.models import Courrier
from .models import IAResult
from core.models import Category, ClassificationRule
from workflow.models import Workflow, WorkflowStep
import spacy
import pytesseract
from PIL import Image

# nlp = spacy.load("fr_core_news_md")  # modèle français spaCy

_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("fr_core_news_sm")  # PLUS LÉGER
    return _nlp

def process_courrier_automatique(courrier: Courrier):
    """
    Traitement automatique IA + workflow
    """

    # --- 1. OCR ---
    texte_extrait = courrier.texte if hasattr(courrier, "texte") else ""
    # Si fichier image/PDF :
    # texte_extrait = pytesseract.image_to_string(Image.open(courrier.fichier.path))

    # --- 2. NLP → catégorie ---
    categories = Category.objects.all()
    doc = nlp(texte_extrait)
    cat_scores = {}
    for cat in categories:
        cat_doc = nlp(cat.name)
        cat_scores[cat.id] = doc.similarity(cat_doc)

    if cat_scores:
        best_cat_id = max(cat_scores, key=cat_scores.get)
        categorie_predite = Category.objects.get(id=best_cat_id)
        fiabilite = cat_scores[best_cat_id]
    else:
        categorie_predite = None
        fiabilite = 0.0

    # --- 3. Suggestion service ---
    service_suggere = None
    if categorie_predite:
        rules = ClassificationRule.objects.filter(category=categorie_predite, active=True).order_by('priority')
        if rules.exists():
            service_suggere = rules.first().service

    # --- 4. Création / mise à jour IAResult ---
    ia_result, created = IAResult.objects.update_or_create(
        courrier=courrier,
        defaults={
            "texte_extrait": texte_extrait,
            "categorie_predite": categorie_predite,
            "service_suggere": service_suggere,
            "fiabilite": fiabilite,
            "meta": {"cat_scores": cat_scores},
        }
    )

    # --- 5. Création workflow automatique ---
    workflow, wf_created = Workflow.objects.get_or_create(courrier=courrier)
    if wf_created:
        WorkflowStep.objects.create(
            workflow=workflow,
            step_number=1,
            label=f"Traitement initial - {categorie_predite.name if categorie_predite else 'Non classé'}",
            approbateur_service=service_suggere,
            statut='en_attente'
        )

    return ia_result, workflow
