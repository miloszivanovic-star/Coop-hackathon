from bots.bot_interface import BotInterface
from game.rules import BOARD_SIZE


class Zeus(BotInterface):
    def __init__(self):
        self._name = "Zeus"
        self._sprite_path = "assets/wizards/zeus.jpg"
        self._minion_sprite_path = "assets/minions/ares.jpg"
        self._first_turn = True  # Track first turn for smart teleport

    @property
    def name(self):
        return self._name

    @property
    def sprite_path(self):
        return self._sprite_path

    @property
    def minion_sprite_path(self):
        return self._minion_sprite_path

    def decide(self, state):
        self_data = state["self"]
        opp_data = state["opponent"]
        artifacts = state.get("artifacts", [])
        minions = state.get("minions", [])

        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data.get("cooldowns", {})
        mana = self_data.get("mana", 0)
        hp = self_data.get("hp", 100)
        has_shield = self_data.get("shield_active", False)

        move = [0, 0]
        spell = None

        # ---------- Helpers ----------
        def dist(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def manhattan_dist(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        # Get all enemy units (safely handle missing "owner")
        enemies = [
            e for e in minions + [opp_data]
            if e.get("owner", opp_data.get("name", "opponent")) != self_data["name"]
        ]
        adjacent_enemies = [e for e in enemies if manhattan_dist(self_pos, e["position"]) == 1]

        # Track own minions safely
        my_minions = [m for m in minions if m.get("owner", "") == self_data["name"]]

        # ---------- FIRST TURN SMART TELEPORT ----------
        if self._first_turn:
            self._first_turn = False
            if cooldowns.get("teleport", 0) == 0 and mana >= 40 and artifacts:
                # pick closest artifact that also moves toward opponent
                target_art = min(artifacts, key=lambda a: dist(a["position"], opp_pos))
                spell = {"name": "teleport", "target": target_art["position"]}
                return {"move": move, "spell": spell}

        # ---------- DEFENSIVE PRIORITIES ----------
        # Shield if low HP or expecting damage
        if hp <= 50 and not has_shield and cooldowns.get("shield", 0) == 0 and mana >= 20:
            spell = {"name": "shield"}

        # Summon minion early if none exists
        elif cooldowns.get("summon", 0) == 0 and mana >= 50 and len(my_minions) == 0:
            spell = {"name": "summon"}

        # Heal if HP moderately low
        elif hp <= 80 and cooldowns.get("heal", 0) == 0 and mana >= 25:
            spell = {"name": "heal"}

        # ---------- OFFENSIVE PRIORITIES ----------
        # Melee attack if adjacent
        elif adjacent_enemies and cooldowns.get("melee_attack", 0) == 0:
            target = min(adjacent_enemies, key=lambda e: e.get("hp", 20))
            spell = {"name": "melee_attack", "target": target["position"]}

        # Fireball if in range (2–5)
        elif cooldowns.get("fireball", 0) == 0 and mana >= 30:
            d = dist(self_pos, opp_pos)
            if 2 <= d <= 5:
                spell = {"name": "fireball", "target": opp_pos}

        # ---------- RESOURCE CONTROL ----------
        # Move toward useful artifact if HP or mana low
        if not spell and artifacts and (mana <= 60 or hp <= 60):
            nearest = min(artifacts, key=lambda a: dist(self_pos, a["position"]))
            move = self.move_toward(self_pos, nearest["position"])
        # Otherwise, move toward opponent
        elif not spell:
            move = self._maintain_optimal_distance(self_pos, opp_pos)

        return {"move": move, "spell": spell}

    # ---------- Movement Helpers ----------
    def move_toward(self, start, target):
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        return [step_x, step_y]

    def move_away(self, start, threat):
        dx = start[0] - threat[0]
        dy = start[1] - threat[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        return [step_x, step_y]

    def _maintain_optimal_distance(self, self_pos, opp_pos):
        """
        Maintain fireball range: 2–5 squares.
        Strafe if in optimal range.
        """
        d = max(abs(self_pos[0] - opp_pos[0]), abs(self_pos[1] - opp_pos[1]))
        if d < 2:
            return self.move_away(self_pos, opp_pos)
        elif d > 5:
            return self.move_toward(self_pos, opp_pos)
        else:
            # Strafe perpendicular
            dx = opp_pos[0] - self_pos[0]
            dy = opp_pos[1] - self_pos[1]
            if abs(dx) > abs(dy):
                # Vertical strafe
                if 0 < self_pos[1] < BOARD_SIZE - 1:
                    return [0, 1] if self_pos[1] < 5 else [0, -1]
            else:
                # Horizontal strafe
                if 0 < self_pos[0] < BOARD_SIZE - 1:
                    return [1, 0] if self_pos[0] < 5 else [-1, 0]
            return [0, 0]  # Hold if at boundary
