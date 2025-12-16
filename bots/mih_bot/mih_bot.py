"""
Mih Bot - Optimized Elite Tactical Wizard

OPTIMIZED STRATEGY (Based on tournament analysis):
1. MINION MASTER FOCUS: Like the #1 bot (89.1% win rate), prioritize sustained minion pressure
   - Early and consistent minion summoning for 10 dmg/turn DPS
   - Aggressive mana artifact collection to sustain minion spam
   
2. ADAPTIVE MODE SWITCHING: Like the #2 bot (82.7% win rate), dynamically adapt strategy
   - Aggressive mode: HP advantage or late game (turn >= 50)
   - Defensive mode: HP disadvantage >= 20
   - Resource mode: Low HP/mana, prioritize artifact collection
   - Minion Master mode: Maintain minion pressure while supporting with spells
   
3. MELEE SUPREMACY: Melee bypasses shields (10 dmg, 0 mana) - maximize usage
4. PREDICTIVE ATTACKS: Fire at predicted positions for splash damage
5. RESOURCE EFFICIENCY: Shield blocks 20 dmg for 20 mana (100% efficient)
6. TACTICAL POSITIONING: Control distance and force advantageous engagements
"""

from bots.bot_interface import BotInterface


class MihBot(BotInterface):
    def __init__(self):
        self._name = "Mih Bot"
        self._sprite_path = "assets/wizards/mih_bot.svg"
        self._minion_sprite_path = "assets/minions/mih_minion.svg"
        self._last_opp_pos = None
        self._turns_stationary = 0
        self._opponent_pattern = []  # Track opponent movement history

    @property
    def name(self) -> str:
        return self._name

    @property
    def sprite_path(self):
        return self._sprite_path

    @property
    def minion_sprite_path(self):
        return self._minion_sprite_path

    def decide(self, state: dict) -> dict:
        self_data = state["self"]
        opp_data = state["opponent"]
        artifacts = state.get("artifacts", [])
        minions = state.get("minions", [])
        turn = state.get("turn", 0)
        board_size = state.get("board_size", 10)

        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        opp_hp = opp_data["hp"]
        opp_mana = opp_data["mana"]
        opp_cooldowns = opp_data.get("cooldowns", {})
        shield_active = self_data.get("shield_active", False)
        opp_shield = opp_data.get("shield_active", False)

        # Track opponent movement patterns
        if self._last_opp_pos == opp_pos:
            self._turns_stationary += 1
        else:
            self._turns_stationary = 0
        self._last_opp_pos = opp_pos

        hp_advantage = hp - opp_hp
        mana_advantage = mana - opp_mana

        # DETERMINE COMBAT MODE (inspired by Adaptive Bot)
        if hp <= 40 or mana <= 30:
            mode = "resource"
        elif hp_advantage >= 25 or turn >= 50:
            mode = "aggressive"
        elif hp_advantage <= -20:
            mode = "defensive"
        else:
            mode = "minion_master"  # Default to sustained pressure strategy

        move = [0, 0]
        spell = None

        # Helper functions
        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        def move_toward(start, target):
            dx = target[0] - start[0]
            dy = target[1] - start[1]
            return [
                1 if dx > 0 else -1 if dx < 0 else 0,
                1 if dy > 0 else -1 if dy < 0 else 0,
            ]

        def move_away(start, target):
            toward = move_toward(start, target)
            return [-toward[0], -toward[1]]

        def clamp_pos(pos):
            return [max(0, min(board_size - 1, pos[0])), max(0, min(board_size - 1, pos[1]))]

        def predict_opponent_move():
            """Enhanced prediction based on opponent state and behavior."""
            # If opponent is stationary (likely casting), predict they stay
            if self._turns_stationary >= 1:
                return [0, 0]
            
            # Low resources = artifact hunting
            if artifacts and (opp_mana <= 60 or opp_hp <= 60):
                nearest_artifact = min(
                    artifacts, key=lambda a: chebyshev(opp_pos, a["position"])
                )
                if chebyshev(opp_pos, nearest_artifact["position"]) <= 5:
                    return move_toward(opp_pos, nearest_artifact["position"])
            
            # Aggressive bots charge forward
            if opp_mana <= 30:
                return move_toward(opp_pos, self_pos)
            
            # Defensive bots retreat when low HP
            if opp_hp <= 40 and hp > opp_hp:
                return move_away(opp_pos, self_pos)
            
            # Default: move toward us
            return move_toward(opp_pos, self_pos)

        def get_predicted_opp_pos():
            """Get the predicted position of opponent next turn."""
            opp_move = predict_opponent_move()
            return clamp_pos([opp_pos[0] + opp_move[0], opp_pos[1] + opp_move[1]])

        def get_splash_target():
            """Get optimal fireball target for splash damage."""
            predicted = get_predicted_opp_pos()
            # If opponent likely won't move, aim adjacent for guaranteed splash
            if predicted == opp_pos:
                # Aim at adjacent tile they might move to
                for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
                    target = [opp_pos[0] + dx, opp_pos[1] + dy]
                    if 0 <= target[0] < board_size and 0 <= target[1] < board_size:
                        return target
            return predicted

        # Count minions
        enemy_minions = [m for m in minions if m["owner"] != self_data["name"]]
        my_minions = [m for m in minions if m["owner"] == self_data["name"]]
        has_minion = len(my_minions) > 0

        # Calculate distances
        dist_to_opp = chebyshev(self_pos, opp_pos)
        manhattan_to_opp = manhattan(self_pos, opp_pos)

        # Find all adjacent enemies (wizards and minions)
        adjacent_enemies = []
        if manhattan_to_opp == 1:
            adjacent_enemies.append({"pos": opp_pos, "hp": opp_hp, "is_wizard": True})
        for m in enemy_minions:
            if manhattan(self_pos, m["position"]) == 1:
                adjacent_enemies.append({"pos": m["position"], "hp": m["hp"], "is_wizard": False})

        # Categorize artifacts
        health_artifacts = [a for a in artifacts if a["type"] == "health"]
        mana_artifacts = [a for a in artifacts if a["type"] == "mana"]
        cooldown_artifacts = [a for a in artifacts if a["type"] == "cooldown"]

        # ===== PRIORITY 0: IMMEDIATE LETHAL CHECKS =====
        
        # Melee kills (bypasses shields - melee does 5 damage)
        if adjacent_enemies and cooldowns["melee_attack"] == 0:
            for enemy in adjacent_enemies:
                if enemy["is_wizard"] and enemy["hp"] <= 5:
                    return {"move": [0, 0], "spell": {"name": "melee_attack", "target": enemy["pos"]}}
        
        # Fireball kills (must check shield)
        if cooldowns["fireball"] == 0 and mana >= 30 and dist_to_opp <= 5:
            if not opp_shield and opp_hp <= 20:
                return {"move": [0, 0], "spell": {"name": "fireball", "target": opp_pos}}

        # ===== EXECUTE MODE-BASED STRATEGY =====
        
        if mode == "aggressive":
            return self._aggressive_mode(state, hp_advantage, has_minion)
        elif mode == "defensive":
            return self._defensive_mode(state, hp_advantage, has_minion)
        elif mode == "resource":
            return self._resource_mode(state, has_minion)
        else:  # minion_master mode
            return self._minion_master_mode(state, hp_advantage, has_minion)

    def _aggressive_mode(self, state, hp_advantage, has_minion):
        """All-out attack mode when we have HP advantage or late game."""
        self_data = state["self"]
        opp_data = state["opponent"]
        board_size = state.get("board_size", 10)
        
        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        opp_shield = opp_data.get("shield_active", False)
        
        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        def move_toward(start, target):
            dx = target[0] - start[0]
            dy = target[1] - start[1]
            return [
                1 if dx > 0 else -1 if dx < 0 else 0,
                1 if dy > 0 else -1 if dy < 0 else 0,
            ]
        
        dist = chebyshev(self_pos, opp_pos)
        
        # MELEE priority - 10 damage, free
        if manhattan(self_pos, opp_pos) == 1 and cooldowns["melee_attack"] == 0:
            return {"move": [0, 0], "spell": {"name": "melee_attack", "target": opp_pos}}
        
        # BLINK into melee range
        if cooldowns["blink"] == 0 and mana >= 10 and 1 < dist <= 2:
            adj_positions = [
                [opp_pos[0] + dx, opp_pos[1] + dy]
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
                if 0 <= opp_pos[0] + dx < board_size and 0 <= opp_pos[1] + dy < board_size
            ]
            if adj_positions:
                closest = min(adj_positions, key=lambda p: chebyshev(self_pos, p))
                return {"move": [0, 0], "spell": {"name": "blink", "target": closest}}
        
        # FIREBALL for damage
        if cooldowns["fireball"] == 0 and mana >= 30 and dist <= 5:
            return {"move": move_toward(self_pos, opp_pos),
                    "spell": {"name": "fireball", "target": opp_pos}}
        
        # TELEPORT to close gap if far
        if cooldowns["teleport"] == 0 and mana >= 20 and dist > 4:
            adj_positions = [
                [opp_pos[0] + dx, opp_pos[1] + dy]
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
                if 0 <= opp_pos[0] + dx < board_size and 0 <= opp_pos[1] + dy < board_size
            ]
            if adj_positions:
                closest = min(adj_positions, key=lambda p: chebyshev(self_pos, p))
                return {"move": [0, 0], "spell": {"name": "teleport", "target": closest}}
        
        # Just charge forward
        return {"move": move_toward(self_pos, opp_pos), "spell": None}

    def _defensive_mode(self, state, hp_advantage, has_minion):
        """Defensive mode when at HP disadvantage - focus on survival."""
        self_data = state["self"]
        opp_data = state["opponent"]
        artifacts = state.get("artifacts", [])
        board_size = state.get("board_size", 10)
        
        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        shield_active = self_data.get("shield_active", False)
        
        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        def move_toward(start, target):
            dx = target[0] - start[0]
            dy = target[1] - start[1]
            return [
                1 if dx > 0 else -1 if dx < 0 else 0,
                1 if dy > 0 else -1 if dy < 0 else 0,
            ]
        
        def move_away(start, threat):
            dx = start[0] - threat[0]
            dy = start[1] - threat[1]
            move_x = 1 if dx > 0 else -1 if dx < 0 else 0
            move_y = 1 if dy > 0 else -1 if dy < 0 else 0
            new_x = start[0] + move_x
            new_y = start[1] + move_y
            if not (0 <= new_x < board_size):
                move_x = 0
            if not (0 <= new_y < board_size):
                move_y = 0
            return [move_x, move_y]
        
        dist = chebyshev(self_pos, opp_pos)
        health_artifacts = [a for a in artifacts if a["type"] == "health"]
        
        # SHIELD first if not active
        if not shield_active and cooldowns["shield"] == 0 and mana >= 20:
            return {"move": move_away(self_pos, opp_pos), "spell": {"name": "shield"}}
        
        # HEAL if low
        if hp <= 70 and cooldowns["heal"] == 0 and mana >= 25:
            return {"move": move_away(self_pos, opp_pos), "spell": {"name": "heal"}}
        
        # TELEPORT to health artifact
        if health_artifacts and cooldowns["teleport"] == 0 and mana >= 20:
            nearest = min(health_artifacts, key=lambda a: chebyshev(self_pos, a["position"]))
            if chebyshev(self_pos, nearest["position"]) >= 3:
                return {"move": [0, 0], "spell": {"name": "teleport", "target": nearest["position"]}}
        
        # Counter with MELEE if forced
        if manhattan(self_pos, opp_pos) == 1 and cooldowns["melee_attack"] == 0:
            return {"move": [0, 0], "spell": {"name": "melee_attack", "target": opp_pos}}
        
        # FIREBALL while kiting
        if cooldowns["fireball"] == 0 and mana >= 30 and dist <= 5:
            return {"move": move_away(self_pos, opp_pos),
                    "spell": {"name": "fireball", "target": opp_pos}}
        
        # Just kite
        return {"move": move_away(self_pos, opp_pos), "spell": None}

    def _resource_mode(self, state, has_minion):
        """Resource collection mode when low on HP/mana."""
        self_data = state["self"]
        opp_data = state["opponent"]
        artifacts = state.get("artifacts", [])
        board_size = state.get("board_size", 10)
        
        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        
        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        def move_toward(start, target):
            dx = target[0] - start[0]
            dy = target[1] - start[1]
            return [
                1 if dx > 0 else -1 if dx < 0 else 0,
                1 if dy > 0 else -1 if dy < 0 else 0,
            ]
        
        def move_away(start, threat):
            dx = start[0] - threat[0]
            dy = start[1] - threat[1]
            move_x = 1 if dx > 0 else -1 if dx < 0 else 0
            move_y = 1 if dy > 0 else -1 if dy < 0 else 0
            new_x = start[0] + move_x
            new_y = start[1] + move_y
            if not (0 <= new_x < board_size):
                move_x = 0
            if not (0 <= new_y < board_size):
                move_y = 0
            return [move_x, move_y]
        
        health_artifacts = [a for a in artifacts if a["type"] == "health"]
        mana_artifacts = [a for a in artifacts if a["type"] == "mana"]
        
        # EMERGENCY HEAL
        if hp <= 50 and cooldowns["heal"] == 0 and mana >= 25:
            return {"move": move_away(self_pos, opp_pos), "spell": {"name": "heal"}}
        
        # TELEPORT to priority artifact
        if artifacts and cooldowns["teleport"] == 0 and mana >= 20:
            if hp < mana:
                priority = health_artifacts if health_artifacts else artifacts
            else:
                priority = mana_artifacts if mana_artifacts else artifacts
            
            nearest = min(priority, key=lambda a: chebyshev(self_pos, a["position"]))
            if chebyshev(self_pos, nearest["position"]) >= 2:
                return {"move": [0, 0], "spell": {"name": "teleport", "target": nearest["position"]}}
        
        # BLINK to nearby artifact
        if artifacts and cooldowns["blink"] == 0 and mana >= 10:
            nearest = min(artifacts, key=lambda a: chebyshev(self_pos, a["position"]))
            art_dist = chebyshev(self_pos, nearest["position"])
            if 0 < art_dist <= 2:
                return {"move": [0, 0], "spell": {"name": "blink", "target": nearest["position"]}}
        
        # Counter melee if adjacent
        if manhattan(self_pos, opp_pos) == 1 and cooldowns["melee_attack"] == 0:
            return {"move": [0, 0], "spell": {"name": "melee_attack", "target": opp_pos}}
        
        # Move toward artifacts
        if artifacts:
            nearest = min(artifacts, key=lambda a: chebyshev(self_pos, a["position"]))
            return {"move": move_toward(self_pos, nearest["position"]), "spell": None}
        
        # Fallback: kite
        return {"move": move_away(self_pos, opp_pos), "spell": None}

    def _minion_master_mode(self, state, hp_advantage, has_minion):
        """Minion Master mode - sustain minion pressure like the #1 bot (89% win rate)."""
        self_data = state["self"]
        opp_data = state["opponent"]
        artifacts = state.get("artifacts", [])
        minions = state.get("minions", [])
        board_size = state.get("board_size", 10)
        turn = state.get("turn", 0)
        
        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        shield_active = self_data.get("shield_active", False)
        opp_shield = opp_data.get("shield_active", False)
        
        my_minions = [m for m in minions if m["owner"] == self_data["name"]]
        
        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        def move_toward(start, target):
            dx = target[0] - start[0]
            dy = target[1] - start[1]
            return [
                1 if dx > 0 else -1 if dx < 0 else 0,
                1 if dy > 0 else -1 if dy < 0 else 0,
            ]
        
        def move_away(start, threat):
            dx = start[0] - threat[0]
            dy = start[1] - threat[1]
            move_x = 1 if dx > 0 else -1 if dx < 0 else 0
            move_y = 1 if dy > 0 else -1 if dy < 0 else 0
            new_x = start[0] + move_x
            new_y = start[1] + move_y
            if not (0 <= new_x < board_size):
                move_x = 0
            if not (0 <= new_y < board_size):
                move_y = 0
            return [move_x, move_y]
        
        dist = chebyshev(self_pos, opp_pos)
        mana_artifacts = [a for a in artifacts if a["type"] == "mana"]
        
        # 1. SUMMON minion if we don't have one (HIGHEST PRIORITY - key to #1 bot)
        if not has_minion and cooldowns["summon"] == 0 and mana >= 50:
            return {"move": move_toward(self_pos, opp_pos), "spell": {"name": "summon"}}
        
        # 2. MELEE if adjacent
        if manhattan(self_pos, opp_pos) == 1 and cooldowns["melee_attack"] == 0:
            return {"move": [0, 0], "spell": {"name": "melee_attack", "target": opp_pos}}
        
        # 3. Emergency SHIELD
        if not shield_active and cooldowns["shield"] == 0 and mana >= 20 and hp <= 60 and dist <= 3:
            return {"move": move_toward(self_pos, opp_pos), "spell": {"name": "shield"}}
        
        # 4. Collect MANA artifacts to sustain summoning (critical strategy)
        if mana < 50 and mana_artifacts:
            nearest = min(mana_artifacts, key=lambda a: chebyshev(self_pos, a["position"]))
            art_dist = chebyshev(self_pos, nearest["position"])
            
            # Teleport to distant mana
            if cooldowns["teleport"] == 0 and mana >= 20 and art_dist > 3:
                return {"move": [0, 0], "spell": {"name": "teleport", "target": nearest["position"]}}
            
            # Blink to nearby mana
            if cooldowns["blink"] == 0 and mana >= 10 and 0 < art_dist <= 2:
                return {"move": [0, 0], "spell": {"name": "blink", "target": nearest["position"]}}
            
            # Walk toward mana
            return {"move": move_toward(self_pos, nearest["position"]), "spell": None}
        
        # 5. FIREBALL to support minion
        if has_minion and cooldowns["fireball"] == 0 and mana >= 30 and dist <= 5:
            return {"move": move_toward(self_pos, opp_pos),
                    "spell": {"name": "fireball", "target": opp_pos}}
        
        # 6. HEAL when needed
        if hp <= 55 and cooldowns["heal"] == 0 and mana >= 25:
            return {"move": move_toward(self_pos, opp_pos), "spell": {"name": "heal"}}
        
        # 7. Position: Stay at medium range if we have minion, let it work
        if has_minion and my_minions:
            minion_pos = my_minions[0]["position"]
            minion_dist_to_opp = chebyshev(minion_pos, opp_pos)
            
            # If minion is close to opponent, support from distance
            if minion_dist_to_opp <= 3:
                if dist < 4:
                    return {"move": move_away(self_pos, opp_pos), "spell": None}
                else:
                    return {"move": [0, 0], "spell": None}  # Hold position
            else:
                # Push opponent toward minion
                return {"move": move_toward(self_pos, opp_pos), "spell": None}
        else:
            # No minion, close gap
            return {"move": move_toward(self_pos, opp_pos), "spell": None}

