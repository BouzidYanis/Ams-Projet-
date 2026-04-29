"""
train_ner.py
============
Entraîne un composant NER spaCy pour reconnaître les entités :
    SPORT · LIEU · DATE · HEURE · NOMBRE

Le modèle est sauvegardé dans models/ner_model/ et peut ensuite
être utilisé directement dans nlu_train.py à la place du Matcher.

Usage :
    python train_ner.py
    python train_ner.py --iter 50 --output models/ner_model
"""

import argparse
import random
import warnings
from pathlib import Path

import spacy
from spacy.training import Example
from spacy.util import minibatch, compounding

from app.test_model.francais.continuous_learning import validated_to_ner_training_data
from app.test_model.francais.training_data_ner import ENTITY_LABELS, NER_TRAINING_DATA

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def validate_data(data: list) -> list:
    """
    Vérifie que tous les offsets sont valides et qu'il n'y a pas
    de chevauchement. Supprime les exemples invalides.
    """
    clean = []
    for text, annots in data:
        ents = annots.get("entities", [])
        valid = True
        seen_offsets = []

        for start, end, label in ents:
            # Offset hors bornes
            if start < 0 or end > len(text) or start >= end:
                print(f"  [WARN] Offset invalide [{start}:{end}] dans « {text} »")
                valid = False
                break
            # Chevauchement
            for s2, e2, _ in seen_offsets:
                if not (end <= s2 or start >= e2):
                    print(f"  [WARN] Chevauchement [{start}:{end}] / [{s2}:{e2}] dans « {text} »")
                    valid = False
                    break
            if not valid:
                break
            seen_offsets.append((start, end, label))

        if valid:
            clean.append((text, annots))

    removed = len(data) - len(clean)
    if removed:
        print(f"  [WARN] {removed} exemple(s) supprimé(s) après validation.")
    return clean


def split_data(data: list, ratio: float = 0.85) -> tuple:
    random.shuffle(data)
    cut = int(len(data) * ratio)
    return data[:cut], data[cut:]


def evaluate_ner(nlp, eval_data: list) -> dict:
    """
    Calcule precision / recall / F1 par label.
    """
    tp: dict[str, int] = {lbl: 0 for lbl in ENTITY_LABELS}
    fp: dict[str, int] = {lbl: 0 for lbl in ENTITY_LABELS}
    fn: dict[str, int] = {lbl: 0 for lbl in ENTITY_LABELS}

    for text, annots in eval_data:
        doc = nlp(text)
        gold_ents = set(
            (text[s:e], s, e, lbl) for s, e, lbl in annots.get("entities", [])
        )
        pred_ents = set(
            (ent.text, ent.start_char, ent.end_char, ent.label_) for ent in doc.ents
        )

        for ent in pred_ents:
            lbl = ent[3]
            if lbl in tp:
                if ent in gold_ents:
                    tp[lbl] += 1
                else:
                    fp[lbl] += 1

        for ent in gold_ents:
            lbl = ent[3]
            if lbl in fn and ent not in pred_ents:
                fn[lbl] += 1

    results = {}
    total_tp = total_fp = total_fn = 0

    for lbl in ENTITY_LABELS:
        p = tp[lbl] / (tp[lbl] + fp[lbl]) if (tp[lbl] + fp[lbl]) > 0 else 0.0
        r = tp[lbl] / (tp[lbl] + fn[lbl]) if (tp[lbl] + fn[lbl]) > 0 else 0.0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        results[lbl] = {"p": round(p, 3), "r": round(r, 3), "f1": round(f, 3)}
        total_tp += tp[lbl]
        total_fp += fp[lbl]
        total_fn += fn[lbl]

    # Micro F1 global
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = (
        2 * micro_p * micro_r / (micro_p + micro_r)
        if (micro_p + micro_r) > 0
        else 0.0
    )
    results["__micro__"] = {
        "p": round(micro_p, 3),
        "r": round(micro_r, 3),
        "f1": round(micro_f1, 3),
    }
    return results


def print_metrics(metrics: dict):
    print(f"\n  {'Label':<28} {'Précision':>10} {'Rappel':>10} {'F1':>10}")
    print("  " + "─" * 62)
    for lbl in ENTITY_LABELS:
        m = metrics[lbl]
        print(f"  {lbl:<28} {m['p']:>10.1%} {m['r']:>10.1%} {m['f1']:>10.1%}")
    print("  " + "─" * 62)
    m = metrics["__micro__"]
    print(f"  {'MICRO (global)':<28} {m['p']:>10.1%} {m['r']:>10.1%} {m['f1']:>10.1%}")


# ─────────────────────────────────────────────────────────────────
# Entraînement
# ─────────────────────────────────────────────────────────────────

