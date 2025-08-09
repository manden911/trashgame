import random
import time
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# Cyberpunk Battle Royale Simulator (self-running)
# Humans vs Cyborgs fight to the end. No external deps.


@dataclass
class StatusEffect:
    name: str
    duration: int
    magnitude: float = 0.0


@dataclass
class Move:
    name: str
    power: int
    energy_cost: int
    accuracy: float  # 0..1
    crit_chance: float  # 0..1
    tags: List[str] = field(default_factory=list)  # e.g. ["bleed"], ["emp"], ["heal"], ["buff_attack"], ["buff_defense"], ["hack"]
    description: str = ""


@dataclass
class Fighter:
    name: str
    faction: str  # "Human" or "Cyborg"
    max_hp: int
    hp: int
    attack: int
    defense: int
    speed: int
    max_energy: int
    energy: int
    moves: List[Move]
    statuses: Dict[str, StatusEffect] = field(default_factory=dict)
    is_alive: bool = True

    def has_status(self, status_name: str) -> bool:
        return status_name in self.statuses and self.statuses[status_name].duration > 0

    def add_status(self, status: StatusEffect):
        # overwrite weaker or extend
        self.statuses[status.name] = status

    def tick_statuses(self, log: List[str]):
        # Apply ongoing effects and reduce durations
        expired: List[str] = []
        if self.has_status("bleed"):
            bleed = self.statuses["bleed"]
            bleed_damage = max(3, int(bleed.magnitude))
            self.hp -= bleed_damage
            log.append(f"  - {self.name} bleeds for {bleed_damage} HP")
            bleed.duration -= 1
            if bleed.duration <= 0:
                expired.append("bleed")
        if self.has_status("hack"):
            hack = self.statuses["hack"]
            hack.duration -= 1
            if hack.duration <= 0:
                expired.append("hack")
        if self.has_status("shield"):
            sh = self.statuses["shield"]
            sh.duration -= 1
            if sh.duration <= 0:
                expired.append("shield")
        if self.has_status("overclock"):
            oc = self.statuses["overclock"]
            oc.duration -= 1
            if oc.duration <= 0:
                expired.append("overclock")
        for s in expired:
            del self.statuses[s]
            log.append(f"  - {self.name}'s {s} effect ended")
        if self.hp <= 0:
            self.is_alive = False

    def effective_attack(self) -> int:
        attack = self.attack
        if self.has_status("overclock"):
            attack = int(attack * (1.0 + self.statuses["overclock"].magnitude))
        return attack

    def effective_defense(self) -> int:
        defense = self.defense
        if self.has_status("shield"):
            defense = int(defense * (1.0 + self.statuses["shield"].magnitude))
        return defense

    def effective_speed(self) -> int:
        speed = self.speed
        if self.has_status("overclock"):
            speed = int(speed * (1.0 + 0.25))
        return speed


def type_effectiveness(move: Move, attacker: Fighter, defender: Fighter) -> float:
    # Simple: EMP strong vs Cyborg, Bleed strong vs Human. Railgun strong vs Shield.
    mult = 1.0
    if "emp" in move.tags and defender.faction == "Cyborg":
        mult *= 1.5
    if "bleed" in move.tags and defender.faction == "Human":
        mult *= 1.3
    if "railgun" in move.tags and defender.has_status("shield"):
        mult *= 1.3
    if "hack" in move.tags and defender.faction == "Human":
        mult *= 0.8  # humans less vulnerable to hacking
    return mult


def accuracy_modifier(attacker: Fighter, defender: Fighter) -> float:
    mod = 1.0
    if attacker.has_status("hack"):
        mod *= 0.8
    # Speed differential lightly affects evasion
    speed_diff = defender.effective_speed() - attacker.effective_speed()
    if speed_diff > 0:
        mod *= max(0.75, 1.0 - min(0.2, speed_diff / 400.0))
    return mod


def calculate_damage(attacker: Fighter, defender: Fighter, move: Move) -> Tuple[int, bool]:
    effective = type_effectiveness(move, attacker, defender)
    attack_stat = attacker.effective_attack()
    defense_stat = max(1, defender.effective_defense())
    base = move.power * (1.0 + attack_stat / 100.0)
    variance = random.uniform(0.85, 1.15)
    raw = base * effective * variance - (defense_stat / 10.0)
    raw = max(1.0, raw)
    is_crit = random.random() < move.crit_chance
    if is_crit:
        raw *= 1.5
    return int(raw), is_crit


