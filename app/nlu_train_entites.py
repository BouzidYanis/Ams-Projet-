import random
from pathlib import Path

import spacy
from spacy.training.example import Example

# More varied training data
TRAIN_DATA_ENTITIES = [
    ("je veux faire du football", {"entities": [(16, 24, "ACTIVITY")]}),
    ("je voudrais faire du basketball", {"entities": [(20, 30, "ACTIVITY")]}),
    ("réserver un cours de fitness", {"entities": [(19, 26, "ACTIVITY")]}),
    ("inscription au futsal", {"entities": [(15, 21, "ACTIVITY")]}),
    ("je veux jouer au basket", {"entities": [(18, 24, "ACTIVITY")]}),
    ("est-ce qu'il y a du tennis ?", {"entities": [(19, 25, "ACTIVITY")]}),

    ("où est la salle de sport", {"entities": [(10, 23, "LOCATION")]}),
    ("où est la salle", {"entities": [(10, 18, "LOCATION")]}),
    ("où se trouve le vestiaire", {"entities": [(15, 23, "LOCATION")]}),
    ("peux-tu m'orienter vers le vestiaire", {"entities": [(29, 37, "LOCATION")]}),
    ("comment aller au terrain", {"entities": [(15, 21, "LOCATION")]}),
    ("je cherche l'accueil", {"entities": [(10, 16, "LOCATION")]}),
    ("je cherche la salle principale", {"entities": [(13, 29, "LOCATION")]}),

    # --- Salles (NER) : apprendre l'entité complète "salle A" (pas juste "salle") ---
    ("je cherche salle A", {"entities": [(10, 17, "LOCATION")]}),
    ("je cherche la salle A", {"entities": [(13, 20, "LOCATION")]}),
    ("où est salle A", {"entities": [(7, 14, "LOCATION")]}),
    ("où est la salle A", {"entities": [(10, 17, "LOCATION")]}),
    ("peux-tu me guider vers salle A", {"entities": [(23, 30, "LOCATION")]}),
    ("je veux aller à la salle A", {"entities": [(17, 24, "LOCATION")]}),
    ("direction salle A", {"entities": [(10, 17, "LOCATION")]}),
    ("je vais en salle A", {"entities": [(10, 17, "LOCATION")]}),

    ("je cherche salle B", {"entities": [(10, 17, "LOCATION")]}),
    ("je cherche la salle B", {"entities": [(13, 20, "LOCATION")]}),
    ("où est la salle B", {"entities": [(10, 17, "LOCATION")]}),
    ("peux-tu me guider vers salle B", {"entities": [(23, 30, "LOCATION")]}),

    ("je cherche salle C", {"entities": [(10, 17, "LOCATION")]}),
    ("je cherche la salle C", {"entities": [(13, 20, "LOCATION")]}),
    ("où est la salle C", {"entities": [(10, 17, "LOCATION")]}),

    ("je cherche salle D", {"entities": [(10, 17, "LOCATION")]}),
    ("je cherche la salle D", {"entities": [(13, 20, "LOCATION")]}),
    ("où est la salle D", {"entities": [(10, 17, "LOCATION")]}),

    # --- Natation / salle natation ---
    ("je cherche natation", {"entities": [(10, 18, "LOCATION")]}),
    ("où est natation", {"entities": [(7, 15, "LOCATION")]}),
    ("je cherche la natation", {"entities": [(13, 21, "LOCATION")]}),
    ("je cherche la salle natation", {"entities": [(13, 27, "LOCATION")]}),
    ("où est la salle natation", {"entities": [(10, 24, "LOCATION")]}),
    ("où est la salle de natation", {"entities": [(10, 27, "LOCATION")]}),

    # --- Autres lieux ---
    ("où est le secrétariat", {"entities": [(10, 20, "LOCATION")]}),
]

ACTIVITIES = ["yoga", "fitness", "basket", "basketball", "tennis", "futsal", "natation", "football"]
LOCATIONS = ["salle A", "salle de sport", "vestiaire", "terrain", "accueil", "secrétariat"]


def train(output_dir: str = "entity_model", n_iter: int = 40, seed: int = 42):
    random.seed(seed)
    nlp = spacy.blank("fr")

    # ÉTAPE 1 : Ajouter le NER en PREMIER
    ner = nlp.add_pipe("ner")
    for _, annotations in TRAIN_DATA_ENTITIES:
        for _, _, label in annotations["entities"]:
            ner.add_label(label)

    # ÉTAPE 2 : Initialiser et entraîner le NER
    optimizer = nlp.initialize()

    print("🔄 Entraînement du NER...")
    for i in range(n_iter):
        random.shuffle(TRAIN_DATA_ENTITIES)
        losses = {}
        for text, annotations in TRAIN_DATA_ENTITIES:
            doc = nlp.make_doc(text)
            example = Example.from_dict(doc, annotations)
            nlp.update([example], sgd=optimizer, losses=losses)

        # Afficher la progression tous les 10 itérations
        if (i + 1) % 10 == 0:
            test_doc = nlp("je cherche la salle A")
            ents = [(e.text, e.label_) for e in test_doc.ents]
            print(f"Iteration {i+1}/{n_iter} - Loss: {losses['ner']:.4f} - Test ents: {ents}")

    # ÉTAPE 3 : Ajouter l'entity_ruler APRÈS l'entraînement, en mode complémentaire
    print("\n📋 Ajout de l'Entity Ruler...")
    ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": False})

    patterns = []
    for a in ACTIVITIES:
        patterns.append({"label": "ACTIVITY", "pattern": a})
    for l in LOCATIONS:
        patterns.append({"label": "LOCATION", "pattern": l})
    ruler.add_patterns(patterns)

    # ÉTAPE 4 : Vérification finale
    print("\n✅ Vérification du pipeline final:")
    print("Pipes:", nlp.pipe_names)
    print("EntityRuler patterns:", len(ruler.patterns))

    # Tests de sanité
    test_cases = [
        "où est le secrétariat",
        "je veux faire du football",
        "réserver un cours de yoga",
        "je cherche salle A",
        "je cherche la salle natation",
    ]

    print("\n🧪 Tests:")
    for test_text in test_cases:
        doc = nlp(test_text)
        ents = [(e.text, e.label_) for e in doc.ents]
        print(f"  '{test_text}' → {ents}")

    # ÉTAPE 5 : Sauvegarder le modèle complet
    nlp.to_disk(Path(output_dir))
    print(f"\n💾 Modèle entities sauvegardé dans {output_dir}")
    print(f"   - NER entraîné pour apprendre des patterns")
    print(f"   - Entity Ruler ajouté pour couvrir les cas connus")


if __name__ == "__main__":
    train()
