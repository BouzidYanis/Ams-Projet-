"""
Train English intent model (TextCategorizer) with continuous feedback.
"""

import argparse
import random
from pathlib import Path

import spacy
from spacy.training import Example

from app.nlu_models.english.continuous_learning import validated_to_training_data
from app.nlu_models.english.training_data import INTENTS, TRAINING_DATA


def split_data(data: list, ratio: float = 0.85):
    random.shuffle(data)
    cut = int(len(data) * ratio)
    return data[:cut], data[cut:]


def evaluate(nlp, eval_data: list) -> dict[str, float]:
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
    }


def _load_base_model():
    for name in ("en_core_web_md", "en_core_web_sm"):
        try:
            return spacy.load(name)
        except OSError:
            continue
    return spacy.blank("en")


def train(n_iter: int = 40, output_dir: str | None = None, seed: int = 42):
    if output_dir is None:
        output_dir = str(Path(__file__).parent.parent / "models" / "nlu_model_en")

    random.seed(seed)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    nlp = _load_base_model()

    if "textcat" in nlp.pipe_names:
        textcat = nlp.get_pipe("textcat")
    else:
        textcat = nlp.add_pipe(
            "textcat",
            config={"model": {"@architectures": "spacy.TextCatEnsemble.v2"}},
            last=True,
        )

    for intent in INTENTS:
        textcat.add_label(intent)

    all_data = list(TRAINING_DATA) + validated_to_training_data()
    train_data, eval_data = split_data(all_data, ratio=0.85)

    other_pipes = [p for p in nlp.pipe_names if p != "textcat"]
    with nlp.select_pipes(disable=other_pipes):
        optimizer = nlp.begin_training()
        best_acc = 0.0

        for i in range(1, n_iter + 1):
            random.shuffle(train_data)
            losses: dict[str, float] = {}

            for j in range(0, len(train_data), 8):
                batch = train_data[j : j + 8]
                examples = []
                for text, annots in batch:
                    doc = nlp.make_doc(text)
                    examples.append(Example.from_dict(doc, annots))
                nlp.update(examples, sgd=optimizer, drop=0.3, losses=losses)

            if i % 5 == 0 or i == 1:
                metrics = evaluate(nlp, eval_data)
                if metrics["accuracy"] > best_acc:
                    best_acc = metrics["accuracy"]
                    nlp.to_disk(output_path)
                print(
                    f"iter {i:3d} | loss {losses.get('textcat', 0):.4f} | "
                    f"acc {metrics['accuracy']:.2%}"
                )

    return spacy.load(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train English NLU intent model")
    parser.add_argument("--iter", type=int, default=40)
    parser.add_argument("--output", type=str, default="models/nlu_model_en")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train(n_iter=args.iter, output_dir=args.output, seed=args.seed)
