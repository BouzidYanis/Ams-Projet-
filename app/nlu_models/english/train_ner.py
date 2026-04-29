"""
Train English NER model with continuous feedback data.
"""

import argparse
import random
from pathlib import Path

import spacy
from spacy.training import Example
from spacy.util import compounding, minibatch

from app.nlu_models.english.continuous_learning import validated_to_ner_training_data
from app.nlu_models.english.training_data_ner import ENTITY_LABELS, NER_TRAINING_DATA


def split_data(data: list, ratio: float = 0.85):
    random.shuffle(data)
    cut = int(len(data) * ratio)
    return data[:cut], data[cut:]


def _load_base_model():
    for name in ("en_core_web_md", "en_core_web_sm"):
        try:
            return spacy.load(name)
        except OSError:
            continue
    return spacy.blank("en")


def train(n_iter: int = 50, output_dir: str | None = None, seed: int = 42):
    if output_dir is None:
        output_dir = str(Path(__file__).parent.parent / "models" / "ner_model_en")

    random.seed(seed)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    nlp = _load_base_model()

    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    for label in ENTITY_LABELS:
        ner.add_label(label)

    train_data, _eval_data = split_data(
        list(NER_TRAINING_DATA) + validated_to_ner_training_data(), ratio=0.85
    )

    other_pipes = [p for p in nlp.pipe_names if p != "ner"]
    with nlp.select_pipes(disable=other_pipes):
        optimizer = nlp.begin_training()

        for i in range(1, n_iter + 1):
            random.shuffle(train_data)
            losses: dict[str, float] = {}

            for batch in minibatch(train_data, size=compounding(4.0, 32.0, 1.001)):
                examples = []
                for text, annots in batch:
                    doc = nlp.make_doc(text)
                    try:
                        examples.append(Example.from_dict(doc, annots))
                    except Exception:
                        continue
                if examples:
                    nlp.update(examples, sgd=optimizer, drop=0.35, losses=losses)

            if i % 10 == 0 or i == 1:
                print(f"iter {i:3d} | ner loss {losses.get('ner', 0):.4f}")

    nlp.to_disk(output_path)
    return spacy.load(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train English NER model")
    parser.add_argument("--iter", type=int, default=50)
    parser.add_argument("--output", type=str, default="models/ner_model_en")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train(n_iter=args.iter, output_dir=args.output, seed=args.seed)
