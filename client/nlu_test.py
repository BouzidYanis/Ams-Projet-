from app.nlu import NLU

nlu = NLU()

tests = [
    # intents
    "quelles activités sont disponibles ?",
    "vous proposez quoi comme sports ?",
    "à quelle heure ouvrez-vous",
    "vous fermez à quelle heure ?",
    "je veux réserver un cours",
    "je voudrais m'inscrire au futsal",
    "bonjour",
    "bonsoir",
    "qui es-tu",
    "quel est ton rôle",

    # navigation + entities
    "où est la salle de sport ?",
    "où se trouve le vestiaire ?",
    "je cherche l'accueil",
    "où est le secrétariat",

    # mixed
    "je veux faire du football à la salle",
    "réserver fitness",

    # unknown-ish
    "peux-tu me raconter une blague",
]

for t in tests:
    print("=" * 50)
    print(t)
    print(nlu.parse(t))
