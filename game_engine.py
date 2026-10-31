# Game logic is kept separate from Flask routes.
# Each user's state is stored in their own GameSave row.

CLUBS = {
    "Real Madrid": {"budget": 180_000_000, "rating": 91},
    "Barcelona": {"budget": 120_000_000, "rating": 89},
    "Arsenal": {"budget": 110_000_000, "rating": 88},
    "Bayern Munich": {"budget": 140_000_000, "rating": 90},
    "Manchester United": {"budget": 100_000_000, "rating": 85},
}

STARTING_SQUADS = {
    "Real Madrid": [
        ("Thibaut Courtois", "GK", 89), ("Dani Carvajal", "RB", 84),
        ("Antonio Rudiger", "CB", 88), ("Eder Militao", "CB", 86),
        ("Ferland Mendy", "LB", 83), ("Federico Valverde", "CM", 89),
        ("Jude Bellingham", "CAM", 91), ("Eduardo Camavinga", "CM", 86),
        ("Rodrygo", "RW", 87), ("Kylian Mbappe", "ST", 92),
        ("Vinicius Jr", "LW", 91),
    ],
    "Barcelona": [
        ("Marc-Andre ter Stegen", "GK", 87), ("Jules Kounde", "RB", 86),
        ("Ronald Araujo", "CB", 88), ("Pau Cubarsi", "CB", 82),
        ("Alejandro Balde", "LB", 84), ("Pedri", "CM", 89),
        ("Frenkie de Jong", "CM", 87), ("Gavi", "CM", 85),
        ("Lamine Yamal", "RW", 90), ("Robert Lewandowski", "ST", 88),
        ("Raphinha", "LW", 87),
    ],
    "Arsenal": [
        ("David Raya", "GK", 86), ("Ben White", "RB", 85),
        ("William Saliba", "CB", 89), ("Gabriel", "CB", 88),
        ("Riccardo Calafiori", "LB", 84), ("Declan Rice", "DM", 90),
        ("Martin Odegaard", "CAM", 89), ("Thomas Partey", "CM", 83),
        ("Bukayo Saka", "RW", 90), ("Kai Havertz", "ST", 86),
        ("Gabriel Martinelli", "LW", 85),
    ],
    "Bayern Munich": [
        ("Manuel Neuer", "GK", 87), ("Joshua Kimmich", "RB", 88),
        ("Dayot Upamecano", "CB", 85), ("Kim Min-jae", "CB", 86),
        ("Alphonso Davies", "LB", 87), ("Leon Goretzka", "CM", 85),
        ("Jamal Musiala", "CAM", 91), ("Aleksandar Pavlovic", "CM", 83),
        ("Michael Olise", "RW", 87), ("Harry Kane", "ST", 92),
        ("Kingsley Coman", "LW", 85),
    ],
    "Manchester United": [
        ("Andre Onana", "GK", 84), ("Diogo Dalot", "RB", 83),
        ("Matthijs de Ligt", "CB", 86), ("Lisandro Martinez", "CB", 85),
        ("Luke Shaw", "LB", 82), ("Kobbie Mainoo", "CM", 84),
        ("Bruno Fernandes", "CAM", 88), ("Casemiro", "DM", 84),
        ("Amad Diallo", "RW", 83), ("Benjamin Sesko", "ST", 84),
        ("Matheus Cunha", "LW", 85),
    ],
}

def create_new_game(club):
    info = CLUBS[club]
    players = [
        {"name": name, "position": pos, "rating": rating, "level": 0}
        for name, pos, rating in STARTING_SQUADS[club]
    ]
    return {
        "club": club,
        "budget": info["budget"],
        "season": 1,
        "week": 1,
        "points": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "players": players,
        "formation": "4-3-3",
    }

def get_dashboard(state):
    return {
        "club": state["club"],
        "budget": state["budget"],
        "season": state["season"],
        "week": state["week"],
        "points": state["points"],
        "wins": state["wins"],
        "draws": state["draws"],
        "losses": state["losses"],
        "formation": state["formation"],
        "squad_size": len(state["players"]),
        "average_rating": round(sum(p["rating"] + p["level"] for p in state["players"]) / max(1, len(state["players"])), 1),
    }

def get_squad(state):
    return sorted(state["players"], key=lambda p: p["rating"] + p["level"], reverse=True)