def choose_move(attacker: Fighter) -> Move:
    affordable = [m for m in attacker.moves if m.energy_cost <= attacker.energy]
    if not affordable:
        # pick cheapest to save for
        return min(attacker.moves, key=lambda m: m.energy_cost)
    # If low HP, bias to heal or shield if available
    low_hp_ratio = attacker.hp / attacker.max_hp
    support_moves = []
    if low_hp_ratio < 0.35:
        support_moves = [m for m in affordable if any(t in m.tags for t in ["heal", "buff_defense", "buff_attack"])]
    if support_moves and random.random() < 0.7:
        return random.choice(support_moves)
    # Otherwise pick highest power or special if hacked target soon
    return max(affordable, key=lambda m: m.power + (15 if ("emp" in m.tags or "railgun" in m.tags or "hack" in m.tags) else 0))


def pick_target(attacker: Fighter, roster: List[Fighter]) -> Optional[Fighter]:
    candidates = [f for f in roster if f.is_alive and f is not attacker]
    if not candidates:
        return None
    # Prefer targeting the healthiest enemy to avoid overkill sometimes; mix randomness
    if random.random() < 0.5:
        return max(candidates, key=lambda f: f.hp)
    return random.choice(candidates)


def apply_move(attacker: Fighter, defender: Fighter, move: Move, round_log: List[str]):
    # Energy
    if attacker.energy < move.energy_cost:
        round_log.append(f"{attacker.name} tried to use {move.name} but lacks energy.")
        return

    attacker.energy -= move.energy_cost

    # Non-damaging
    if "heal" in move.tags:
        heal_amount = int(move.power * (1.0 + attacker.attack / 200.0))
        old_hp = attacker.hp
        attacker.hp = min(attacker.max_hp, attacker.hp + heal_amount)
        round_log.append(f"{attacker.name} uses {move.name}, healing {attacker.hp - old_hp} HP")
        return

    if "buff_defense" in move.tags:
        attacker.add_status(StatusEffect("shield", duration=3, magnitude=0.35))
        round_log.append(f"{attacker.name} projects a shield (+DEF) with {move.name}")
        return

    if "buff_attack" in move.tags:
        attacker.add_status(StatusEffect("overclock", duration=3, magnitude=0.25))
        round_log.append(f"{attacker.name} overclocks systems (+ATK) with {move.name}")
        return

    # Accuracy
    acc = move.accuracy * accuracy_modifier(attacker, defender)
    if random.random() > acc:
        round_log.append(f"{attacker.name}'s {move.name} missed {defender.name}")
        return

    # Damage
    dmg, is_crit = calculate_damage(attacker, defender, move)
    defender.hp -= dmg
    crit_txt = " CRIT!" if is_crit else ""
    eff_mult = type_effectiveness(move, attacker, defender)
    eff_txt = "" if abs(eff_mult - 1.0) < 1e-6 else (" super effective!" if eff_mult > 1.0 else " not very effective.")
    round_log.append(f"{attacker.name} hits {defender.name} with {move.name} for {dmg} dmg.{crit_txt}{eff_txt}")

    # On-hit effects
    if "bleed" in move.tags and random.random() < 0.5:
        defender.add_status(StatusEffect("bleed", duration=3, magnitude=6))
        round_log.append(f"  - {defender.name} starts bleeding")
    if "hack" in move.tags and random.random() < (0.6 if defender.faction == "Cyborg" else 0.3):
        defender.add_status(StatusEffect("hack", duration=2, magnitude=0.0))
        round_log.append(f"  - {defender.name} is hacked (lower accuracy)")

    if defender.hp <= 0 and defender.is_alive:
        defender.is_alive = False
        round_log.append(f"☠ {defender.name} is eliminated!")


def energy_regen(f: Fighter):
    regen = 15
    if f.has_status("overclock"):
        regen += 5
    f.energy = min(f.max_energy, f.energy + regen)


def black_ice_event(round_index: int, roster: List[Fighter], main_log: List[str]):
    # Every 5 rounds, the Net becomes hostile causing random damage or effects
    if round_index % 5 != 0:
        return
    main_log.append("- The Black ICE intensifies across the grid -")
    for f in roster:
        if not f.is_alive:
            continue
        if random.random() < 0.5:
            hazard = random.randint(6, 18)
            f.hp -= hazard
            main_log.append(f"  • {f.name} is zapped by ICE for {hazard} HP")
            if f.hp <= 0 and f.is_alive:
                f.is_alive = False
                main_log.append(f"☠ {f.name} collapses under the ICE surge!")
        else:
            # 25% chance to purge a debuff
            if random.random() < 0.25:
                removed = None
                for key in ["bleed", "hack"]:
                    if f.has_status(key):
                        removed = key
                        break
                if removed:
                    del f.statuses[removed]
                    main_log.append(f"  • {f.name}'s {removed} was purged by ICE backwash")


