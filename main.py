from engine.pokemon import Pokemon
from engine.game_state import GameState

def main():
    starter = Pokemon("bulbasaur", level=5)
    print(f"{starter.name} knows: {starter.moves}")

if __name__ == "__main__":
    main()
