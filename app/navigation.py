import networkx as nx


class IndoorMap:
    def __init__(self):
        self.graph = nx.Graph()
        self._build_graph()

    def _build_graph(self):
        """
        Création du graphe sémantique du bâtiment
        """

        # Ajout des points d’intérêt
        self.graph.add_nodes_from([
            "Entrée",
            "Escaliers",
            "Couloir",
            "Salle de fitness",
            "Accueil"
        ])

        # Connexions entre les lieux
        self.graph.add_edge("Entrée", "Accueil")
        self.graph.add_edge("Accueil", "Escaliers")
        self.graph.add_edge("Escaliers", "Couloir")
        self.graph.add_edge("Couloir", "Salle de fitness")

    def shortest_path(self, start, end):
        """
        Calcul du chemin le plus court
        """
        return nx.shortest_path(self.graph, start, end)


class InstructionGenerator:
    def generate(self, path):
        instructions = []

        for i in range(len(path) - 1):
            current = path[i]
            nxt = path[i + 1]

            if nxt == "Escaliers":
                instructions.append("Prenez l'escalier.")
            elif current == "Escaliers":
                instructions.append("Montez au premier étage.")
            elif nxt == "Couloir":
                instructions.append("Avancez dans le couloir.")
            elif nxt == "Salle de fitness":
                instructions.append("La salle de fitness se trouve sur votre droite.")
            else:
                instructions.append(f"Allez de {current} vers {nxt}.")

        return instructions


if __name__ == "__main__":
    indoor_map = IndoorMap()
    generator = InstructionGenerator()

    start = "Entrée"
    destination = "Salle de fitness"

    path = indoor_map.shortest_path(start, destination)

    print("Chemin calculé :", " → ".join(path))
    print("\nInstructions pour l'utilisateur :")

    instructions = generator.generate(path)
    for step, instr in enumerate(instructions, start=1):
        print(f"{step}. {instr}")