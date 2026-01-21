import random
from pathlib import Path

import spacy
from spacy.training.example import Example

# Expanded dataset (keep it small but more varied). Each example will be converted
# to exclusive classes across all labels.
RAW_TRAIN_DATA = [
    # greeting
    ("bonjour", "greeting"),
    ("salut", "greeting"),
    ("bonsoir", "greeting"),
    ("salut robot", "greeting"),
    ("hello", "greeting"),

    # ask_hours
    ("quels sont vos horaires", "ask_hours"),
    ("quels sont les horaires d'ouverture", "ask_hours"),
    ("à quelle heure vous ouvrez", "ask_hours"),
    ("à quelle heure vous fermez", "ask_hours"),
    ("c'est ouvert aujourd'hui", "ask_hours"),
    ("vous êtes ouverts le dimanche ?", "ask_hours"),

    # ask_activities
    ("quelles activités proposez-vous", "ask_activities"),
    ("quels sports sont disponibles", "ask_activities"),
    ("quelles activités sont disponibles", "ask_activities"),
    ("le programme des cours", "ask_activities"),
    ("vous proposez du yoga ?", "ask_activities"),
    ("il y a des cours de fitness ?", "ask_activities"),

    # navigate
    ("où est la salle de sport", "navigate"),
    ("où se trouve le vestiaire", "navigate"),
    ("peux-tu m'orienter vers le vestiaire", "navigate"),
    ("comment aller au terrain", "navigate"),
    ("je cherche l'accueil", "navigate"),
    ("où est le secrétariat", "navigate"),

    # book_activity
    ("je veux m'inscrire au yoga", "book_activity"),
    ("je voudrais réserver un cours de fitness", "book_activity"),
    ("réserver un cours", "book_activity"),
    ("faire une réservation", "book_activity"),
    ("inscription au basket", "book_activity"),
    ("je veux faire du football", "book_activity"),

    # who_are_you
    ("qui es-tu", "who_are_you"),
    ("tu es qui", "who_are_you"),
    ("quel est ton rôle", "who_are_you"),
    ("tu sers à quoi", "who_are_you"),
]


def _to_exclusive_cats(data: list[tuple[str, str]], labels: list[str]):
    out = []
    for text, lab in data:
        cats = {l: 0.0 for l in labels}
        cats[lab] = 1.0
        out.append((text, {"cats": cats}))
    return out


def train(output_dir: str = "intent_model", n_iter: int = 30, dev_ratio: float = 0.2, seed: int = 42):
    random.seed(seed)

    labels = sorted({lab for _, lab in RAW_TRAIN_DATA})
    examples = RAW_TRAIN_DATA[:]
    random.shuffle(examples)

    split = max(1, int(len(examples) * (1.0 - dev_ratio)))
    train_raw = examples[:split]
    dev_raw = examples[split:]

    train_data = _to_exclusive_cats(train_raw, labels)
    dev_data = _to_exclusive_cats(dev_raw, labels)

    nlp = spacy.blank("fr")

    textcat = nlp.add_pipe(
        "textcat",
        config={
            "model": {
                "@architectures": "spacy.TextCatBOW.v3",
                "exclusive_classes": True,
                "ngram_size": 2,
                "no_output_layer": False,
            }
        },
    )

    for label in labels:
        textcat.add_label(label)

    optimizer = nlp.initialize()

    best_dev_loss = float("inf")
    patience = 4
    bad_epochs = 0

    for i in range(n_iter):
        random.shuffle(train_data)
        losses = {}

        for text, annotations in train_data:
            doc = nlp.make_doc(text)
            example = Example.from_dict(doc, annotations)
            nlp.update([example], sgd=optimizer, losses=losses)

        # Simple dev loss (same update call but with no optimizer step)
        dev_losses = {}
        for text, annotations in dev_data:
            doc = nlp.make_doc(text)
            example = Example.from_dict(doc, annotations)
            nlp.update([example], losses=dev_losses, sgd=None)

        train_loss = float(losses.get("textcat", 0.0))
        dev_loss = float(dev_losses.get("textcat", 0.0))
        print(f"Iteration {i+1}/{n_iter} - train_loss={train_loss:.4f} dev_loss={dev_loss:.4f}")

        if dev_data:
            if dev_loss + 1e-6 < best_dev_loss:
                best_dev_loss = dev_loss
                bad_epochs = 0
            else:
                bad_epochs += 1
                if bad_epochs >= patience:
                    print("Early stopping: dev loss not improving")
                    break

    nlp.to_disk(Path(output_dir))
    print(f"✅ Modèle intent sauvegardé dans : {output_dir}")


if __name__ == "__main__":
    train()
