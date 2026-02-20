import networkx as nx


# Mapping clé normalisée (venant du NLU) → nom du nœud dans le graphe
DESTINATION_KEY_TO_NODE = {
    "accueil": "Accueil",
    "salle_a": "Salle A",
    "salle_b": "Salle B",
    "salle_c": "Salle C",
    "salle_d": "Salle D",
    "natation": "Salle Natation",
    "salle_natation": "Salle Natation",
    "vestiaire": "Vestiaire",
    "vestiaires": "Vestiaire",
    "terrain": "Terrain",
    "secretariat": "Secrétariat",
    "secrétariat": "Secrétariat",
    "entree": "Entrée",
    "entrée": "Entrée",
}


class IndoorMap:
    def __init__(self):
        self.graph = nx.Graph()
        self._build_graph()

    def _build_graph(self):
        """
        Création du graphe sémantique du bâtiment
        """

        # Ajout des points d'intérêt
        self.graph.add_nodes_from([
            "Entrée",
            "Accueil",
            "Escalier 1",
            "Escalier 2",
            "Couloir",
            "Salle A",
            "Salle B",
            "Salle C",
            "Salle D",
            "Salle Natation",
        ])

        # Connexions entre les lieux
        self.graph.add_edges_from([
            ("Entrée", "Accueil"),
            ("Accueil", "Couloir"),
            ("Couloir", "Salle A"),
            ("Couloir", "Salle B"),
            ("Couloir", "Salle C"),
            ("Couloir", "Salle D"),
            ("Couloir", "Salle Natation"),
            ("Couloir", "Escalier 1"),
            ("Couloir", "Escalier 2"),
        ])

    def shortest_path(self, start, end):
        """
        Calcul du chemin le plus court
        """
        return nx.shortest_path(self.graph, start, end)

    def resolve_destination(self, destination_key):
        """Résout une clé normalisée en nom de nœud du graphe. Retourne None si inconnu."""
        return DESTINATION_KEY_TO_NODE.get(destination_key)


class InstructionGenerator:
    def generate(self, path):
        instructions = []

        for i in range(len(path) - 1):
            current = path[i]
            nxt = path[i + 1]

            if "Escalier" in nxt:
                instructions.append("Prenez les escaliers.")
            elif "Escalier" in current:
                instructions.append("Montez au premier étage.")
            elif nxt == "Couloir":
                instructions.append("Avancez dans le couloir.")
            elif nxt == "Accueil":
                instructions.append("Dirigez-vous vers l'accueil.")
            elif nxt == "Entrée":
                instructions.append("Retournez vers l'entrée.")
            elif "Salle" in nxt:
                instructions.append("Continuez tout droit, {} se trouve devant vous.".format(nxt))
            else:
                instructions.append("Allez de {} vers {}.".format(current, nxt))

        return instructions


# Instance singleton réutilisable
_map = IndoorMap()
_generator = InstructionGenerator()


def get_navigation_instructions(destination_key, start_key="accueil"):
    """
    Fonction utilitaire : prend une clé normalisée (ex: 'salle_a')
    et retourne un dict avec le chemin, les instructions et l'URL tablette.
    """
    node = _map.resolve_destination(destination_key)
    if node is None:
        return None

    start_node = _map.resolve_destination(start_key) or "Accueil"

    try:
        path = _map.shortest_path(start_node, node)
    except nx.NetworkXNoPath:
        return None

    instructions = _generator.generate(path)

    return {
        "destination": node,
        "destination_key": destination_key,
        "path": path,
        "instructions": instructions,
    }