def make_moves_for_faction(faction: str) -> List[Move]:
    common = [
        Move("Mono-Molecular Blade", power=28, energy_cost=15, accuracy=0.92, crit_chance=0.18, tags=["bleed"], description="A razor slice that causes bleeding."),
        Move("EMP Grenade", power=22, energy_cost=25, accuracy=0.88, crit_chance=0.10, tags=["emp"], description="Electromagnetic pulse; great vs cyborgs."),
        Move("Adrenal Surge", power=22, energy_cost=20, accuracy=1.0, crit_chance=0.0, tags=["heal"], description="Regenerate under fire."),
        Move("Ballistic Burst", power=26, energy_cost=18, accuracy=0.9, crit_chance=0.15, tags=[], description="Standard ranged attack."),
        Move("Reactive Plating", power=0, energy_cost=16, accuracy=1.0, crit_chance=0.0, tags=["buff_defense"], description="Temporary shield plating."),
        Move("Overclocked Reflexes", power=0, energy_cost=16, accuracy=1.0, crit_chance=0.0, tags=["buff_attack"], description="Increase attack speed and strength."),
    ]
    cyborg = [
        Move("Railgun Burst", power=32, energy_cost=24, accuracy=0.86, crit_chance=0.2, tags=["railgun"], description="Hypervelocity slugs."),
        Move("Logic Bomb", power=25, energy_cost=22, accuracy=0.9, crit_chance=0.12, tags=["hack"], description="Hack the enemy's targeting."),
        Move("Nano-Repair", power=24, energy_cost=20, accuracy=1.0, crit_chance=0.0, tags=["heal"], description="Swarm nanites repair damage."),
        Move("Thermal Lance", power=30, energy_cost=22, accuracy=0.88, crit_chance=0.15, tags=[], description="Melts cover and armor."),
        Move("Carbon Shield", power=0, energy_cost=16, accuracy=1.0, crit_chance=0.0, tags=["buff_defense"], description="Deploy ablative shield."),
    ]
    if faction == "Cyborg":
        return cyborg
    return common


HUMAN_NAMES = [
    "Rogue", "Vesper", "Nyx", "Kaito", "Nova", "Jax", "Echo", "Riven", "Zara", "Orion",
    "Valk", "Quinn", "Blade", "Zero", "Mara", "Specter", "Neon", "Raze", "Sable", "Knox",
]

CYBORG_NAMES = [
    "ECHO-7", "MANTIS-3", "KRAKEN-12", "VIREX-9", "ONYX-4", "PHOENIX-2", "TITAN-8", "NOVA-11",
    "SPECTRE-6", "RAPTOR-5", "CERBERUS-10", "APEX-13", "SCARAB-15", "NOMAD-01", "AURORA-14", "ZEUS-21",
]


def create_fighter(faction: str, used_names: set) -> Fighter:
    if faction == "Human":
        name_pool = HUMAN_NAMES
        base_hp = random.randint(95, 120)
        attack = random.randint(22, 34)
        defense = random.randint(12, 24)
        speed = random.randint(20, 35)
        max_energy = random.randint(65, 85)
        moves = make_moves_for_faction("Human")
    else:
        name_pool = CYBORG_NAMES
        base_hp = random.randint(100, 130)
        attack = random.randint(24, 36)
        defense = random.randint(16, 28)
        speed = random.randint(18, 30)
        max_energy = random.randint(70, 90)
        moves = make_moves_for_faction("Cyborg")
    # ensure unique name
    candidates = [n for n in name_pool if n not in used_names]
    if not candidates:
        base = random.choice(name_pool)
        name = f"{base}-{random.randint(100,999)}"
    else:
        name = random.choice(candidates)
    used_names.add(name)

    return Fighter(
        name=name,
        faction=faction,
        max_hp=base_hp,
        hp=base_hp,
        attack=attack,
        defense=defense,
        speed=speed,
        max_energy=max_energy,
        energy=max_energy,
        moves=moves,
    )


def create_roster(num_fighters: int = 12) -> List[Fighter]:
    roster: List[Fighter] = []
    used_names: set = set()
    # balance factions roughly
    for i in range(num_fighters):
        faction = "Cyborg" if i % 2 == 0 else "Human"
        roster.append(create_fighter(faction, used_names))
    return roster


