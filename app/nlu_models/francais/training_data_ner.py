"""
training_data_ner.py
====================
Dataset d'entraînement pour la reconnaissance d'entités nommées (NER).

Entités reconnues :
    SPORT    → natation, yoga, fitness, tennis …
    LIEU     → vestiaires, salle A, piscine, accueil …
    DATE     → lundi, demain, ce week-end, le 5 mai …
    HEURE    → 9h, 14h30, matin, soir …
    NOMBRE   → 2, 10, une place …

Format spaCy :
    (texte, {"entities": [(start, end, label), ...]})
    Les offsets sont des indices de caractères dans le texte.
"""

# ─────────────────────────────────────────────────────────────────
# Entités reconnues
# ─────────────────────────────────────────────────────────────────
ENTITY_LABELS = ["SPORT", "LIEU", "DATE", "HEURE", "NOMBRE"]


# ─────────────────────────────────────────────────────────────────
# Helper : calcule automatiquement les offsets d'une sous-chaîne
# ─────────────────────────────────────────────────────────────────
def e(text: str, span: str, label: str) -> tuple[int, int, str]:
    """Retourne (start, end, label) pour la première occurrence de `span` dans `text`."""
    start = text.index(span)
    return (start, start + len(span), label)


def entities(*items) -> dict:
    return {"entities": list(items)}


