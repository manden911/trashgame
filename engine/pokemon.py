from utils.loader import load_yaml

class Pokemon:
    def __init__(self, species_id, level=5):
        all_data = load_yaml("data/pokemon.yaml")
        species = all_data.get(species_id)
        if not species:
            raise ValueError(f"Unknown Pokémon: {species_id}")
        
        self.name = species_id
        self.level = level
        self.types = species["types"]
        self.stats = species["base_stats"]
        self.moves = self.init_moves(species["learnset"]["level_up"])

    def init_moves(self, learnset):
        return [entry["move"] for entry in learnset if entry["level"] <= self.level]
