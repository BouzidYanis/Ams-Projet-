import spacy
from spacy.tokens import Doc
from spacy.matcher import Matcher
import re

# Charger le modèle français
nlp = spacy.load("fr_core_news_md")

# Enregistrer les attributs personnalisés
if not Doc.has_extension("intent"):
    Doc.set_extension("intent", default=None)
if not Doc.has_extension("confidence"):
    Doc.set_extension("confidence", default=0.0)

# Définir les patterns pour chaque intention
INTENT_PATTERNS = {
    "salutation": [
        r"\b(bonjour|salut|hello|bonsoir|hey|coucou|hi)\b",
        r"\b(comment (ça va|allez-vous))\b",
    ],
    
    "demander_heure": [
        r"\b(horaire|heure|quand|ouvre|ferme|ouvert|ouverture|fermeture)\b",
        r"\b(à quelle heure|quel heure)\b",
        r"\b(planning|emploi du temps|programme)\b",
    ],
    
    "demander_activite": [
        r"\b(activité|sport|cours|séance|discipline)\b",
        r"\b(qu'est-ce que|c'est quoi|info|information|propose)\b.*\b(activité|sport|cours)\b",
        r"\b(quel|quelle).*\b(activité|sport|cours)\b",
        r"\b(liste|voir).*\b(activité|sport|cours)\b",
    ],
    
    "demander_lieu": [
        r"\b(où|trouver|situé|trouve|aller)\b",
        r"\b(vestiaire|salle|piscine|terrain|accueil|toilette|casier)\b",
        r"\b(comment.*aller|pour aller)\b",
        r"\b(direction|chemin|localisation|emplacement)\b",
    ],
    
    "reserver": [
        r"\b(réserver|réservation|réserve|inscription|inscrire|inscrit)\b",
        r"\b(prendre.*cours|prendre.*place)\b",
        r"\b(je (veux|voudrais|souhaite).*réserver)\b",
        r"\b(booking|book)\b",
        r"\b(je (veux|voudrais|souhaite).*(salle|cours|terrain))\b",
        r"\b(réserver.*(salle|cours|terrain|créneau))\b",
    ],
    
    "qui": [
        r"\b(qui (es-tu|êtes-vous|est)|tu es qui)\b",
        r"\b(c'est quoi.*nom|ton nom|votre nom|comment.*appel)\b",
        r"\b(qui.*créé|qui.*développé|qui.*robot)\b",
        r"\b(présente-toi|présentez-vous)\b",
    ],
    "demander_evenement_special": [
        r"\b(événement|animation|spécial|occasion)\b",
        r"\b(qu'est-ce que|c'est quoi|info|information|propose)\b.*\b(événement|animation|spécial|occasion)\b",
        r"\b(quel|quelle).*\b(événement|animation|spécial|occasion)\b",
        r"\b(liste|voir).*\b(événement|animation|spécial|occasion)\b",
    ],
}

# Compilez les patterns regex
compiled_patterns = {
    intent: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for intent, patterns in INTENT_PATTERNS.items()
}

@spacy.Language.component("intent_classifier")
def intent_classifier(doc):
    """Classifie l'intention de l'utilisateur"""
    text = doc.text.lower()
    scores = {}
    
    # Calculer un score pour chaque intention
    for intent, patterns in compiled_patterns.items():
        score = 0
        for pattern in patterns:
            if pattern.search(text):
                score += 1
        scores[intent] = score
    
    # Sélectionner l'intention avec le score le plus élevé
    if max(scores.values()) > 0:
        doc._.intent = max(scores, key=scores.get)
        doc._.confidence = scores[doc._.intent] / len(compiled_patterns[doc._.intent])
    else:
        doc._.intent = "inconnu"
        doc._.confidence = 0.0
    
    return doc

# Ajouter le composant au pipeline
nlp.add_pipe("intent_classifier", last=True)

# Matcher pour extraire les entités (sports, lieux)
matcher = Matcher(nlp.vocab)

# Patterns pour les sports/activités
sports_patterns = [
    [{"LOWER": {"IN": ["piscine", "natation", "nage", "aquagym"]}}],
    [{"LOWER": {"IN": ["tennis", "badminton", "squash", "ping-pong"]}}],
    [{"LOWER": {"IN": ["fitness", "musculation", "cardio", "gym"]}}],
    [{"LOWER": {"IN": ["yoga", "pilates", "stretching"]}}],
    [{"LOWER": {"IN": ["zumba", "danse", "aerobic"]}}],
    [{"LOWER": {"IN": ["football", "basket", "volley", "handball"]}}],
    [{"LOWER": {"IN": ["running", "course", "jogging", "athlétisme"]}}],
]

matcher.add("SPORT", sports_patterns)

