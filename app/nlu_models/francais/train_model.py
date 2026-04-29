"""
train_model.py
==============
Entraîne un TextCategorizer spaCy (fr_core_news_md) sur les données
de training_data.py et sauvegarde le modèle dans models/nlu_model/.

Usage :
    python train_model.py
    python train_model.py --iter 40 --output models/mon_modele
"""

import argparse
import random
import warnings
from pathlib import Path

import spacy
from spacy.training import Example

from app.nlu_models.francais.continuous_learning import validated_to_training_data
from app.nlu_models.francais.training_data import INTENTS, TRAINING_DATA

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def split_data(data: list, ratio: float = 0.85):
    """Divise les données en train / eval."""
    random.shuffle(data)
    cut = int(len(data) * ratio)
    return data[:cut], data[cut:]


def evaluate(nlp, eval_data: list) -> dict[str, float]:
    """Calcule accuracy + score moyen de confiance sur le jeu d'évaluation."""
    correct = 0
    total = len(eval_data)
    conf_sum = 0.0

    for text, annots in eval_data:
        doc = nlp(text)
        expected = max(annots["cats"], key=annots["cats"].get)
        predicted = max(doc.cats, key=doc.cats.get)
        conf_sum += doc.cats[predicted]
        if predicted == expected:
            correct += 1

    return {
        "accuracy": round(correct / total, 4) if total else 0.0,
        "avg_confidence": round(conf_sum / total, 4) if total else 0.0,
        "correct": correct,
        "total": total,
    }


def print_confusion(nlp, eval_data: list):
    """Affiche les erreurs de classification."""
    errors = []
    for text, annots in eval_data:
        doc = nlp(text)
        expected = max(annots["cats"], key=annots["cats"].get)
        predicted = max(doc.cats, key=doc.cats.get)
        if predicted != expected:
            conf = doc.cats[predicted]
            errors.append((text, expected, predicted, conf))

    if not errors:
        print("  ✓ Aucune erreur sur le jeu d'évaluation !")
        return

    print(f"  ✗ {len(errors)} erreur(s) :")
    for text, exp, pred, conf in errors:
        print(f"    [{exp}] → [{pred}] ({conf:.2f})  « {text} »")


# ─────────────────────────────────────────────────────────────────
# Entraînement principal
# ─────────────────────────────────────────────────────────────────

def train(n_iter: int = 40, output_dir: str = None, seed: int = 42):
    if output_dir is None:
        output_dir = str(Path(__file__).parent.parent / "models" / "nlu_model")
    random.seed(seed)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── 1. Charger le modèle de base ─────────────────────────────
    print("► Chargement de fr_core_news_md …")
    nlp = spacy.load("fr_core_news_md")

    # ── 2. Ajouter le TextCategorizer ────────────────────────────
    if "textcat" in nlp.pipe_names:
        textcat = nlp.get_pipe("textcat")
    else:
        # "ensemble" combine bag-of-words + CNN → bon compromis
        textcat = nlp.add_pipe(
            "textcat",
            config={"model": {"@architectures": "spacy.TextCatEnsemble.v2"}},
            last=True,
        )

    for intent in INTENTS:
        textcat.add_label(intent)

    # ── 3. Découper train / eval ──────────────────────────────────
    base_data = list(TRAINING_DATA)
    feedback_data = validated_to_training_data()

    if feedback_data:
        print(f"► Feedback valide detecte : +{len(feedback_data)} exemple(s)")

    all_data = base_data + feedback_data
    train_data, eval_data = split_data(all_data, ratio=0.85)
    print(f"► Données : {len(train_data)} train  |  {len(eval_data)} eval")

    # ── 4. Initialiser l'optimiseur ───────────────────────────────
    # On désactive tous les composants sauf textcat pour ne pas les modifier
    other_pipes = [p for p in nlp.pipe_names if p != "textcat"]

    with nlp.select_pipes(disable=other_pipes):
        optimizer = nlp.begin_training()

        print(f"\n► Entraînement ({n_iter} itérations) …\n")
        best_acc = 0.0

        for i in range(1, n_iter + 1):
            random.shuffle(train_data)
            losses: dict[str, float] = {}

            # Batches de taille 8
            for j in range(0, len(train_data), 8):
                batch = train_data[j : j + 8]
                examples = []
                for text, annots in batch:
                    doc = nlp.make_doc(text)
                    examples.append(Example.from_dict(doc, annots))
                nlp.update(examples, sgd=optimizer, drop=0.3, losses=losses)

            # Affichage tous les 5 tours
            if i % 5 == 0 or i == 1:
                metrics = evaluate(nlp, eval_data)
                marker = " ◄ meilleur" if metrics["accuracy"] > best_acc else ""
                print(
                    f"  iter {i:3d} | loss {losses.get('textcat', 0):.4f} | "
                    f"acc {metrics['accuracy']:.2%} | "
                    f"conf moy {metrics['avg_confidence']:.2%}{marker}"
                )
                # Sauvegarder le meilleur modèle
                if metrics["accuracy"] > best_acc:
                    best_acc = metrics["accuracy"]
                    nlp.to_disk(output_path)

    # ── 5. Rapport final ──────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f"  Meilleure accuracy : {best_acc:.2%}")
    print(f"  Modèle sauvegardé  : {output_path.resolve()}")
    print(f"{'─'*55}\n")

    # Recharger le meilleur modèle pour l'évaluation finale
    best_nlp = spacy.load(output_path)
    final = evaluate(best_nlp, eval_data)
    print("► Évaluation finale (meilleur modèle) :")
    print(f"  Accuracy : {final['accuracy']:.2%}  ({final['correct']}/{final['total']})")
    print(f"  Confiance moyenne : {final['avg_confidence']:.2%}")
    print()
    print_confusion(best_nlp, eval_data)

    return best_nlp


# ─────────────────────────────────────────────────────────────────
# Test rapide après entraînement
# ─────────────────────────────────────────────────────────────────

def quick_test(nlp):
    """Quelques phrases de contrôle manuel."""
    samples = [
        ("bonjour !",                           "salutation"),
        ("c'est combien le yoga",               "ask_pricing"),
        ("je veux annuler mon cours",           "cancel_booking"),
        ("vous êtes ouverts demain",            "demander_heure"),
        ("où sont les vestiaires",              "demander_lieu"),
        ("je voudrais réserver la salle A",     "reserver"),
        ("mes réservations",                    "demander_mes_reservations"),
        ("créneaux disponibles natation",       "ask_available_slots"),
        ("tu es un robot",                      "qui"),
        ("la météo aujourd'hui",                "inconnu"),
    ]

    print("\n► Test rapide :")
    print(f"  {'Phrase':<45} {'Attendu':<28} {'Prédit':<28} {'Conf':>6}")
    print("  " + "─" * 112)

    for text, expected in samples:
        doc = nlp(text)
        predicted = max(doc.cats, key=doc.cats.get)
        conf = doc.cats[predicted]
        ok = "✓" if predicted == expected else "✗"
        print(f"  {ok} {text:<43} {expected:<28} {predicted:<28} {conf:>5.0%}")


# ─────────────────────────────────────────────────────────────────
# Entrée principale
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entraîne le modèle NLU spaCy.")
    parser.add_argument("--iter",   type=int, default=40,              help="Nombre d'itérations (défaut : 40)")
    parser.add_argument("--output", type=str, default="models/nlu_model", help="Répertoire de sauvegarde")
    parser.add_argument("--seed",   type=int, default=42,              help="Graine aléatoire")
    args = parser.parse_args()

    best_model = train(n_iter=args.iter, output_dir=args.output, seed=args.seed)
    quick_test(best_model)