from bots.bot_interface import BotInterface
 
 
class UltimateBot(BotInterface):
    def __init__(self):
        self._name = "Ultimate Ninja"
        self._sprite_path = "assets/ninja/ultimate_ninja.png"
        self._minion_sprite_path = "assets/minions/ninja.png"
 
        self._turn = 0
        self._opp_fireballs = 0
 
    @property
    def name(self):
        return self._name
 
    @property
    def sprite_path(self):
        return self._sprite_path
 
    @property
    def minion_sprite_path(self):
        return self._minion_sprite_path
 
    # ============================================================
    # MAIN DECISION LOOP
    # ============================================================
    def decide(self, state):
        self._turn += 1
 
        me = state["self"]
        opp = state["opponent"]
        artifacts = state.get("artifacts", [])
        minions = state.get("minions", [])
 
        my_pos = me["position"]
        opp_pos = opp["position"]
        cd = me["cooldowns"]
        mana = me["mana"]
        hp = me["hp"]
 
        enemy_minions = [m for m in minions if m["owner"] != me["name"]]
        own_minions = [m for m in minions if m["owner"] == me["name"]]
 
        # ------------------------------------------------------------
        # Distance helpers
        # ------------------------------------------------------------
        def cheb(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
 
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
 
        def nearest_artifact():
            return min(artifacts, key=lambda a: cheb(my_pos, a["position"]))
 
        dist = cheb(my_pos, opp_pos)
        move = [0, 0]
        spell = None
 
        # ------------------------------------------------------------
        # Lightweight opponent aggression detection
        # ------------------------------------------------------------
        if opp.get("last_spell") == "fireball":
            self._opp_fireballs += 1
 
        aggressive_opp = self._opp_fireballs >= 2
 
        # ------------------------------------------------------------
        # Adaptive heal threshold (KEY improvement vs Rade)
        # ------------------------------------------------------------
        if self._turn < 10:
            heal_threshold = 40
        elif self._turn < 20:
            heal_threshold = 55
        else:
            heal_threshold = 70
 
        # ============================================================
        # PHASE 0 — HARD SURVIVAL
        # ============================================================
        if hp <= 30 and cd["shield"] == 0 and mana >= 20:
            spell = {"name": "shield"}
 
        elif hp <= heal_threshold and cd["heal"] == 0 and mana >= 25:
            spell = {"name": "heal"}
 
        # ============================================================
        # PHASE 1 — EARLY DEFENSIVE TEMPO
        # ============================================================
        elif self._turn <= 2 and cd["shield"] == 0 and mana >= 20:
            spell = {"name": "shield"}
 
        elif aggressive_opp and hp <= 75 and cd["shield"] == 0 and mana >= 20:
            spell = {"name": "shield"}
 
        elif not own_minions and cd["summon"] == 0 and mana >= 45:
            spell = {"name": "summon"}
 
        # ============================================================
        # PHASE 2 — RESOURCE CONTROL
        # ============================================================
        elif artifacts and mana < 45:
            a = nearest_artifact()
            if cd["teleport"] == 0 and mana >= 40:
                spell = {"name": "teleport", "target": a["position"]}
            else:
                move = self.move_toward(my_pos, a["position"])
 
        # ============================================================
        # PHASE 3 — PRESSURE / COLLAPSE
        # ============================================================
        elif (
            self._turn > 8
            and not enemy_minions
            and dist >= 6
            and mana >= 60
            and hp >= 60
        ):
            move = self.move_toward(my_pos, opp_pos)
 
        # ============================================================
        # PHASE 4 — EXECUTION MODE
        # ============================================================
        elif (
            self._turn > 12
            and not enemy_minions
            and dist <= 4
            and mana >= 45
            and hp >= 55
            and opp["hp"] <= hp + 10
        ):
            if cd["fireball"] == 0 and opp["hp"] <= 40:
                spell = {"name": "fireball", "target": opp_pos}
            elif cd["melee_attack"] == 0 and manhattan(my_pos, opp_pos) == 1:
                spell = {"name": "melee_attack", "target": opp_pos}
            else:
                move = self.move_toward(my_pos, opp_pos)
 
        # ============================================================
        # PHASE 5 — OPPORTUNISTIC DAMAGE
        # ============================================================
        elif enemy_minions and cd["fireball"] == 0 and mana >= 45:
            in_range = [m for m in enemy_minions if cheb(my_pos, m["position"]) <= 5]
            if in_range:
                target = min(in_range, key=lambda m: m["hp"])
                spell = {"name": "fireball", "target": target["position"]}
 
        elif cd["melee_attack"] == 0 and manhattan(my_pos, opp_pos) == 1:
            spell = {"name": "melee_attack", "target": opp_pos}
 
        elif cd["fireball"] == 0 and mana >= 45 and dist <= 5:
            spell = {"name": "fireball", "target": opp_pos}
 
        # ============================================================
        # PHASE 6 — POSITIONING / KITING
        # ============================================================
        else:
            if dist <= 3:
                move = self.move_away(my_pos, opp_pos)
            elif dist >= 6:
                move = self.move_toward(my_pos, opp_pos)
 
        return {"move": move, "spell": spell}
 
    # ============================================================
    # MOVEMENT HELPERS
    # ============================================================
    def move_toward(self, start, target):
        return [
            1 if target[0] > start[0] else -1 if target[0] < start[0] else 0,
            1 if target[1] > start[1] else -1 if target[1] < start[1] else 0,
        ]
 
    def move_away(self, start, target):
        return [
            -1 if target[0] > start[0] else 1 if target[0] < start[0] else 0,
            -1 if target[1] > start[1] else 1 if target[1] < start[1] else 0,
        ]
 