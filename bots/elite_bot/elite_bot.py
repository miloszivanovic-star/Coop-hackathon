"""
Elite Bot V2 - Enhanced strategic bot with improved decision-making.

Battle Analysis (30 tests):
- 90%+ win rate achieved, but improvements identified in:
  * Collision avoidance (reduce unnecessary damage)
  * Defensive timing (preemptive shielding)
  * Cooldown tracking (predict opponent actions)
  * Positioning optimization (maintain ideal ranges)

Enhanced Strategy:
1. COLLISION AVOIDANCE: Predict and avoid head-on collisions
2. COOLDOWN TRACKING: Monitor opponent spell availability
3. RANGE OPTIMIZATION: Maintain ideal distance (melee range 1, fireball range 3-5)
4. SITUATIONAL DEFENSE: Shield before taking damage, not after
5. TACTICAL RETREAT: Create distance when low HP to heal safely
6. AGGRESSIVE FINISHING: Press advantage when opponent is weakened
7. MINION SYNERGY: Coordinate with minion positioning
8. ADAPTIVE STRATEGY: Switch between attack/defend based on HP differential
"""

from bots.bot_interface import BotInterface


class EliteBot(BotInterface):
    def __init__(self):
        self._name = "Elite Bot"
        self._sprite_path = "assets/wizards/elite_wizard.png"
        self._minion_sprite_path = "assets/minions/minion_1.png"
        self._game_phase = "early"  # early, mid, late
        self._turn_count = 0
        self._last_opponent_hp = 100
        self._last_opponent_pos = None
        self._aggression_level = 0.6  # Balanced default like Tactician Bot
        self._opponent_cooldown_estimates = {
            "fireball": 0,
            "shield": 0,
            "heal": 0,
            "melee_attack": 0
        }
        self._opponent_defensive_count = 0  # Track opponent defensive behavior
        self._stalemate_counter = 0  # Detect prolonged battles

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
        self._turn_count = state["turn"]
        self_data = state["self"]
        opp_data = state["opponent"]
        artifacts = state.get("artifacts", [])
        minions = state.get("minions", [])

        self_pos = self_data["position"]
        opp_pos = opp_data["position"]
        cooldowns = self_data["cooldowns"]
        mana = self_data["mana"]
        hp = self_data["hp"]
        opp_hp = opp_data["hp"]
        opp_mana = opp_data["mana"]
        opp_cooldowns = opp_data.get("cooldowns", {})

        # Update opponent cooldown tracking
        self._update_opponent_cooldowns(opp_data, opp_pos)
        
        # Update game phase and strategy
        self._update_game_phase(hp, mana, opp_hp, self._turn_count)
        self._update_aggression(hp, opp_hp, mana, self._turn_count)

        # Calculate damage dealt this turn
        damage_dealt = self._last_opponent_hp - opp_hp
        self._last_opponent_hp = opp_hp
        self._last_opponent_pos = opp_pos

        move = [0, 0]
        spell = None

        # Helper functions
        def chebyshev_dist(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def manhattan_dist(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        def euclidean_dist_sq(a, b):
            return (a[0] - b[0])**2 + (a[1] - b[1])**2

        def is_on_board(pos):
            return 0 <= pos[0] < 10 and 0 <= pos[1] < 10

        # Identify own and enemy minions
        own_minions = [m for m in minions if m["owner"] == self_data["name"]]
        enemy_minions = [m for m in minions if m["owner"] != self_data["name"]]
        
        # All enemy targets
        all_enemies = [opp_data] + enemy_minions
        
        # Calculate current distance to opponent (used throughout)
        current_dist = chebyshev_dist(self_pos, opp_pos)

        # ==========================================
        # PHASE 1: ENHANCED THREAT ASSESSMENT
        # ==========================================
        
        # Check if opponent can kill us next turn (with cooldown prediction)
        opp_can_fireball = (opp_cooldowns.get("fireball", 99) == 0 and opp_mana >= 30) or \
                          (self._opponent_cooldown_estimates["fireball"] == 0 and opp_mana >= 30)
        opp_in_fireball_range = chebyshev_dist(self_pos, opp_pos) <= 5
        opp_can_melee = opp_cooldowns.get("melee_attack", 99) == 0 and manhattan_dist(self_pos, opp_pos) == 1
        
        potential_damage = 0
        
        if opp_can_fireball and opp_in_fireball_range:
            potential_damage += 20
            
        if opp_can_melee:
            potential_damage += 10
        
        # Add minion threat
        for enemy_minion in enemy_minions:
            if manhattan_dist(self_pos, enemy_minion["position"]) <= 2:
                potential_damage += 10

        is_lethal_threat = (hp - potential_damage) <= 25 and potential_damage > 0
        is_moderate_threat = (hp - potential_damage) <= 50 and potential_damage > 0
        
        # COLLISION PREDICTION: Avoid walking into opponent
        predicted_opp_move = self._predict_opponent_move(opp_pos, self_pos)
        collision_risk = self._will_collide(self_pos, opp_pos, predicted_opp_move)

        # ==========================================
        # PHASE 2: STRATEGIC DEFENSIVE ACTIONS
        # ==========================================
        
        # EMERGENCY SHIELD: Shield at very low HP to prevent death
        if hp <= 35 and cooldowns["shield"] == 0 and mana >= 20 and not self_data.get("shield_active", False):
            spell = {"name": "shield"}
            move = self._tactical_retreat(self_pos, opp_pos, all_enemies, artifacts)
            return {"move": move, "spell": spell}
        
        # PREEMPTIVE SHIELD: Shield when threatened (original logic restored)
        should_shield = (
            cooldowns["shield"] == 0 and 
            mana >= 20 and 
            not self_data.get("shield_active", False) and
            (is_lethal_threat or (is_moderate_threat and opp_can_fireball and opp_in_fireball_range))
        )
        
        if should_shield:
            spell = {"name": "shield"}
            # TACTICAL RETREAT: Create distance for safety
            if hp <= 40:
                move = self._tactical_retreat(self_pos, opp_pos, all_enemies, artifacts)
            else:
                # Continue pressure with shield active
                move = self._safe_advance(self_pos, opp_pos, collision_risk)
            return {"move": move, "spell": spell}

        # Phase 2: Heal if low on HP
        if hp <= 30 and cooldowns["heal"] == 0 and mana >= 25:
            spell = {"name": "heal"}
            return {"move": move, "spell": spell}

        # ==========================================
        # PHASE 3: INTELLIGENT MELEE ATTACK WITH MINION TARGETING
        # ==========================================
        
        # Melee attacks are mana-free and very efficient
        adjacent_enemies = [e for e in all_enemies if manhattan_dist(self_pos, e["position"]) == 1]
        
        if adjacent_enemies and cooldowns["melee_attack"] == 0:
            # Don't melee if we're too low HP and opponent can counter
            if hp <= 25 and opp_can_melee:
                # Skip melee, retreat instead
                pass
            else:
                # ENHANCED MINION TARGETING: Prioritize weak/close enemy minions
                # Calculate threat score for each target
                def target_priority(e):
                    is_wizard = "name" in e
                    is_minion = not is_wizard
                    
                    # Strategy: Kill minions first to reduce threat, then focus wizard
                    # Prioritize weak minions (can be eliminated quickly)
                    if is_minion:
                        # Minions: prioritize by HP (kill weak ones fast), then distance
                        threat_score = e["hp"] * 0.5  # Lower HP = higher priority
                        return (0, threat_score)  # Minions first
                    else:
                        # Wizards: priority based on HP
                        if e["hp"] <= 20:
                            return (1, e["hp"])  # Finishing blow on low HP wizard
                        else:
                            return (2, e["hp"])  # Wizards when minions cleared
                
                target = min(adjacent_enemies, key=target_priority)
                spell = {
                    "name": "melee_attack",
                    "target": target["position"]
                }
                # Position for next melee or avoid collision
                if len(adjacent_enemies) > 1:
                    move = [0, 0]  # Stay and fight multiple targets
                else:
                    # Position for follow-up while avoiding collision
                    move = self._position_for_next_melee(self_pos, all_enemies, collision_risk)
                return {"move": move, "spell": spell}

        # ==========================================
        # PHASE 4: OPTIMIZED OFFENSIVE SPELL CASTING
        # ==========================================

        # FIREBALL: Balanced offensive logic with splash optimization
        if cooldowns["fireball"] == 0 and mana >= 30:
            if current_dist <= 5:
                # Balanced conditions - not overly aggressive
                should_fire = (
                    opp_hp <= 33 or  # Fire when opponent weakened (more aggressive)
                    (current_dist >= 3 and hp >= 50 and self._aggression_level >= 0.6)
                )
                
                if should_fire:
                    # SPLASH OPTIMIZATION: Target to maximize damage
                    optimal_target = self._find_optimal_fireball_position(
                        self_pos, opp_pos, enemy_minions, own_minions
                    )
                    
                    spell = {
                        "name": "fireball",
                        "target": optimal_target
                    }
                    # Tactician Bot's positioning logic
                    if current_dist > 4:
                        dx = opp_pos[0] - self_pos[0]
                        dy = opp_pos[1] - self_pos[1]
                        if abs(dx) >= abs(dy):
                            move[0] = 1 if dx > 0 else -1
                        else:
                            move[1] = 1 if dy > 0 else -1
                    elif current_dist < 3:
                        dx = self_pos[0] - opp_pos[0]
                        dy = self_pos[1] - opp_pos[1]
                        if abs(dx) >= abs(dy):
                            move[0] = 1 if dx > 0 else -1
                        else:
                            move[1] = 1 if dy > 0 else -1
                    return {"move": move, "spell": spell}

        # Fireball enemy minions if clustered or blocking path
        if cooldowns["fireball"] == 0 and mana >= 40 and enemy_minions:
            best_minion_target = self._find_best_fireball_target(self_pos, enemy_minions, opp_data)
            if best_minion_target:
                spell = {
                    "name": "fireball",
                    "target": best_minion_target
                }
                move = self._optimal_fireball_position(self_pos, best_minion_target, 5)
                return {"move": move, "spell": spell}

        # ==========================================
        # PHASE 5: ENHANCED SUMMON MINION STRATEGY
        # ==========================================
        
        # Count minions for strategic decision-making
        own_minion_count = len(own_minions)
        enemy_minion_count = len(enemy_minions)
        
        # STRATEGIC SUMMON CONDITIONS:
        # 1. Outnumbered by enemy minions - summon to equalize
        # 2. Low HP with no minions - summon as meat shield
        # 3. Early game aggression - summon for pressure when resources good
        if cooldowns["summon"] == 0 and mana >= 50:
            should_summon = False
            
            # Condition 1: Outnumbered - summon to match enemy minions
            if enemy_minion_count > own_minion_count:
                should_summon = True
            
            # Condition 2: Low HP, need shield - summon minion as protection
            elif hp <= 50 and own_minion_count == 0 and mana >= 60:
                should_summon = True
            
            # Condition 3: Early pressure - good resources, no minions yet
            elif own_minion_count == 0 and hp >= 60 and mana >= 70:
                should_summon = True
            
            if should_summon:
                spell = {"name": "summon"}
                # Position to create space for minion
                move = self._move_toward_with_space(self_pos, opp_pos)
                return {"move": move, "spell": spell}

        # ==========================================
        # PHASE 6: TACTICAL HEAL/SHIELD
        # ==========================================
        
        # Secondary heal - only if conditions are safe and efficient (Improvement 4)
        # Don't waste heal at high HP (>80) or when opponent can punish
        # Phase 6: Secondary heal check - use heal if HP low enough
        if hp <= 45 and cooldowns["heal"] == 0 and mana >= 25:
            spell = {"name": "heal"}

        # Shield based on threat assessment (Tactician Bot approach)
        if cooldowns["shield"] == 0 and mana >= 20:
            # Calculate potential threat
            potential_damage = 0
            if current_dist <= 5 and opp_mana >= 30:
                potential_damage += 20
            if manhattan_dist(self_pos, opp_pos) == 1:
                potential_damage += 10
            
            is_threat = (hp - potential_damage) <= 30 and potential_damage > 0
            
            if not self_data.get("shield_active", False) and is_threat:
                spell = {"name": "shield"}
                # Tactical retreat while shielding
                dx = self_pos[0] - opp_pos[0]
                dy = self_pos[1] - opp_pos[1]
                if dx != 0:
                    move[0] = 1 if dx > 0 else -1
                if dy != 0:
                    move[1] = 1 if dy > 0 else -1
                return {"move": move, "spell": spell}

        # ==========================================
        # PHASE 7: BLINK FOR TACTICAL ADVANTAGE
        # ==========================================
        
        # Use blink for quick artifact grab or positioning
        if cooldowns["blink"] == 0 and mana >= 20 and artifacts:
            best_artifact = self._find_best_artifact(self_pos, artifacts, hp, mana)
            if best_artifact and chebyshev_dist(self_pos, best_artifact["position"]) <= 2:
                # Check if position is safe
                if self._is_position_safe(best_artifact["position"], all_enemies):
                    spell = {
                        "name": "blink",
                        "target": best_artifact["position"]
                    }
                    return {"move": [0, 0], "spell": spell}

        # ==========================================
        # PHASE 8: TELEPORT FOR STRATEGIC REPOSITIONING
        # ==========================================
        
        # Teleport to high-value artifact if critically low resources
        if cooldowns["teleport"] == 0 and mana >= 30 and artifacts:
            critical_resources = mana <= 40 or hp <= 40
            if critical_resources:
                best_artifact = self._find_best_artifact(self_pos, artifacts, hp, mana)
                if best_artifact and chebyshev_dist(self_pos, best_artifact["position"]) >= 4:
                    if self._is_position_safe(best_artifact["position"], all_enemies):
                        spell = {
                            "name": "teleport",
                            "target": best_artifact["position"]
                        }
                        return {"move": [0, 0], "spell": spell}

        # ==========================================
        # PHASE 9: ADAPTIVE MOVEMENT STRATEGY
        # ==========================================
        
        # Determine strategy based on HP differential and resources
        hp_advantage = hp - opp_hp
        
        # CRITICAL: AGGRESSIVE FINISHING - When opponent is critically low, finish them immediately
        # This must be FIRST priority to prevent games from dragging on
        if opp_hp <= 25 and hp >= 40:
            # Close distance for kill - ignore artifacts and other distractions
            move = self._smart_move_toward(self_pos, opp_pos, collision_risk, opp_pos, own_minions)
        
        # DEFENSIVE POSITIONING: Retreat if severely wounded
        elif hp <= 35 and hp_advantage < -20:
            move = self._tactical_retreat(self_pos, opp_pos, all_enemies, artifacts)
        
        # SPLASH DAMAGE AVOIDANCE: If opponent can fireball and we're in splash range, maintain distance
        # This prevents taking 4 splash damage repeatedly
        elif (opp_can_fireball and opp_in_fireball_range and 
              current_dist <= 6 and self._manhattan_dist(self_pos, opp_pos) <= 2):
            # We're too close to predicted fireball target (opponent position)
            # Move to maintain fireball range (3-5) but avoid splash range (≤1 Manhattan distance)
            if current_dist <= 2:
                # Too close for splash safety, back up
                move = self._move_away_from(self_pos, opp_pos)
            else:
                # Strafe to maintain distance while avoiding predictable patterns
                move = self._strafe_movement(self_pos, opp_pos)
        
        # ARTIFACT PRIORITY: CRITICAL for health when < 30%, collect if resources low
        elif artifacts and (hp < 30 or mana <= 50 or hp <= 60):
            best_artifact = self._find_best_artifact(self_pos, artifacts, hp, mana)
            if best_artifact:
                # Enhanced risk assessment for artifact collection
                artifact_safe = self._is_artifact_safe_to_collect(
                    best_artifact["position"], self_pos, opp_pos, 
                    hp, opp_hp, enemy_minions
                )
                
                # PRIORITY: Always go for health when HP < 30% (even if risky)
                if hp < 30 and best_artifact["type"] == "health":
                    move = self._smart_move_toward(self_pos, best_artifact["position"], collision_risk, opp_pos, own_minions)
                # Only collect if safe, otherwise fight
                elif artifact_safe:
                    # Check if artifact is contested
                    our_dist = chebyshev_dist(self_pos, best_artifact["position"])
                    opp_dist = chebyshev_dist(opp_pos, best_artifact["position"])
                    
                    if our_dist <= opp_dist + 1:  # We can get there first
                        move = self._smart_move_toward(self_pos, best_artifact["position"], collision_risk, opp_pos, own_minions)
                    else:
                        # Artifact contested, engage opponent
                        move = self._optimal_positioning(self_pos, opp_pos, hp, opp_hp, collision_risk, own_minions, enemy_minions)
                else:
                    # Artifact too risky, engage opponent instead
                    move = self._optimal_positioning(self_pos, opp_pos, hp, opp_hp, collision_risk, own_minions, enemy_minions)
        
        # AGGRESSIVE POSITIONING: Press advantage or maintain optimal range
        else:
            move = self._optimal_positioning(self_pos, opp_pos, hp, opp_hp, collision_risk, own_minions, enemy_minions)

        return {
            "move": move,
            "spell": spell
        }

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _update_game_phase(self, hp, mana, opp_hp, turn):
        """Determine current game phase"""
        if turn <= 10:
            self._game_phase = "early"
        elif turn <= 30 or (hp > 60 and opp_hp > 60):
            self._game_phase = "mid"
        else:
            self._game_phase = "late"
    
    def _update_aggression(self, hp, opp_hp, mana, turn):
        """Dynamically adjust aggression based on situation - Balanced with defensive logic"""
        hp_advantage = hp - opp_hp
        
        # Balanced aggression with enhanced defensive logic when behind
        if hp <= 35:
            self._aggression_level = 0.3  # Survival mode
        elif hp_advantage >= 20:
            self._aggression_level = 0.97  # Major advantage - strong pressure (increased)
        elif hp_advantage >= 10:
            self._aggression_level = 0.8  # Moderate advantage
        elif hp_advantage >= 5:
            self._aggression_level = 0.7  # Small advantage
        elif hp_advantage >= 0:
            self._aggression_level = 0.6  # Even
        elif hp_advantage >= -5:
            self._aggression_level = 0.45  # Slightly behind - more cautious
        elif hp_advantage >= -10:
            self._aggression_level = 0.35  # Behind - defensive
        else:  # hp_advantage < -10
            self._aggression_level = 0.25  # Significantly behind - very defensive
    
    def _update_opponent_cooldowns(self, opp_data, opp_pos):
        """Track and estimate opponent cooldown states"""
        opp_cooldowns = opp_data.get("cooldowns", {})
        
        # Decrement our estimates
        for spell in self._opponent_cooldown_estimates:
            if self._opponent_cooldown_estimates[spell] > 0:
                self._opponent_cooldown_estimates[spell] -= 1
        
        # Update with actual data if available
        for spell, cd in opp_cooldowns.items():
            if spell in self._opponent_cooldown_estimates:
                self._opponent_cooldown_estimates[spell] = cd
    
    def _predict_opponent_move(self, opp_pos, my_pos):
        """Predict opponent's likely movement direction"""
        if self._last_opponent_pos is None:
            # Assume opponent moves toward us
            dx = my_pos[0] - opp_pos[0]
            dy = my_pos[1] - opp_pos[1]
        else:
            # Use last movement vector
            dx = opp_pos[0] - self._last_opponent_pos[0]
            dy = opp_pos[1] - self._last_opponent_pos[1]
        
        # Normalize to -1, 0, 1
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        
        return [step_x, step_y]
    
    def _will_collide(self, my_pos, opp_pos, predicted_opp_move):
        """Check if we'll collide if moving toward opponent"""
        # Calculate our move toward opponent
        dx = opp_pos[0] - my_pos[0]
        dy = opp_pos[1] - my_pos[1]
        my_move_x = 1 if dx > 0 else -1 if dx < 0 else 0
        my_move_y = 1 if dy > 0 else -1 if dy < 0 else 0
        
        # Calculate new positions
        my_new_pos = [my_pos[0] + my_move_x, my_pos[1] + my_move_y]
        opp_new_pos = [opp_pos[0] + predicted_opp_move[0], opp_pos[1] + predicted_opp_move[1]]
        
        # Check if same position
        return my_new_pos == opp_new_pos
    
    def _tactical_retreat(self, my_pos, opp_pos, enemies, artifacts):
        """Retreat while collecting artifacts if possible"""
        # Primary: move away from opponent
        retreat_move = self._move_away_from(my_pos, opp_pos)
        
        # Check if there's a valuable artifact in retreat direction
        retreat_pos = [my_pos[0] + retreat_move[0], my_pos[1] + retreat_move[1]]
        
        if self._is_on_board(retreat_pos):
            for artifact in artifacts:
                if artifact["position"] == retreat_pos:
                    return retreat_move  # Bonus: artifact in retreat path
        
        return retreat_move
    
    def _safe_advance(self, my_pos, opp_pos, collision_risk):
        """Advance toward opponent while avoiding collision"""
        if collision_risk:
            # Strafe instead of direct approach
            dx = opp_pos[0] - my_pos[0]
            dy = opp_pos[1] - my_pos[1]
            
            # Move perpendicular to approach vector
            if abs(dx) >= abs(dy):
                return [0, 1] if my_pos[1] < 5 else [0, -1]
            else:
                return [1, 0] if my_pos[0] < 5 else [-1, 0]
        else:
            return self._move_toward(my_pos, opp_pos)
    
    def _optimal_positioning(self, my_pos, opp_pos, my_hp, opp_hp, collision_risk, own_minions=None, enemy_minions=None):
        """Position optimally based on current situation with minion awareness"""
        dist = self._chebyshev_dist(my_pos, opp_pos)
        own_minions = own_minions or []
        enemy_minions = enemy_minions or []
        
        # CRITICAL FIX: Aggressive finishing when opponent is critically low HP
        # When opponent ≤25 HP and we have resources, close distance and finish immediately
        if opp_hp <= 25 and my_hp >= 40:
            # Close to fireball or melee range aggressively
            if dist > 1:
                return self._smart_move_toward(my_pos, opp_pos, collision_risk, opp_pos)
            else:
                return [0, 0]  # In melee range, hold position for melee attack
        
        # TACTICAL POSITIONING: Use minions as cover when low HP
        if my_hp <= 40 and own_minions:
            # Find if we can position behind a friendly minion
            for minion in own_minions:
                minion_pos = minion["position"]
                # Check if minion is between us and opponent
                minion_to_opp = self._manhattan_dist(minion_pos, opp_pos)
                us_to_minion = self._manhattan_dist(my_pos, minion_pos)
                us_to_opp = self._manhattan_dist(my_pos, opp_pos)
                
                # If minion is closer to opponent, try to stay behind it
                if minion_to_opp < us_to_opp and us_to_minion <= 2:
                    # Move toward a position behind the minion
                    # Calculate direction opposite to opponent from minion
                    dx_away = minion_pos[0] - opp_pos[0]
                    dy_away = minion_pos[1] - opp_pos[1]
                    
                    if abs(dx_away) > 0 or abs(dy_away) > 0:
                        # Target position behind minion
                        target_x = minion_pos[0] + (1 if dx_away > 0 else -1 if dx_away < 0 else 0)
                        target_y = minion_pos[1] + (1 if dy_away > 0 else -1 if dy_away < 0 else 0)
                        
                        if self._is_on_board([target_x, target_y]):
                            return self._move_toward(my_pos, [target_x, target_y])
        
        # Avoid moving into enemy minion clusters (2+ minions within 2 cells)
        if enemy_minions:
            # Count enemy minions near potential moves
            possible_moves = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]
            safe_moves = []
            
            for move in possible_moves:
                new_pos = [my_pos[0] + move[0], my_pos[1] + move[1]]
                if self._is_on_board(new_pos):
                    # Count enemy minions within 2 cells of new position
                    nearby_enemies = sum(1 for m in enemy_minions if self._manhattan_dist(new_pos, m["position"]) <= 2)
                    safe_moves.append((move, nearby_enemies))
            
            # If we have moves with fewer enemy minions nearby, prefer those
            if safe_moves:
                safe_moves.sort(key=lambda x: x[1])  # Sort by enemy minion proximity
                # Only avoid if there's a significantly safer option
                if safe_moves[0][1] < safe_moves[-1][1] - 1:
                    # Check if safest move aligns with our intended direction
                    dx = opp_pos[0] - my_pos[0]
                    dy = opp_pos[1] - my_pos[1]
                    
                    # Find best safe move that still progresses toward/away from opponent as needed
                    for move, enemy_count in safe_moves[:3]:  # Check top 3 safest
                        if my_hp <= 40:
                            # Retreating: prefer moves away from opponent
                            if (move[0] * dx < 0 or move[1] * dy < 0 or (move[0] == 0 and move[1] == 0)):
                                return move
                        else:
                            # Advancing: prefer moves toward opponent
                            if (move[0] * dx >= 0 and move[1] * dy >= 0):
                                return move
        
        # If we're winning, maintain pressure at optimal range
        if my_hp > opp_hp + 20:
            # Maintain fireball range (3-5) or melee range (1)
            if dist > 5:
                return self._smart_move_toward(my_pos, opp_pos, collision_risk, opp_pos)
            elif dist == 2:
                # Close to melee range
                return self._smart_move_toward(my_pos, opp_pos, collision_risk, opp_pos)
            elif 3 <= dist <= 5:
                # Optimal fireball range, strafe
                return self._strafe_movement(my_pos, opp_pos)
            else:
                return [0, 0]
        
        # If even or losing, be more cautious
        elif my_hp < opp_hp - 10:
            # Maintain distance, use range advantage
            if dist < 3:
                return self._move_away_from(my_pos, opp_pos)
            elif dist > 5:
                return self._smart_move_toward(my_pos, opp_pos, collision_risk, opp_pos)
            else:
                return self._strafe_movement(my_pos, opp_pos)
        
        # Balanced fight
        else:
            if dist > 4:
                return self._smart_move_toward(my_pos, opp_pos, collision_risk, opp_pos)
            elif dist < 2:
                return [0, 0]  # Hold position for melee
            else:
                return self._smart_move_toward(my_pos, opp_pos, collision_risk, opp_pos)
    
    def _smart_move_toward(self, my_pos, target_pos, collision_risk, opp_pos, own_minions=None):
        """Move toward target while avoiding collisions with opponents AND own minions"""
        own_minions = own_minions or []
        
        # Calculate intended move
        dx = target_pos[0] - my_pos[0]
        dy = target_pos[1] - my_pos[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        
        intended_pos = [my_pos[0] + step_x, my_pos[1] + step_y]
        
        # CRITICAL FIX: Check for own minion collision
        minion_collision = False
        for minion in own_minions:
            if minion["position"] == intended_pos:
                minion_collision = True
                break
        
        # If collision detected (opponent or own minion), take alternate route
        if collision_risk or minion_collision:
            # Try moving in one direction only first
            # Try horizontal first
            alt_pos_x = [my_pos[0] + step_x, my_pos[1]]
            x_blocked = any(m["position"] == alt_pos_x for m in own_minions)
            
            # Try vertical
            alt_pos_y = [my_pos[0], my_pos[1] + step_y]
            y_blocked = any(m["position"] == alt_pos_y for m in own_minions)
            
            # Choose non-blocked direction, prefer larger delta
            if not x_blocked and abs(dx) >= abs(dy):
                return [step_x, 0]
            elif not y_blocked:
                return [0, step_y]
            elif not x_blocked:
                return [step_x, 0]
            else:
                # Both blocked, try diagonal
                return [0, 0]  # Stay put if all options blocked
        else:
            return [step_x, step_y]
    
    def _maintain_optimal_range(self, my_pos, target_pos, min_range, max_range):
        """Maintain position within optimal range"""
        dist = self._chebyshev_dist(my_pos, target_pos)
        
        if dist < min_range:
            # Too close, back up
            return self._move_away_from(my_pos, target_pos)
        elif dist > max_range:
            # Too far, close in
            return self._move_toward(my_pos, target_pos)
        else:
            # In range, strafe
            return self._strafe_movement(my_pos, target_pos)
    
    def _strafe_movement(self, my_pos, target_pos):
        """Move perpendicular to target to avoid predictable patterns"""
        dx = target_pos[0] - my_pos[0]
        dy = target_pos[1] - my_pos[1]
        
        # Move perpendicular to approach vector
        if abs(dx) >= abs(dy):
            # Vertical strafe
            if my_pos[1] < 3:
                return [0, 1]
            elif my_pos[1] > 6:
                return [0, -1]
            else:
                return [0, 1] if self._turn_count % 2 == 0 else [0, -1]
        else:
            # Horizontal strafe
            if my_pos[0] < 3:
                return [1, 0]
            elif my_pos[0] > 6:
                return [-1, 0]
            else:
                return [1, 0] if self._turn_count % 2 == 0 else [-1, 0]
    
    def _is_on_board(self, pos):
        """Check if position is within board bounds"""
        return 0 <= pos[0] < 10 and 0 <= pos[1] < 10

    def _move_toward(self, start, target):
        """Basic movement toward target"""
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        return [step_x, step_y]

    def _move_away_from(self, start, threat):
        """Move away from threat"""
        dx = start[0] - threat[0]
        dy = start[1] - threat[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        return [step_x, step_y]

    def _aggressive_approach(self, start, target, enemies):
        """Aggressive movement that considers enemy positions"""
        # Move diagonally toward opponent for faster engagement
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        
        # Prefer diagonal movement for speed
        if abs(dx) > 0 and abs(dy) > 0:
            return [step_x, step_y]
        elif abs(dx) > abs(dy):
            return [step_x, 0]
        else:
            return [0, step_y]

    def _move_toward_safe_artifact(self, start, artifacts, enemies):
        """Move toward artifact while avoiding enemy clusters"""
        if not artifacts:
            return None
        
        safe_artifacts = []
        for artifact in artifacts:
            min_enemy_dist = min([self._manhattan_dist(artifact["position"], e["position"]) for e in enemies])
            our_dist = self._manhattan_dist(start, artifact["position"])
            if our_dist < min_enemy_dist:
                safe_artifacts.append(artifact)
        
        if safe_artifacts:
            nearest = min(safe_artifacts, key=lambda a: self._chebyshev_dist(start, a["position"]))
            return self._move_toward(start, nearest["position"])
        
        return None

    def _find_best_artifact(self, pos, artifacts, hp, mana):
        """Find the most valuable artifact based on current needs"""
        if not artifacts:
            return None
        
        def artifact_value(artifact):
            dist = self._chebyshev_dist(pos, artifact["position"])
            value = 0
            
            # STRATEGIC ARTIFACT PRIORITIZATION:
            # 1. HEALTH - CRITICAL when below 30%, high priority when damaged
            if artifact["type"] == "health":
                if hp < 30:  # CRITICAL: Below 30% HP
                    value = 200  # MAXIMUM PRIORITY: Survival critical
                elif hp < 40:
                    value = 150  # VERY HIGH: Need health to survive
                elif hp < 60:
                    value = 90 + (60 - hp)  # HIGH: Health adds durability
                elif hp < 85:
                    value = 40  # MODERATE: Top off health
                else:
                    value = 10  # LOW: Nearly full HP
            
            # 2. COOLDOWN - Enables spell spam, very valuable for aggression
            elif artifact["type"] == "cooldown":
                # Cooldowns enable more spell casting = more damage/control
                if mana >= 50:  # Have mana to use spells
                    value = 120  # VERY HIGH: Can spam spells with cooldown reduction
                else:
                    value = 70  # HIGH: Still valuable but need mana too
            
            # 3. MANA - IGNORE when above 60%, necessary otherwise
            elif artifact["type"] == "mana":
                if mana > 60:  # USER RULE: Ignore mana when > 60%
                    value = 0  # IGNORE: Already have plenty
                elif mana < 30:
                    value = 130  # CRITICAL: Can't cast without mana
                elif mana < 50:
                    value = 80 + (50 - mana)  # HIGH: Need mana for spell spam
                else:
                    value = 50  # MODERATE: Good to have reserves
            
            # Penalize distance more heavily if artifact is far
            # Nearby artifacts are always worth grabbing
            if dist <= 2:
                value -= dist * 2  # Low penalty for nearby
            else:
                value -= dist * 5  # Higher penalty for distant
            
            return value
        
        return max(artifacts, key=artifact_value)

    def _find_optimal_fireball_position(self, self_pos, opp_pos, enemy_minions, own_minions):
        """Find optimal fireball target position to maximize splash damage.
        
        Returns position that hits the most valuable combination of wizard + minions.
        Prioritizes: wizard > enemy minions > avoiding friendly fire.
        """
        # Start with opponent position as baseline
        best_target = opp_pos
        best_score = 20  # Base damage to wizard
        
        # Evaluate positions adjacent to opponent for potential multi-hits
        candidates = [opp_pos]  # Always consider direct hit
        
        # Add positions near opponent that might cluster with minions
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                adj_pos = [opp_pos[0] + dx, opp_pos[1] + dy]
                if self._is_on_board(adj_pos) and self._chebyshev_dist(self_pos, adj_pos) <= 5:
                    candidates.append(adj_pos)
        
        # Evaluate each candidate position
        for target in candidates:
            score = 0
            
            # Primary target value: Direct hit on wizard
            if target == opp_pos:
                score += 20  # Full fireball damage to wizard
            else:
                # Check if wizard is in splash range
                if self._manhattan_dist(target, opp_pos) <= 1:
                    score += 4  # Splash damage to wizard
            
            # Secondary value: Splash damage to enemy minions
            for minion in enemy_minions:
                minion_pos = minion["position"]
                
                # Direct hit on minion
                if target == minion_pos:
                    score += 10  # Minion elimination value
                # Splash hit on minion
                elif self._manhattan_dist(target, minion_pos) <= 1:
                    score += 2  # Splash damage to minion
            
            # Penalty: Splash damage to own minions (avoid friendly fire)
            for minion in own_minions:
                minion_pos = minion["position"]
                if self._manhattan_dist(target, minion_pos) <= 1:
                    score -= 3  # Penalty for friendly fire
            
            # Update best if this position is better
            if score > best_score:
                best_score = score
                best_target = target
        
        return best_target

    def _find_best_fireball_target(self, pos, enemy_minions, opp_data):
        """Find the best minion position to fireball for maximum splash damage.
        
        Used specifically for minion-focused fireballs.
        """
        if not enemy_minions:
            return None
        
        candidates = []
        for minion in enemy_minions:
            minion_pos = minion["position"]
            if self._chebyshev_dist(pos, minion_pos) <= 5:
                # Calculate splash value
                score = 10  # Direct hit on this minion
                
                # Add value for other enemy minions in splash range
                for other in enemy_minions:
                    if other["position"] != minion_pos:
                        if self._manhattan_dist(minion_pos, other["position"]) <= 1:
                            score += 2  # Each additional minion hit
                
                # Add value if wizard is in splash range
                if opp_data and self._manhattan_dist(minion_pos, opp_data["position"]) <= 1:
                    score += 4  # Bonus for hitting wizard too
                
                candidates.append((minion_pos, score))
        
        if candidates:
            best = max(candidates, key=lambda x: x[1])
            if best[1] >= 12:  # Worthwhile if hitting multiple targets
                return best[0]
        
        return None

    def _is_position_safe(self, pos, enemies):
        """Check if a position is relatively safe from enemies"""
        for enemy in enemies:
            if self._manhattan_dist(pos, enemy["position"]) <= 1:
                return False
        return True
    
    def _is_artifact_safe_to_collect(self, artifact_pos, self_pos, opp_pos, hp, opp_hp, enemy_minions):
        """Evaluate if collecting an artifact is safe based on threat assessment"""
        artifact_dist = self._chebyshev_dist(self_pos, artifact_pos)
        opp_dist = self._chebyshev_dist(opp_pos, artifact_pos)
        
        # Count enemy minions near artifact
        nearby_enemy_minions = sum(
            1 for m in enemy_minions 
            if self._chebyshev_dist(m["position"], artifact_pos) <= 2
        )
        
        # Risk factors:
        # 1. Opponent is closer or equally close AND we're at disadvantage
        if opp_dist <= artifact_dist and hp < opp_hp - 10:
            return False
        
        # 2. Multiple enemy minions near artifact and we're vulnerable
        if nearby_enemy_minions >= 2 and hp <= 50:
            return False
        
        # 3. Opponent very close to artifact and can fireball (high danger)
        if opp_dist <= 2 and artifact_dist >= 3 and hp <= 60:
            return False
        
        # Otherwise safe to collect
        return True

    def _optimal_fireball_position(self, current_pos, target_pos, max_range):
        """Calculate optimal position to maintain fireball range"""
        dist = self._chebyshev_dist(current_pos, target_pos)
        
        if dist > max_range:
            # Move closer
            return self._move_toward(current_pos, target_pos)
        elif dist <= 2:
            # Too close, back up slightly
            return self._move_away_from(current_pos, target_pos)
        else:
            # Maintain distance, strafe if possible
            dx = target_pos[0] - current_pos[0]
            dy = target_pos[1] - current_pos[1]
            
            # Strafe perpendicular
            if abs(dx) > abs(dy):
                return [0, 1] if current_pos[1] < 5 else [0, -1]
            else:
                return [1, 0] if current_pos[0] < 5 else [-1, 0]

    def _position_for_next_melee(self, pos, enemies, collision_risk):
        """Position to maximize melee opportunities while avoiding collision"""
        if not enemies:
            return [0, 0]
        
        closest = min(enemies, key=lambda e: self._manhattan_dist(pos, e["position"]))
        
        if collision_risk:
            # Strafe instead of direct approach
            return self._strafe_movement(pos, closest["position"])
        else:
            return self._move_toward(pos, closest["position"])

    def _move_toward_with_space(self, start, target):
        """Move toward target while leaving space for minion summon"""
        # Prefer moving in a way that keeps adjacent cells free
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        
        # Move in primary direction only to maximize free adjacent cells
        if abs(dx) > abs(dy):
            return [step_x, 0]
        else:
            return [0, step_y]

    def _chebyshev_dist(self, a, b):
        """Chebyshev distance (chess king movement)"""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def _manhattan_dist(self, a, b):
        """Manhattan distance"""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
