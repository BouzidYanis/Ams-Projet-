import re

def parse_heure_to_minutes(heure_str: str) -> int:
        """
        Convertit une chaîne d'heure en minutes depuis minuit.
        Supporte : '19h', '19h30', '19H00', '18:00', 'à 19', '19'
        Retourne None si impossible à parser.
        """
        if not heure_str:
            return None
        heure_str = heure_str.strip().lower()

        # Format "18:00", "17:30"
        m = re.search(r'(\d{1,2}):(\d{1,2})', heure_str)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))

        # Format "19h30", "19h", "19H00"
        m = re.search(r'(\d{1,2})\s*[hH]\s*(\d{1,2})?', heure_str)
        if m:
            h = int(m.group(1))
            mins = int(m.group(2)) if m.group(2) else 0
            return h * 60 + mins

        # Format "à 19" ou juste "19"
        m = re.search(r'(\d{1,2})', heure_str)
        if m:
            return int(m.group(1)) * 60

        return None

def parse_minutes_to_heure(minutes: int) -> str:
        """
        Convertit un nombre de minutes depuis minuit en une chaîne d'heure au format "HH:MM".
        Par exemple, 1140 devient "19:00", 1170 devient "19:30".
        """
        if minutes is None:
            return None
        h = minutes // 60
        m = minutes % 60
        return "{:02d}:{:02d}".format(h, m)