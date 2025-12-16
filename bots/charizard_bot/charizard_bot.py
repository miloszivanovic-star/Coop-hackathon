from bots.bot_interface import BotInterface


class TacticalBot(BotInterface):
    """
    Tactical bot with clear strategic priorities:
    1. Shield when don't have one and can cast it (move closer to opponent)
    2. Melee attack when close to opponent (then retreat to fireball range)
    3. Use fireball if none of above were used
    4. Heal if HP is lower than max damage possible (20 from fireball) and retreat
    5. Spawn minion at beginning and prioritize if HP not too low
    6. Teleport to artifacts when urgent (low resources)
    """
    
    def __init__(self):
        self._name = "Charizard Bot"
        self._sprite_path = "assets/wizards/charizard.png"
        self._minion_sprite_path = "assets/minions/charmander.png"
        self._turn_count = 0

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
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        has_shield = self_data.get("shield_active", False)  # Get shield status from game state
        
        self._turn_count += 1
        
        move = [0, 0]
        spell = None
        
        # Distance calculation functions
        def chebyshev_dist(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        
        def manhattan_dist(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        dist_to_opp = chebyshev_dist(self_pos, opp_pos)
        manhattan_to_opp = manhattan_dist(self_pos, opp_pos)
        
        # Get minion info
        my_minions = [m for m in minions if m["owner"] == self_data["name"]]
        enemy_minions = [m for m in minions if m["owner"] != self_data["name"]]
        
        # Constants
        HP_CRITICAL = 20  # Very low HP - prioritize heal over attack
        HP_LOW = 40  # Low HP threshold for healing
        FIREBALL_RANGE_MIN = 2  # Expanded from 3
        FIREBALL_RANGE_MAX = 5
        
        # PRIORITY 1: Spawn minion at beginning (first 2 turns) if mana sufficient
        if self._turn_count <= 2 and cooldowns["summon"] == 0 and mana >= 70 and hp > 30:
            if len(my_minions) == 0:
                spell = {"name": "summon"}
                # Move toward fireball range while summoning
                move = self._maintain_fireball_range(self_pos, opp_pos, dist_to_opp)
                return {"move": move, "spell": spell}
        
        # PRIORITY 2: CRITICAL HEAL - if HP very low, heal before anything else
        if hp <= HP_CRITICAL and cooldowns["heal"] == 0 and mana >= 25:
            spell = {"name": "heal"}
            # Move away from opponent while healing
            move = self._move_away(self_pos, opp_pos)
            return {"move": move, "spell": spell}
        
        # PRIORITY 3: Shield when don't have one and can cast it (move closer)
        if not has_shield and cooldowns["shield"] == 0 and mana >= 20:
            # Cast shield and move closer to opponent
            spell = {"name": "shield"}
            move = self._move_toward(self_pos, opp_pos)
            return {"move": move, "spell": spell}
        
        # PRIORITY 4: Melee attack adjacent ENEMY MINIONS first (defensive)
        adjacent_enemy_minions = [m for m in enemy_minions if manhattan_dist(self_pos, m["position"]) == 1]
        if adjacent_enemy_minions and cooldowns["melee_attack"] == 0:
            # Target lowest HP minion
            target = min(adjacent_enemy_minions, key=lambda m: m["hp"])
            spell = {
                "name": "melee_attack",
                "target": target["position"]
            }
            # Retreat after melee to fireball range
            move = self._retreat_to_fireball_range(self_pos, opp_pos, dist_to_opp)
            return {"move": move, "spell": spell}
        
        # PRIORITY 5: Melee attack opponent if adjacent
        if manhattan_to_opp == 1 and cooldowns["melee_attack"] == 0:
            spell = {
                "name": "melee_attack",
                "target": opp_pos
            }
            # Retreat after melee to fireball range
            move = self._retreat_to_fireball_range(self_pos, opp_pos, dist_to_opp)
            return {"move": move, "spell": spell}
        
        # PRIORITY 6: Heal if HP lower than safe threshold
        if hp <= HP_LOW and cooldowns["heal"] == 0 and mana >= 25:
            spell = {"name": "heal"}
            # Move away from opponent but stay within fireball range
            move = self._retreat_to_fireball_range(self_pos, opp_pos, dist_to_opp)
            return {"move": move, "spell": spell}
        
        # PRIORITY 7: Spawn minion if we don't have one and HP is not too low
        if cooldowns["summon"] == 0 and mana >= 50 and hp > HP_LOW:
            if len(my_minions) == 0:
                spell = {"name": "summon"}
                # Move toward fireball range while summoning
                move = self._maintain_fireball_range(self_pos, opp_pos, dist_to_opp)
                return {"move": move, "spell": spell}
        
        # PRIORITY 8: Blink for tactical repositioning
        if cooldowns["blink"] == 0 and mana >= 10:
            # Blink away if too close and low HP
            if dist_to_opp <= 2 and hp <= HP_LOW:
                # Calculate escape direction (2 squares away)
                dx = self_pos[0] - opp_pos[0]
                dy = self_pos[1] - opp_pos[1]
                # Normalize and multiply by blink distance (2)
                if dx != 0:
                    dx = (2 if dx > 0 else -2)
                if dy != 0:
                    dy = (2 if dy > 0 else -2)
                
                target_x = max(0, min(9, self_pos[0] + dx))
                target_y = max(0, min(9, self_pos[1] + dy))
                
                spell = {
                    "name": "blink",
                    "target": [target_x, target_y]
                }
                return {"move": [0, 0], "spell": spell}
            
            # Blink toward opponent if too far and good HP
            elif dist_to_opp >= 6 and hp >= 60 and mana >= 40:
                dx = opp_pos[0] - self_pos[0]
                dy = opp_pos[1] - self_pos[1]
                # Move 2 steps closer
                step_x = 2 if dx > 0 else -2 if dx < 0 else 0
                step_y = 2 if dy > 0 else -2 if dy < 0 else 0
                
                target_x = max(0, min(9, self_pos[0] + step_x))
                target_y = max(0, min(9, self_pos[1] + step_y))
                
                spell = {
                    "name": "blink",
                    "target": [target_x, target_y]
                }
                return {"move": [0, 0], "spell": spell}
        
        # PRIORITY 9: Teleport to artifacts if urgent (low mana or low HP)
        if cooldowns["teleport"] == 0 and mana >= 20 and artifacts:
            if mana <= 45 or hp <= 35:  # Adjusted threshold to ensure mana reserve
                nearest = min(artifacts, key=lambda a: chebyshev_dist(self_pos, a["position"]))
                spell = {
                    "name": "teleport",
                    "target": nearest["position"]
                }
                move = [0, 0]  # Teleport handles movement
                return {"move": move, "spell": spell}
        
        # PRIORITY 10: Use fireball if in range and available (expanded range 2-5)
        if cooldowns["fireball"] == 0 and mana >= 30:
            if FIREBALL_RANGE_MIN <= dist_to_opp <= FIREBALL_RANGE_MAX:
                spell = {
                    "name": "fireball",
                    "target": opp_pos
                }
                # Maintain optimal distance
                move = self._maintain_fireball_range(self_pos, opp_pos, dist_to_opp)
                return {"move": move, "spell": spell}
        
        # MOVEMENT LOGIC (when no spell cast)
        # If we're too close, retreat to fireball range
        if dist_to_opp < FIREBALL_RANGE_MIN:
            move = self._retreat_to_fireball_range(self_pos, opp_pos, dist_to_opp)
        # If we're too far, approach to fireball range
        elif dist_to_opp > FIREBALL_RANGE_MAX:
            move = self._move_toward(self_pos, opp_pos)
        # If at optimal range, maintain it
        else:
            move = self._maintain_fireball_range(self_pos, opp_pos, dist_to_opp)
        
        # If we have low resources and artifacts exist, move toward nearest artifact
        if (mana <= 50 or hp <= 50) and artifacts:
            nearest_artifact = min(artifacts, key=lambda a: chebyshev_dist(self_pos, a["position"]))
            artifact_dist = chebyshev_dist(self_pos, nearest_artifact["position"])
            # Move to artifact if closer than opponent or resources critical
            if artifact_dist < dist_to_opp or mana <= 35 or hp <= 35:
                move = self._move_toward(self_pos, nearest_artifact["position"])
        
        return {
            "move": move,
            "spell": spell
        }
    
    def _move_toward(self, start, target):
        """Move one step toward target."""
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        return [step_x, step_y]
    
    def _move_away(self, start, threat):
        """Move one step away from threat."""
        dx = start[0] - threat[0]
        dy = start[1] - threat[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        return [step_x, step_y]
    
    def _retreat_to_fireball_range(self, self_pos, opp_pos, current_dist):
        """
        Retreat away from opponent but stay close enough for fireball.
        Target: distance 2-5 (fireball range)
        """
        if current_dist < 2:
            # Too close - retreat
            return self._move_away(self_pos, opp_pos)
        elif current_dist >= 2 and current_dist <= 5:
            # Already at good range - maintain or slightly retreat if very close
            if current_dist <= 2:
                return self._move_away(self_pos, opp_pos)
            else:
                return [0, 0]  # Hold position
        else:
            # Too far - approach slightly
            return self._move_toward(self_pos, opp_pos)
    
    def _maintain_fireball_range(self, self_pos, opp_pos, current_dist):
        """
        Maintain optimal fireball range (2-5 squares).
        Use strafing if at optimal distance with boundary checks.
        """
        if current_dist < 2:
            # Too close - retreat
            return self._move_away(self_pos, opp_pos)
        elif current_dist > 5:
            # Too far - advance
            return self._move_toward(self_pos, opp_pos)
        else:
            # Optimal range - strafe (move perpendicular) with boundary checks
            dx = opp_pos[0] - self_pos[0]
            dy = opp_pos[1] - self_pos[1]
            
            # Move perpendicular to avoid being predictable
            if abs(dx) > abs(dy):
                # Move vertically if opponent is more horizontal
                # Check boundaries: board is 0-9
                if self_pos[1] < 5 and self_pos[1] < 9:
                    return [0, 1]
                elif self_pos[1] >= 5 and self_pos[1] > 0:
                    return [0, -1]
                else:
                    # At boundary, try horizontal instead
                    if self_pos[0] < 9:
                        return [1, 0]
                    elif self_pos[0] > 0:
                        return [-1, 0]
                    else:
                        return [0, 0]
            else:
                # Move horizontally if opponent is more vertical
                if self_pos[0] < 5 and self_pos[0] < 9:
                    return [1, 0]
                elif self_pos[0] >= 5 and self_pos[0] > 0:
                    return [-1, 0]
                else:
                    # At boundary, try vertical instead
                    if self_pos[1] < 9:
                        return [0, 1]
                    elif self_pos[1] > 0:
                        return [0, -1]
                    else:
                        return [0, 0]
