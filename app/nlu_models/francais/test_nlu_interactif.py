"""
Test interactif du pipeline NLU.
Tape une phrase, le script affiche l'intent et les entites detectees.
"""

import spacy

from app.test_model.francais.continuous_learning import (
    add_blocked_entity,
    entity_blocklist_count,
    entity_hints_count,
    format_intents,
    is_valid_intent,
    log_interaction,
    pending_count,
    validated_count,
    record_entity_correction,
)
from app.test_model.francais.nlu_train import traiter_requete


try:
    _INTENT_MODEL = spacy.load("models/nlu_model")
except OSError:
    _INTENT_MODEL = None


def afficher_resultat(phrase: str) -> None:
    """Affiche proprement le resultat NLU pour une phrase."""
    resultat = traiter_requete(phrase)

    print("\n" + "-" * 60)
    print(f"Phrase      : {phrase}")
    print(f"Intent      : {resultat['intent']}")
    print(f"Confiance   : {resultat['confidence']:.0%}")
    print("Entites:")

    entites = resultat.get("entites", {})
    if not entites:
        print("  (aucune)")
        return

    has_values = False
    for cle, valeurs in entites.items():
        if valeurs:
            has_values = True
            print(f"  - {cle}: {valeurs}")

    if not has_values:
        print("  (aucune)")


def _top_intents(phrase: str, top_k: int = 3) -> list[tuple[str, float]]:
    if _INTENT_MODEL is None:
        return []
    doc = _INTENT_MODEL(phrase)
    ordered = sorted(doc.cats.items(), key=lambda x: x[1], reverse=True)
    return [(intent, float(score)) for intent, score in ordered[:top_k]]


def demander_feedback(phrase: str, intent: str, confidence: float, entities: dict) -> None:
    """
    Journalise l'interaction et laisse l'utilisateur valider/corriger l'intent.
    """
    top3 = _top_intents(phrase, top_k=3)

    if top3:
        top3_txt = " | ".join(f"{i}:{s:.0%}" for i, s in top3)
        print(f"Top intents  : {top3_txt}")

    reponse = input("Prediction correcte ? (o/n/s) ").strip().lower()

    if reponse in {"o", "oui", "y", "yes"}:
        log_interaction(
            text=phrase,
            predicted_intent=intent,
            confidence=confidence,
            top_intents=top3,
            entities=entities,
            corrected_intent=intent,
        )
        print("Feedback     : valide et ajoute pour le prochain entrainement")
        return

    if reponse in {"n", "non"}:
        print(f"Intents dispo: {format_intents()}")
        correction = input("Intent correct: ").strip()
        if not is_valid_intent(correction):
            print("Intent invalide -> interaction stockee en pending")
            log_interaction(
                text=phrase,
                predicted_intent=intent,
                confidence=confidence,
                top_intents=top3,
                entities=entities,
                corrected_intent=None,
            )
            return

        log_interaction(
            text=phrase,
            predicted_intent=intent,
            confidence=confidence,
            top_intents=top3,
            entities=entities,
            corrected_intent=correction,
        )
        print("Feedback     : corrige et ajoute pour le prochain entrainement")
        return

    log_interaction(
        text=phrase,
        predicted_intent=intent,
        confidence=confidence,
        top_intents=top3,
        entities=entities,
        corrected_intent=None,
    )
    print("Feedback     : mis en pending pour revision manuelle")


def demander_feedback_entites(phrase: str, resultat: dict) -> None:
    """
    Permet de bannir des entites fausses positives pour les futures requetes.
    """
    entites = resultat.get("entites", {})
    if not entites:
        return

    valeurs = []
    for key, vals in entites.items():
        for value in vals or []:
            valeurs.append((key, value))

    if not valeurs:
        return

    rep = input("Entites correctes ? (o/n) ").strip().lower()
    if rep not in {"n", "non"}:
        return

    action = input("Action: bannir (b) ou ajouter manquante (a) ? ").strip().lower()

    if action in {"a", "add", "ajouter"}:
        print("Types dispo: sports, lieux, temps, nombres")
        key = input("Type entite: ").strip().lower()
        value = input("Valeur manquante: ").strip()
        added = record_entity_correction(
            text=phrase,
            predicted_intent=resultat.get("intent", "inconnu"),
            confidence=float(resultat.get("confidence", 0.0)),
            top_intents=_top_intents(phrase, top_k=3),
            entities=entites,
            entity_key=key,
            entity_value=value,
        )
        if added:
            print(f"Entite ajoutee et enregistree pour NER: {key} = {value}")
        else:
            print("Impossible d'ajouter (type invalide ou vide).")
        return

    print("Entites detectees:")
    for idx, (key, value) in enumerate(valeurs, start=1):
        print(f"  {idx}. {key} = {value}")

    choix = input("Numero a bannir (ou vide pour annuler): ").strip()
    if not choix:
        return

    if not choix.isdigit():
        print("Choix invalide.")
        return

    index = int(choix) - 1
    if index < 0 or index >= len(valeurs):
        print("Numero hors plage.")
        return

    key, value = valeurs[index]
    added = add_blocked_entity(key, value)
    if added:
        print(f"Entite bannie: {key} = {value}")
    else:
        print("Entite deja bannie ou invalide.")


def main() -> None:
    print("=" * 60)
    print("Test NLU interactif")
    print("Tape une phrase puis appuie sur Entree.")
    print("Commandes de sortie: quit, exit, q")
    print(f"Feedbacks valides : {validated_count()} | pending : {pending_count()}")
    print(f"Entites bannies   : {entity_blocklist_count()}")
    print(f"Entites ajoutees  : {entity_hints_count()}")
    print("=" * 60)

    while True:
        try:
            phrase = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if not phrase:
            print("Phrase vide, essaie encore.")
            continue

        if phrase.lower() in {"quit", "exit", "q"}:
            print("Au revoir.")
            break

        resultat = traiter_requete(phrase)
        afficher_resultat(phrase)
        demander_feedback(
            phrase,
            resultat["intent"],
            float(resultat["confidence"]),
            resultat.get("entites", {}),
        )
        demander_feedback_entites(phrase, resultat)


if __name__ == "__main__":
    main()