# ─────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────
def build_training_data() -> list[tuple[str, dict]]:
    data = []

    # ── SPORT ─────────────────────────────────────────────────────
    samples_sport = [
        "je voudrais réserver un cours de natation",
        "est-ce qu'il y a de la natation demain",
        "je veux m'inscrire au yoga",
        "le cours de yoga est à quelle heure",
        "horaires du fitness",
        "réserver une séance de fitness ce soir",
        "je cherche un cours de tennis",
        "disponibilité pour le tennis samedi",
        "cours de badminton disponibles",
        "annuler mon cours de badminton",
        "je voudrais faire de la musculation",
        "salle de musculation ouverte le dimanche",
        "séance de pilates ce matin",
        "prendre un cours de pilates lundi",
        "inscription zumba jeudi soir",
        "il y a de la zumba cette semaine",
        "cours d'aquagym disponibles",
        "réserver aquagym demain matin",
        "je fais du cardio le matin",
        "une place pour le cardio de 18h",
        "cours de stretching disponible",
        "annuler mon stretching de lundi",
        "séance de danse ce soir",
        "cours de danse pour débutants",
        "je m'inscris au squash",
        "terrain de squash disponible samedi",
        "pratiquer le jogging en salle",
        "cours de running disponibles",
        "match de basket organisé ce soir",
        "terrain de basket disponible demain",
    ]

    # Sports supplémentaires
    samples_sport += [
        "je voudrais faire de la boxe",
        "cours de boxe disponibles",
        "inscription au spinning",
        "réserver une séance de spinning",
        "horaires du crossfit",
        "je veux m'inscrire au crossfit",
        "un cours de handball ce soir",
        "terrain de handball disponible",
        "match de volleyball organisé",
        "cours de volleyball pour débutants",
        "séance de judo lundi matin",
        "je pratique le judo",
        "activité d'escalade disponible",
        "cours d'escalade ce week-end",
        "natation synchronisée horaires",
        "inscription natation synchronisée",
        "cours de tennis de table",
        "réserver une table pour le ping pong",
        "je veux faire du vélo en salle",
        "séance de vélo elliptique",
    ]

    for text in samples_sport:
        ents = []
        for sport in ["natation synchronisée", "tennis de table",
                      "natation", "yoga", "fitness", "tennis", "badminton",
                      "musculation", "pilates", "zumba", "aquagym", "cardio",
                      "stretching", "danse", "squash", "jogging", "running", "basket",
                      "boxe", "spinning", "crossfit", "handball", "volleyball",
                      "judo", "escalade", "ping pong"]:
            if sport in text:
                ents.append(e(text, sport, "SPORT"))
        if ents:
            data.append((text, entities(*ents)))

    # ── LIEU ──────────────────────────────────────────────────────
    samples_lieu = [
        ("où sont les vestiaires",                      [e("où sont les vestiaires",                      "vestiaires",       "LIEU")]),
        ("je cherche les vestiaires hommes",             [e("je cherche les vestiaires hommes",             "vestiaires",       "LIEU")]),
        ("direction salle A s'il vous plaît",            [e("direction salle A s'il vous plaît",            "salle A",          "LIEU")]),
        ("je suis en salle A",                           [e("je suis en salle A",                           "salle A",          "LIEU")]),
        ("je veux aller à la salle A",                   [e("je veux aller à la salle A",                   "salle A",          "LIEU")]),
        ("je souhaite aller à la salle A",               [e("je souhaite aller à la salle A",               "salle A",          "LIEU")]),
        ("conduis-moi vers la salle A",                  [e("conduis-moi vers la salle A",                  "salle A",          "LIEU")]),
        ("cours dans la salle B aujourd'hui",            [e("cours dans la salle B aujourd'hui",            "salle B",          "LIEU")]),
        ("réserver la salle B pour demain",              [e("réserver la salle B pour demain",              "salle B",          "LIEU")]),
        ("comment aller à la salle B",                   [e("comment aller à la salle B",                   "salle B",          "LIEU")]),
        ("la salle C est fermée",                        [e("la salle C est fermée",                        "salle C",          "LIEU")]),
        ("je cherche la salle D",                        [e("je cherche la salle D",                        "salle D",          "LIEU")]),
        ("où est la salle E",                            [e("où est la salle E",                            "salle E",          "LIEU")]),
        ("comment aller à la piscine",                   [e("comment aller à la piscine",                   "piscine",          "LIEU")]),
        ("horaires de la piscine",                       [e("horaires de la piscine",                       "piscine",          "LIEU")]),
        ("je veux aller à la piscine",                   [e("je veux aller à la piscine",                   "piscine",          "LIEU")]),
        ("où se trouve l'accueil",                       [e("où se trouve l'accueil",                       "accueil",          "LIEU")]),
        ("rendez-vous à l'accueil",                      [e("rendez-vous à l'accueil",                      "accueil",          "LIEU")]),
        ("les toilettes sont où",                        [e("les toilettes sont où",                        "toilettes",        "LIEU")]),
        ("je cherche les toilettes",                     [e("je cherche les toilettes",                     "toilettes",        "LIEU")]),
        ("où sont les casiers",                          [e("où sont les casiers",                          "casiers",          "LIEU")]),
        ("je n'ai pas de casier",                        [e("je n'ai pas de casier",                        "casier",           "LIEU")]),
        ("direction secrétariat",                        [e("direction secrétariat",                        "secrétariat",      "LIEU")]),
        ("je dois passer au secrétariat",                [e("je dois passer au secrétariat",                "secrétariat",      "LIEU")]),
        ("où est le bassin de natation",                 [e("où est le bassin de natation",                 "bassin",           "LIEU")]),
        ("je veux aller au bassin olympique",            [e("je veux aller au bassin olympique",            "bassin olympique",  "LIEU")]),
        ("court de tennis numéro 2",                     [e("court de tennis numéro 2",                     "court",            "LIEU")]),
        ("réserver le terrain de basket",                [e("réserver le terrain de basket",                "terrain",          "LIEU")]),
        ("salle de fitness fermée ce soir",              [e("salle de fitness fermée ce soir",              "salle de fitness",  "LIEU")]),
        ("où est la salle 3",                            [e("où est la salle 3",                            "salle 3",          "LIEU")]),
        ("réserver la salle 2 pour lundi",               [e("réserver la salle 2 pour lundi",               "salle 2",          "LIEU")]),
        ("où est le parking",                            [e("où est le parking",                            "parking",          "LIEU")]),
        ("comment accéder au parking",                   [e("comment accéder au parking",                   "parking",          "LIEU")]),
        ("je cherche le gymnase",                        [e("je cherche le gymnase",                        "gymnase",          "LIEU")]),
        ("direction gymnase s'il vous plaît",            [e("direction gymnase s'il vous plaît",            "gymnase",          "LIEU")]),
        ("où est le couloir principal",                  [e("où est le couloir principal",                  "couloir",          "LIEU")]),
        ("je dois aller à l'entrée principale",          [e("je dois aller à l'entrée principale",          "entrée principale", "LIEU")]),
        ("où se trouve la salle de yoga",                [e("où se trouve la salle de yoga",                "salle de yoga",    "LIEU")]),
        ("direction salle de danse",                     [e("direction salle de danse",                     "salle de danse",   "LIEU")]),
        ("accès au vestiaire femmes",                    [e("accès au vestiaire femmes",                    "vestiaire",        "LIEU")]),
        ("où sont les douches",                          [e("où sont les douches",                          "douches",          "LIEU")]),
        ("je cherche les douches",                       [e("je cherche les douches",                       "douches",          "LIEU")]),
        ("je veux aller à la réception",                 [e("je veux aller à la réception",                 "réception",        "LIEU")]),
        ("comment aller vers l'accueil",                 [e("comment aller vers l'accueil",                 "accueil",          "LIEU")]),
    ]

    for text, ents in samples_lieu:
        data.append((text, entities(*ents)))

    # ── DATE ──────────────────────────────────────────────────────
    samples_date = [
        ("réserver un cours demain",                 [e("réserver un cours demain",                 "demain",           "DATE")]),
        ("disponible demain matin",                  [e("disponible demain matin",                  "demain",           "DATE")]),
        ("cours lundi prochain",                     [e("cours lundi prochain",                     "lundi",            "DATE")]),
        ("je viendrai lundi",                        [e("je viendrai lundi",                        "lundi",            "DATE")]),
        ("séance mardi soir",                        [e("séance mardi soir",                        "mardi",            "DATE")]),
        ("annuler mardi",                            [e("annuler mardi",                            "mardi",            "DATE")]),
        ("cours de yoga mercredi",                   [e("cours de yoga mercredi",                   "mercredi",         "DATE")]),
        ("je serai là mercredi",                     [e("je serai là mercredi",                     "mercredi",         "DATE")]),
        ("réserver jeudi matin",                     [e("réserver jeudi matin",                     "jeudi",            "DATE")]),
        ("disponible ce vendredi",                   [e("disponible ce vendredi",                   "vendredi",         "DATE")]),
        ("zumba le vendredi soir",                   [e("zumba le vendredi soir",                   "vendredi",         "DATE")]),
        ("ouvert ce week-end",                       [e("ouvert ce week-end",                       "week-end",         "DATE")]),
        ("tennis ce week-end",                       [e("tennis ce week-end",                       "week-end",         "DATE")]),
        ("séance aujourd'hui",                       [e("séance aujourd'hui",                       "aujourd'hui",      "DATE")]),
        ("cours disponible aujourd'hui",             [e("cours disponible aujourd'hui",             "aujourd'hui",      "DATE")]),
        ("inscription pour ce soir",                 [e("inscription pour ce soir",                 "ce soir",          "DATE")]),
        ("fitness ce soir",                          [e("fitness ce soir",                          "ce soir",          "DATE")]),
        ("je viens ce matin",                        [e("je viens ce matin",                        "ce matin",         "DATE")]),
        ("cours ce matin à 9h",                      [e("cours ce matin à 9h",                      "ce matin",         "DATE")]),
        ("natation cette semaine",                   [e("natation cette semaine",                   "cette semaine",    "DATE")]),
        ("horaires cette semaine",                   [e("horaires cette semaine",                   "cette semaine",    "DATE")]),
        ("yoga samedi prochain",                     [e("yoga samedi prochain",                     "samedi",           "DATE")]),
        ("le 5 mai je voudrais réserver",            [e("le 5 mai je voudrais réserver",            "5 mai",            "DATE")]),
        ("réservation pour le 12 juin",              [e("réservation pour le 12 juin",              "12 juin",          "DATE")]),
    ]

    for text, ents in samples_date:
        data.append((text, entities(*ents)))

    # ── HEURE ─────────────────────────────────────────────────────
    samples_heure = [
        ("cours à 9h disponible",                    [e("cours à 9h disponible",                    "9h",       "HEURE")]),
        ("réserver à 9h30",                          [e("réserver à 9h30",                          "9h30",     "HEURE")]),
        ("séance de 10h à 11h",                      [e("séance de 10h à 11h",                      "10h",      "HEURE")]),
        ("fitness à 14h",                            [e("fitness à 14h",                            "14h",      "HEURE")]),
        ("yoga de 14h30",                            [e("yoga de 14h30",                            "14h30",    "HEURE")]),
        ("cours du soir à 18h",                      [e("cours du soir à 18h",                      "18h",      "HEURE")]),
        ("réserver pour 18h30",                      [e("réserver pour 18h30",                      "18h30",    "HEURE")]),
        ("natation à 20h",                           [e("natation à 20h",                           "20h",      "HEURE")]),
        ("le matin c'est possible",                  [e("le matin c'est possible",                  "matin",    "HEURE")]),
        ("séance du matin",                          [e("séance du matin",                          "matin",    "HEURE")]),
        ("cours en soirée",                          [e("cours en soirée",                          "soirée",   "HEURE")]),
        ("disponible le soir",                       [e("disponible le soir",                       "soir",     "HEURE")]),
        ("cours de l'après-midi",                    [e("cours de l'après-midi",                    "après-midi", "HEURE")]),
        ("disponible l'après-midi",                  [e("disponible l'après-midi",                  "après-midi", "HEURE")]),
        ("midi c'est libre",                         [e("midi c'est libre",                         "midi",     "HEURE")]),
        ("pause déjeuner à midi",                    [e("pause déjeuner à midi",                    "midi",     "HEURE")]),
    ]

    for text, ents in samples_heure:
        data.append((text, entities(*ents)))

    # ── NOMBRE ────────────────────────────────────────────────────
    samples_nombre = [
        ("réserver 2 places",                        [e("réserver 2 places",                        "2",        "NOMBRE")]),
        ("je veux 3 séances",                        [e("je veux 3 séances",                        "3",        "NOMBRE")]),
        ("une place pour le cours",                  [e("une place pour le cours",                  "une",      "NOMBRE")]),
        ("deux personnes pour le tennis",            [e("deux personnes pour le tennis",            "deux",     "NOMBRE")]),
        ("tarif pour 10 séances",                    [e("tarif pour 10 séances",                    "10",       "NOMBRE")]),
        ("carte de 5 entrées",                       [e("carte de 5 entrées",                       "5",        "NOMBRE")]),
        ("abonnement 12 mois",                       [e("abonnement 12 mois",                       "12",       "NOMBRE")]),
    ]

    for text, ents in samples_nombre:
        data.append((text, entities(*ents)))

    # ── Phrases MULTI-ENTITÉS ─────────────────────────────────────
    # Ces exemples sont critiques : le modèle apprend les combinaisons réelles
    multi = [
        (
            "réserver un cours de natation demain à 9h",
            [
                e("réserver un cours de natation demain à 9h", "natation", "SPORT"),
                e("réserver un cours de natation demain à 9h", "demain",   "DATE"),
                e("réserver un cours de natation demain à 9h", "9h",       "HEURE"),
            ],
        ),
        (
            "yoga lundi matin en salle B",
            [
                e("yoga lundi matin en salle B", "yoga",   "SPORT"),
                e("yoga lundi matin en salle B", "lundi",  "DATE"),
                e("yoga lundi matin en salle B", "matin",  "HEURE"),
                e("yoga lundi matin en salle B", "salle B","LIEU"),
            ],
        ),
        (
            "cours de fitness à 18h en salle A ce soir",
            [
                e("cours de fitness à 18h en salle A ce soir", "fitness",  "SPORT"),
                e("cours de fitness à 18h en salle A ce soir", "18h",      "HEURE"),
                e("cours de fitness à 18h en salle A ce soir", "salle A",  "LIEU"),
                e("cours de fitness à 18h en salle A ce soir", "ce soir",  "DATE"),
            ],
        ),
        (
            "annuler ma réservation de tennis samedi à 14h",
            [
                e("annuler ma réservation de tennis samedi à 14h", "tennis",  "SPORT"),
                e("annuler ma réservation de tennis samedi à 14h", "samedi",  "DATE"),
                e("annuler ma réservation de tennis samedi à 14h", "14h",     "HEURE"),
            ],
        ),
        (
            "disponibilité piscine ce week-end le matin",
            [
                e("disponibilité piscine ce week-end le matin", "piscine",   "LIEU"),
                e("disponibilité piscine ce week-end le matin", "week-end",  "DATE"),
                e("disponibilité piscine ce week-end le matin", "matin",     "HEURE"),
            ],
        ),
        (
            "zumba jeudi soir 2 places",
            [
                e("zumba jeudi soir 2 places", "zumba",  "SPORT"),
                e("zumba jeudi soir 2 places", "jeudi",  "DATE"),
                e("zumba jeudi soir 2 places", "soir",   "HEURE"),
                e("zumba jeudi soir 2 places", "2",      "NOMBRE"),
            ],
        ),
        (
            "réserver salle C mardi à 10h pour 3 personnes",
            [
                e("réserver salle C mardi à 10h pour 3 personnes", "salle C", "LIEU"),
                e("réserver salle C mardi à 10h pour 3 personnes", "mardi",   "DATE"),
                e("réserver salle C mardi à 10h pour 3 personnes", "10h",     "HEURE"),
                e("réserver salle C mardi à 10h pour 3 personnes", "3",       "NOMBRE"),
            ],
        ),
        (
            "cours de pilates vendredi après-midi",
            [
                e("cours de pilates vendredi après-midi", "pilates",    "SPORT"),
                e("cours de pilates vendredi après-midi", "vendredi",   "DATE"),
                e("cours de pilates vendredi après-midi", "après-midi", "HEURE"),
            ],
        ),
        (
            "musculation demain matin en salle de fitness",
            [
                e("musculation demain matin en salle de fitness", "musculation",     "SPORT"),
                e("musculation demain matin en salle de fitness", "demain",          "DATE"),
                e("musculation demain matin en salle de fitness", "matin",           "HEURE"),
                e("musculation demain matin en salle de fitness", "salle de fitness","LIEU"),
            ],
        ),
        (
            "badminton ce soir à 20h court numéro 2",
            [
                e("badminton ce soir à 20h court numéro 2", "badminton", "SPORT"),
                e("badminton ce soir à 20h court numéro 2", "ce soir",   "DATE"),
                e("badminton ce soir à 20h court numéro 2", "20h",       "HEURE"),
                e("badminton ce soir à 20h court numéro 2", "court",     "LIEU"),
            ],
        ),
        (
            "inscription aquagym mercredi 18h30 une place",
            [
                e("inscription aquagym mercredi 18h30 une place", "aquagym",  "SPORT"),
                e("inscription aquagym mercredi 18h30 une place", "mercredi", "DATE"),
                e("inscription aquagym mercredi 18h30 une place", "18h30",    "HEURE"),
                e("inscription aquagym mercredi 18h30 une place", "une",      "NOMBRE"),
            ],
        ),
        (
            "squash samedi matin 2 joueurs",
            [
                e("squash samedi matin 2 joueurs", "squash",  "SPORT"),
                e("squash samedi matin 2 joueurs", "samedi",  "DATE"),
                e("squash samedi matin 2 joueurs", "matin",   "HEURE"),
                e("squash samedi matin 2 joueurs", "2",       "NOMBRE"),
            ],
        ),
        (
            "annuler natation vestiaires salle 2",
            [
                e("annuler natation vestiaires salle 2", "natation",    "SPORT"),
                e("annuler natation vestiaires salle 2", "vestiaires",  "LIEU"),
                e("annuler natation vestiaires salle 2", "salle 2",     "LIEU"),
            ],
        ),
        (
            "je veux aller à la salle A demain matin",
            [
                e("je veux aller à la salle A demain matin", "salle A", "LIEU"),
                e("je veux aller à la salle A demain matin", "demain",  "DATE"),
                e("je veux aller à la salle A demain matin", "matin",   "HEURE"),
            ],
        ),
        (
            "cours de boxe vendredi soir en salle C",
            [
                e("cours de boxe vendredi soir en salle C", "boxe",     "SPORT"),
                e("cours de boxe vendredi soir en salle C", "vendredi", "DATE"),
                e("cours de boxe vendredi soir en salle C", "soir",     "HEURE"),
                e("cours de boxe vendredi soir en salle C", "salle C",  "LIEU"),
            ],
        ),
        (
            "handball demain à 15h gymnase",
            [
                e("handball demain à 15h gymnase", "handball", "SPORT"),
                e("handball demain à 15h gymnase", "demain",   "DATE"),
                e("handball demain à 15h gymnase", "15h",      "HEURE"),
                e("handball demain à 15h gymnase", "gymnase",  "LIEU"),
            ],
        ),
        (
            "réserver spinning samedi matin 2 places",
            [
                e("réserver spinning samedi matin 2 places", "spinning", "SPORT"),
                e("réserver spinning samedi matin 2 places", "samedi",   "DATE"),
                e("réserver spinning samedi matin 2 places", "matin",    "HEURE"),
                e("réserver spinning samedi matin 2 places", "2",        "NOMBRE"),
            ],
        ),
        (
            "yoga mercredi à 18h salle de yoga une place",
            [
                e("yoga mercredi à 18h salle de yoga une place", "yoga",         "SPORT"),
                e("yoga mercredi à 18h salle de yoga une place", "mercredi",     "DATE"),
                e("yoga mercredi à 18h salle de yoga une place", "18h",          "HEURE"),
                e("yoga mercredi à 18h salle de yoga une place", "salle de yoga","LIEU"),
                e("yoga mercredi à 18h salle de yoga une place", "une",          "NOMBRE"),
            ],
        ),
        (
            "judo jeudi après-midi salle A",
            [
                e("judo jeudi après-midi salle A", "judo",       "SPORT"),
                e("judo jeudi après-midi salle A", "jeudi",      "DATE"),
                e("judo jeudi après-midi salle A", "après-midi", "HEURE"),
                e("judo jeudi après-midi salle A", "salle A",    "LIEU"),
            ],
        ),
        (
            "natation synchronisée ce soir à 20h bassin olympique",
            [
                e("natation synchronisée ce soir à 20h bassin olympique", "natation synchronisée", "SPORT"),
                e("natation synchronisée ce soir à 20h bassin olympique", "ce soir",               "DATE"),
                e("natation synchronisée ce soir à 20h bassin olympique", "20h",                   "HEURE"),
                e("natation synchronisée ce soir à 20h bassin olympique", "bassin olympique",       "LIEU"),
            ],
        ),
        (
            "crossfit lundi 7h salle de fitness 3 personnes",
            [
                e("crossfit lundi 7h salle de fitness 3 personnes", "crossfit",        "SPORT"),
                e("crossfit lundi 7h salle de fitness 3 personnes", "lundi",           "DATE"),
                e("crossfit lundi 7h salle de fitness 3 personnes", "7h",              "HEURE"),
                e("crossfit lundi 7h salle de fitness 3 personnes", "salle de fitness","LIEU"),
                e("crossfit lundi 7h salle de fitness 3 personnes", "3",               "NOMBRE"),
            ],
        ),
        (
            "tennis de table samedi 10h salle B deux joueurs",
            [
                e("tennis de table samedi 10h salle B deux joueurs", "tennis de table", "SPORT"),
                e("tennis de table samedi 10h salle B deux joueurs", "samedi",          "DATE"),
                e("tennis de table samedi 10h salle B deux joueurs", "10h",             "HEURE"),
                e("tennis de table samedi 10h salle B deux joueurs", "salle B",         "LIEU"),
                e("tennis de table samedi 10h salle B deux joueurs", "deux",            "NOMBRE"),
            ],
        ),
    ]

    for text, ents in multi:
        data.append((text, entities(*ents)))

    return data


NER_TRAINING_DATA = build_training_data()