def train(n_iter: int = 50, output_dir: str = None, seed: int = 42):
    if output_dir is None:
        output_dir = str(Path(__file__).parent.parent / "models" / "ner_model")
    random.seed(seed)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── 1. Valider le dataset ─────────────────────────────────────
    feedback_ner = validated_to_ner_training_data()
    all_ner_data = list(NER_TRAINING_DATA) + feedback_ner

    print(f"► Validation du dataset ({len(all_ner_data)} exemples) …")
    if feedback_ner:
        print(f"  +{len(feedback_ner)} exemple(s) NER issus du feedback valide")

    clean_data = validate_data(all_ner_data)
    print(f"  {len(clean_data)} exemples valides conservés.")

    train_data, eval_data = split_data(clean_data, ratio=0.85)
    print(f"  {len(train_data)} train  |  {len(eval_data)} eval\n")

    # ── 2. Charger le modèle de base ─────────────────────────────
    print("► Chargement de fr_core_news_md …")
    nlp = spacy.load("fr_core_news_md")

    # ── 3. Configurer le NER ─────────────────────────────────────
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    for label in ENTITY_LABELS:
        ner.add_label(label)

    # ── 4. Optimiseur ─────────────────────────────────────────────
    other_pipes = [p for p in nlp.pipe_names if p != "ner"]

    with nlp.select_pipes(disable=other_pipes):
        optimizer = nlp.begin_training()

        # Taille de batch progressivement croissante (recommandé spaCy)
        batch_sizes = compounding(4.0, 32.0, 1.001)

        print(f"► Entraînement ({n_iter} itérations) …\n")
        best_f1 = 0.0

        for i in range(1, n_iter + 1):
            random.shuffle(train_data)
            losses: dict[str, float] = {}

            batches = minibatch(train_data, size=batch_sizes)
            for batch in batches:
                examples = []
                for text, annots in batch:
                    doc = nlp.make_doc(text)
                    try:
                        ex = Example.from_dict(doc, annots)
                        examples.append(ex)
                    except Exception as err:
                        print(f"  [WARN] Exemple ignoré : {text!r} → {err}")
                if examples:
                    nlp.update(examples, sgd=optimizer, drop=0.35, losses=losses)

            # Affichage tous les 10 tours
            if i % 10 == 0 or i == 1:
                metrics = evaluate_ner(nlp, eval_data)
                f1 = metrics["__micro__"]["f1"]
                marker = " ◄ meilleur" if f1 > best_f1 else ""
                print(
                    f"  iter {i:3d} | loss {losses.get('ner', 0):.4f} | "
                    f"F1 micro {f1:.2%}{marker}"
                )
                if f1 > best_f1:
                    best_f1 = f1
                    nlp.to_disk(output_path)

    # ── 5. Rapport final ──────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f"  Meilleur F1 micro : {best_f1:.2%}")
    print(f"  Modèle sauvegardé : {output_path.resolve()}")
    print(f"{'─'*55}")

    best_nlp = spacy.load(output_path)
    metrics = evaluate_ner(best_nlp, eval_data)
    print("\n► Métriques finales par label :")
    print_metrics(metrics)

    return best_nlp


# ─────────────────────────────────────────────────────────────────
# Test rapide
# ─────────────────────────────────────────────────────────────────

def quick_test(nlp):
    samples = [
        "réserver un cours de natation demain à 9h",
        "yoga lundi matin en salle B",
        "cours de fitness à 18h en salle A ce soir",
        "annuler ma réservation de tennis samedi à 14h",
        "disponibilité piscine ce week-end le matin",
        "zumba jeudi soir 2 places",
        "réserver salle C mardi à 10h pour 3 personnes",
        "où sont les vestiaires",
        "musculation demain matin",
        "squash samedi matin 2 joueurs",
    ]

    print("\n► Test rapide :\n")
    for text in samples:
        doc = nlp(text)
        ents_str = "  ".join(
            f"[{ent.text}]→{ent.label_}" for ent in doc.ents
        ) or "(aucune)"
        print(f"  « {text} »")
        print(f"    {ents_str}\n")


# ─────────────────────────────────────────────────────────────────
# Entrée principale
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entraîne le modèle NER spaCy.")
    parser.add_argument("--iter",   type=int, default=50,               help="Nombre d'itérations (défaut : 50)")
    parser.add_argument("--output", type=str, default="models/ner_model", help="Répertoire de sauvegarde")
    parser.add_argument("--seed",   type=int, default=42,               help="Graine aléatoire")
    args = parser.parse_args()

    best_model = train(n_iter=args.iter, output_dir=args.output, seed=args.seed)
    quick_test(best_model)