def print_header(num: int):
    bar = "=" * 60
    print(bar)
    print("CYBERPUNK BATTLE ROYALE: Humans vs Cyborgs")
    print(f"Contestants: {num}. The Net storms every 5 rounds.")
    print("Last entity standing wins. Simulation runs automatically.")
    print(bar)


def print_roster(roster: List[Fighter]):
    for f in roster:
        print(f" - {f.name:12s} [{f.faction:6s}] HP:{f.hp:3d}/{f.max_hp:3d} ATK:{f.attack:2d} DEF:{f.defense:2d} SPD:{f.speed:2d} EN:{f.energy:2d}")


def run_simulation(num_fighters: int = 12, max_rounds: int = 250, seed: Optional[int] = None, delay: float = 0.05):
    if seed is not None:
        random.seed(seed)
    roster = create_roster(num_fighters)
    print_header(len(roster))
    print_roster(roster)
    print("\nFight begins...\n")

    round_index = 0
    while True:
        alive = [f for f in roster if f.is_alive]
        if len(alive) <= 1:
            break
        round_index += 1
        print(f"--- Round {round_index} ---")
        # Initiative by speed
        turn_order = sorted(alive, key=lambda f: (f.effective_speed(), random.random()), reverse=True)

        # Black ICE events sometimes before actions
        round_log: List[str] = []
        black_ice_event(round_index, roster, round_log)

        # Each fighter acts
        for actor in turn_order:
            if not actor.is_alive:
                continue
            # Start of turn regen
            energy_regen(actor)
            # Status tick at start
            actor.tick_statuses(round_log)
            if not actor.is_alive:
                continue
            # Hacked minor skip chance
            if actor.has_status("hack") and random.random() < 0.1:
                round_log.append(f"{actor.name}'s systems glitch out and skip the turn")
                continue
            target = pick_target(actor, roster)
            if not target:
                continue
            move = choose_move(actor)
            apply_move(actor, target, move, round_log)
            if not target.is_alive:
                # 20% chance to siphon energy on kill
                if random.random() < 0.2:
                    siphon = 20
                    actor.energy = min(actor.max_energy, actor.energy + siphon)
                    round_log.append(f"  - {actor.name} siphons {siphon} energy from the fallen")

            # Minor delay for readability
            if delay > 0:
                time.sleep(delay)

        # End of round cleanup + summary
        for line in round_log:
            print(line)

        # Brief scoreboard
        survivors = [f for f in roster if f.is_alive]
        summary = ", ".join([f"{f.name}({f.hp}HP,{f.energy}EN)" for f in survivors])
        print(f"Survivors [{len(survivors)}]: {summary}")
        print()

        if round_index >= max_rounds:
            print("Max rounds reached. Forcing sudden death!")
            # Deal heavy ICE damage until one remains
            for f in survivors:
                f.hp = 1
            while len([f for f in roster if f.is_alive]) > 1:
                attacker = random.choice([f for f in roster if f.is_alive])
                target = pick_target(attacker, roster)
                if not target:
                    break
                move = choose_move(attacker)
                # ensure hit and lethal
                target.hp = 0
                target.is_alive = False
                print(f"SuddenDeath: {attacker.name} executes {target.name} with {move.name}")
            break

    # Winner announcement
    alive = [f for f in roster if f.is_alive]
    if len(alive) == 1:
        winner = alive[0]
        print("=" * 60)
        print(f"WINNER: {winner.name} [{winner.faction}] with {winner.hp} HP remaining")
        print("=" * 60)
    else:
        print("=" * 60)
        print("No clear winner. The grid goes dark.")
        print("=" * 60)


def parse_args(argv: List[str]) -> Tuple[int, Optional[int], float]:
    num = 12
    seed: Optional[int] = None
    delay = 0.03
    for arg in argv:
        if arg.startswith("--fighters="):
            try:
                num = max(2, int(arg.split("=", 1)[1]))
            except Exception:
                pass
        if arg.startswith("--seed="):
            try:
                seed = int(arg.split("=", 1)[1])
            except Exception:
                pass
        if arg.startswith("--delay="):
            try:
                delay = float(arg.split("=", 1)[1])
            except Exception:
                pass
    return num, seed, delay


if __name__ == "__main__":
    num, seed, delay = parse_args(sys.argv[1:])
    run_simulation(num_fighters=num, seed=seed, delay=delay)