import random
from pathlib import Path

import spacy
from spacy.training.example import Example

# More varied training data
TRAIN_DATA_ENTITIES = [
    ("je veux faire du football", {"entities": [(17, 25, "ACTIVITY")]}),
    ("je voudrais faire du basketball", {"entities": [(21, 31, "ACTIVITY")]}),
    ("réserver un cours de fitness", {"entities": [(21, 28, "ACTIVITY")]}),
    ("inscription au futsal", {"entities": [(15, 21, "ACTIVITY")]}),
    ("je veux jouer au basket", {"entities": [(17, 23, "ACTIVITY")]}),
    ("est-ce qu'il y a du tennis ?", {"entities": [(20, 26, "ACTIVITY")]}),

    ("où est la salle de sport", {"entities": [(10, 24, "LOCATION")]}),
    ("où est la salle", {"entities": [(10, 15, "LOCATION")]}),
    ("où se trouve le vestiaire", {"entities": [(16, 25, "LOCATION")]}),
    ("peux-tu m'orienter vers le vestiaire", {"entities": [(27, 36, "LOCATION")]}),
    ("comment aller au terrain", {"entities": [(17, 24, "LOCATION")]}),
    ("je cherche l'accueil", {"entities": [(13, 20, "LOCATION")]}),
    ("où est le secrétariat", {"entities": [(10, 21, "LOCATION")]}),
]

ACTIVITIES = ["yoga", "fitness", "basket", "basketball", "tennis", "futsal", "natation", "football"]
LOCATIONS = ["salle", "salle de sport", "vestiaire", "terrain", "accueil", "secrétariat"]


def train(output_dir: str = "entity_model", n_iter: int = 40, seed: int = 42):
    random.seed(seed)

    nlp = spacy.blank("fr")

    # Add a rule-based component first to boost precision for known activities/locations
    ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": True})
    patterns = []
    for a in ACTIVITIES:
        patterns.append({"label": "ACTIVITY", "pattern": a})
    for l in LOCATIONS:
        patterns.append({"label": "LOCATION", "pattern": l})
    ruler.add_patterns(patterns)

    # Debug: ensure patterns are present
    try:
        print("Pipes:", nlp.pipe_names)
        print("EntityRuler patterns:", len(ruler.patterns))
        dbg_doc = nlp("où est le secrétariat")
        print("Sanity ents:", [(e.text, e.label_) for e in dbg_doc.ents])
    except Exception as e:
        print("EntityRuler debug failed:", e)

    ner = nlp.add_pipe("ner")

    for _, annotations in TRAIN_DATA_ENTITIES:
        for _, _, label in annotations["entities"]:
            ner.add_label(label)

    optimizer = nlp.initialize()

    for i in range(n_iter):
        random.shuffle(TRAIN_DATA_ENTITIES)
        losses = {}

        for text, annotations in TRAIN_DATA_ENTITIES:
            doc = nlp.make_doc(text)
            example = Example.from_dict(doc, annotations)
            nlp.update([example], sgd=optimizer, losses=losses)

        print(f"Iteration {i+1}/{n_iter} - Loss: {losses}")

    nlp.to_disk(Path(output_dir))
    print(f"✅ Modèle entities sauvegardé dans {output_dir}")


if __name__ == "__main__":
    train()