# Patterns pour les lieux
lieux_patterns = [
    [{"LOWER": {"IN": ["vestiaire", "vestiaires", "casier", "casiers"]}}],
    [{"LOWER": {"IN": ["piscine", "bassin"]}}],
    [{"LOWER": {"IN": ["accueil", "réception", "entrée"]}}],
    [{"LOWER": {"IN": ["toilette", "toilettes", "wc"]}}],
    [{"LOWER": {"IN": ["secrétariat", "secrétaire", "bureau"]}}],

    # Salle identifiée par lettre (ex: "salle A") — AVANT le pattern générique "salle"
    [{"LOWER": "salle"}, {"LOWER": {"IN": ["a", "b", "c", "d","e","f"]}}],
    [{"LOWER": "salle"}, {"LOWER": "de"}, {"LOWER": {"IN": ["sport", "natation", "fitness", "musculation"]}}],
    [{"LOWER": "salle"}, {"LOWER": {"IN": ["natation", "fitness", "musculation", "sport"]}}],

    # Salle identifiée par numéro (ex: "salle 2")
    [{"LOWER": "salle"}, {"LIKE_NUM": True}],

    # Lieux génériques (en dernier pour ne pas écraser les patterns composés)
    [{"LOWER": {"IN": ["salle", "terrain", "court"]}}],
]

matcher.add("LIEU", lieux_patterns)

def extraire_entites(doc):
    """Extrait toutes les entités pertinentes"""
    matches = matcher(doc)
    
    sports = []
    lieux = []
    
    # Filtrer les matches pour garder le plus long quand il y a chevauchement
    filtered = []
    matches_sorted = sorted(matches, key=lambda m: (m[1], -(m[2] - m[1])))
    last_end = -1
    for match_id, start, end in matches_sorted:
        if start >= last_end:
            filtered.append((match_id, start, end))
            last_end = end

    for match_id, start, end in filtered:
        label = nlp.vocab.strings[match_id]
        entity_text = doc[start:end].text
        
        if label == "SPORT":
            sports.append(entity_text)
        elif label == "LIEU":
            lieux.append(entity_text)
    
    # Extraire les entités temporelles de spaCy
    temps = [ent.text for ent in doc.ents if ent.label_ in ["DATE", "TIME"]]
    
    # Extraire les nombres (pour les heures, salles, etc.)
    nombres = [token.text for token in doc if token.like_num]
    
    return {
        "intent": doc._.intent,
        "confidence": round(doc._.confidence, 2),
        "entites": {
            "sports": list(set(sports)),
            "lieux": list(set(lieux)),
            "temps": temps,
            "nombres": nombres,
        }
    }

def traiter_requete(texte):
    """Fonction principale de traitement NLU"""
    doc = nlp(texte)
    resultat = extraire_entites(doc)
    return resultat

# ==============================
# TESTS (uniquement si exécuté directement)
# ==============================
if __name__ == "__main__":
    # Tests avec des exemples pour chaque intention
    exemples_test = {
        "salutation": [
            "Bonjour !",
            "Salut, comment ça va ?",
            "Bonsoir",
        ],
        
        "demander_heure": [
            "Quels sont les horaires de la piscine ?",
            "À quelle heure ouvre le centre ?",
            "Le planning des cours de yoga",
            "Quand ferme la salle de musculation ?",
        ],
        
        "demander_activite": [
            "Quelles activités proposez-vous ?",
            "Je voudrais des infos sur les cours de tennis",
            "C'est quoi comme sport ici ?",
            "Liste des activités disponibles",
        ],
        
        "demander_lieu": [
            "Où sont les vestiaires ?",
            "Comment aller à la piscine ?",
            "Je cherche la salle 2",
            "Où se trouve l'accueil ?",
        ],
        
        "reserver": [
            "Je voudrais réserver un cours de fitness",
            "Inscription pour la natation",
            "Prendre un cours de tennis demain",
            "Réservation terrain de badminton",
        ],
        
        "qui": [
            "Qui es-tu ?",
            "C'est quoi ton nom ?",
            "Présente-toi",
            "Qui t'a créé ?",
        ],
    }

    # Exécution des tests
    print("=" * 60)
    print("TESTS DU SYSTÈME NLU - ROBOT D'ACCUEIL MULTISPORT")
    print("=" * 60)

    for intent_attendue, phrases in exemples_test.items():
        print(f"\n### Intention: {intent_attendue.upper()} ###")
        for phrase in phrases:
            resultat = traiter_requete(phrase)
            correct = "✓" if resultat["intent"] == intent_attendue else "✗"
            print(f"\n{correct} Phrase: \"{phrase}\"")
            print(f"  → Intent détectée: {resultat['intent']} (confiance: {resultat['confidence']})")
            if resultat['entites']['sports']:
                print(f"  → Sports: {resultat['entites']['sports']}")
            if resultat['entites']['lieux']:
                print(f"  → Lieux: {resultat['entites']['lieux']}")
            if resultat['entites']['temps']:
                print(f"  → Temps: {resultat['entites']['temps']}")

    # Test interactif
    print("\n" + "=" * 60)
    print("MODE INTERACTIF (tapez 'quit' pour quitter)")
    print("=" * 60)

    while True:
        user_input = input("\nVous: ")
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
        
        resultat = traiter_requete(user_input)
        print(f"\nRésultat NLU:")
        print(f"  Intent: {resultat['intent']}")
        print(f"  Confiance: {resultat['confidence']}")
        print(f"  Entités: {resultat['entites']}")