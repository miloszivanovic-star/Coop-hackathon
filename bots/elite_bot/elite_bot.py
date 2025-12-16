"""Venom Bot V9 - Anti-Runner Optimization

Key Changes from V8:
- RUNNER DETECTION: Detect when opponent is running away (distance increasing)
- PURSUIT BONUS: When chasing runner, value closing distance more
- CORNER TRAP: Bonus for pushing opponent toward edges/corners
- PREDICTIVE MOVEMENT: Move to cut off likely escape routes

Target: Improve Rincewind matchup (24.5% to 35%+) with max 2% loss elsewhere
"""

from bots.bot_interface import BotInterface


class EliteBot(BotInterface):
    def __init__(self):
        self._name = "Venom Bot"
        self._sprite_path = "assets/wizards/venom.png"
        self._minion_sprite_path = "assets/minions/venom_minion.png"

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
        turn = state.get("turn", 0)
        
        my_pos = self_data["position"]
        opp_pos = opp_data["position"]
        my_hp = self_data["hp"]
        opp_hp = opp_data["hp"]
        my_mana = self_data["mana"]
        cooldowns = self_data["cooldowns"]
        opp_cooldowns = opp_data.get("cooldowns", {})
        opp_mana = opp_data.get("mana", 100)
        opp_shield = opp_data.get("shield_active", False)

        # Constants
        FIREBALL_DMG = 20
        MELEE_DMG = 10
        HEAL_AMT = 20
        SHIELD_BLOCK = 20
        BOARD_SIZE = 10

        # --- Helpers ---
        def manhattan_dist(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
            
        def chebyshev_dist(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def get_valid_moves(pos):
            moves = [[0, 0]]  # Stay
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = pos[0] + dx, pos[1] + dy
                    if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                        moves.append([dx, dy])
            return moves

        # --- Count enemy minions for threat awareness ---
        enemy_minions = [m for m in minions if m["owner"] != self.name]
        my_minions = [m for m in minions if m["owner"] == self.name]
        
        # V9: Runner detection - opponents who maintain distance
        dist_to_opp = chebyshev_dist(my_pos, opp_pos)
        opp_can_escape = (opp_cooldowns.get("teleport", 0) == 0 and opp_mana >= 20) or \
                         (opp_cooldowns.get("blink", 0) == 0 and opp_mana >= 10)
        opp_edge_dist = min(opp_pos[0], opp_pos[1], 9 - opp_pos[0], 9 - opp_pos[1])
        
        # Runner behavior: keeping large distance consistently
        RUNNER_BEHAVIOR = dist_to_opp >= 5 and turn > 20
        
        # --- Minion Threat Map: Distance to nearest enemy minion ---
        def nearest_enemy_minion_dist(pos):
            if not enemy_minions:
                return 99
            return min(manhattan_dist(pos, m["position"]) for m in enemy_minions)

        # --- Dynamic Weights (V7 - Balanced like IvraBot) ---
        W_SURVIVAL = 5.0 
        W_AGGRO = 15.0
        W_MANA = 0.2
        
        # Defensive Shift
        if my_hp < 40:
            W_SURVIVAL = 7.0
        if my_hp < 25:
            W_SURVIVAL = 12.0
            
        # Offensive Shift (Bloodlust) - trigger when opponent wounded
        if opp_hp < 62 and my_hp > 30:
            W_AGGRO = 78.0
        
        # FINISHER MODE
        FINISHER_MODE = opp_hp < 30 and my_hp > 25
        if FINISHER_MODE:
            W_AGGRO = 150.0
            W_SURVIVAL = 3.0
        
        # V8: Anti-heal pressure - when opponent likely healing, be aggressive
        OPP_LIKELY_HEALING = opp_hp < 50 and opp_mana >= 25 and opp_cooldowns.get("heal", 0) == 0
        if OPP_LIKELY_HEALING and my_hp > 40:
            W_AGGRO *= 1.3  # Push the attack when they want to heal
            
        # V8: Earlier late game urgency (turn 60 instead of 70)
        LATE_GAME = turn > 60
        if LATE_GAME:
            W_AGGRO *= 1.25  # Slightly more aggressive
        if turn > 80:
            W_AGGRO *= 1.3  # Even more aggressive to avoid draws
            
        # V9: Anti-runner - DON'T chase aggressively, use minions
        # (no additional W_AGGRO boost - chasing is counterproductive)

        # --- Scoring Function (V7 - Minion Aware) ---
        def score_action(act_type, target=None, move_vec=[0, 0]):
            sim_hp = my_hp
            sim_opp_hp = opp_hp
            sim_mana = my_mana
            sim_pos = [my_pos[0] + move_vec[0], my_pos[1] + move_vec[1]]
            
            # Validate position
            if not (0 <= sim_pos[0] < BOARD_SIZE and 0 <= sim_pos[1] < BOARD_SIZE):
                return -99999
            
            # 1. Apply Action Costs & Effects
            action_cost = 0
            dmg_dealt = 0
            healed = 0
            shielded = False
            killed_minion = False
            
            if act_type == "fireball":
                action_cost = 30
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    blocked = SHIELD_BLOCK if opp_shield else 0
                    dmg_dealt = max(0, FIREBALL_DMG - blocked)
                    
            elif act_type == "melee_attack":
                action_cost = 0
                if target:
                    if manhattan_dist(sim_pos, target) == 1:
                        # Check if target is wizard or minion
                        if target == list(opp_pos):
                            dmg_dealt = MELEE_DMG
                        else:
                            # Minion attack
                            killed_minion = True
                    
            elif act_type == "heal":
                action_cost = 25
                healed = HEAL_AMT
                
            elif act_type == "shield":
                action_cost = 20
                shielded = True
                
            elif act_type == "blink":
                action_cost = 10
                sim_pos = list(target) if target else sim_pos
                
            elif act_type == "teleport":
                action_cost = 20
                sim_pos = list(target) if target else sim_pos

            elif act_type == "summon":
                action_cost = 50

            # Update simulation state
            sim_mana -= action_cost 
            sim_hp = min(100, sim_hp + healed)
            
            # 2. Simulate Enemy Retaliation
            incoming = 0
            
            # Fireball Threat
            if opp_mana >= 30 and opp_cooldowns.get("fireball", 0) == 0:
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    dmg = FIREBALL_DMG
                    if shielded or self_data.get("shield_active"):
                        dmg = max(0, dmg - SHIELD_BLOCK)
                    incoming += dmg
            
            # Melee Threat
            if manhattan_dist(sim_pos, opp_pos) == 1 and opp_cooldowns.get("melee_attack", 0) == 0:
                incoming += MELEE_DMG
                
            # V7 CRITICAL: Enemy Minion Threat
            # Count ALL enemy minions that could hit us
            for m in enemy_minions:
                if manhattan_dist(sim_pos, m["position"]) <= 1:
                    incoming += MELEE_DMG  # Minions deal 10 damage on collision

            sim_hp -= incoming
            sim_opp_hp -= dmg_dealt
            
            # 3. Calculate Score
            
            # Win/Loss Check
            if sim_hp <= 0:
                return -10000.0
            if sim_opp_hp <= 0:
                return 10000.0
            
            score = 0.0
            
            # HP Score
            score += sim_hp * W_SURVIVAL
            
            # Opponent HP Score
            score -= sim_opp_hp * W_AGGRO
            
            # Mana Score
            score += sim_mana * W_MANA
            
            # V8: HIGHER MINION KILL BONUS (critical vs Mih Bot)
            if killed_minion:
                score += 65  # Even higher priority vs minion-heavy bots!
                # V9: MUCH higher vs runners - their minions are the real damage source!
                if RUNNER_BEHAVIOR:
                    score += 40  # Total: +105 for killing minion when enemy is running
            
            # V7: MINION AVOIDANCE - Penalty for being near enemy minions (if not killing them)
            if not killed_minion and enemy_minions:
                min_minion_dist = nearest_enemy_minion_dist(sim_pos)
                if min_minion_dist == 0:
                    score -= 80  # On same tile as minion - very bad
                elif min_minion_dist == 1:
                    score -= 40  # Adjacent to minion - will take damage
                elif min_minion_dist == 2:
                    score -= 10  # Close to minion - might get hit
            
            # Artifact Pickup
            if artifacts:
                for a in artifacts:
                    art_pos = a["position"]
                    my_art_dist = manhattan_dist(sim_pos, art_pos)
                    opp_art_dist = manhattan_dist(opp_pos, art_pos)
                    
                    if my_art_dist == 0:
                        if a["type"] == "health":
                            score += 60 if my_hp < 60 else 25
                            # V9: Artifact denial vs runners - take health before they can teleport to it
                            if RUNNER_BEHAVIOR and opp_hp < 50:
                                score += 30  # Deny health artifacts when enemy is hurt
                        elif a["type"] == "cooldown":
                            score += 35
                        elif a["type"] == "mana":
                            score += 30 if my_mana < 50 else 15
                    elif my_art_dist <= 2:
                        if a["type"] == "health":
                            if my_hp < 60:
                                score += 20 - my_art_dist * 5
                            # V9: Move toward health artifacts to deny runners
                            elif RUNNER_BEHAVIOR and opp_hp < 50 and my_art_dist < opp_art_dist:
                                score += 15 - my_art_dist * 3
                        elif a["type"] == "mana" and my_mana < 50:
                            score += 12 - my_art_dist * 4
                        else:
                            score += 8 - my_art_dist * 2
            
            # Center Control
            dist_to_center = manhattan_dist(sim_pos, [4, 5])
            score -= dist_to_center * 1.0
            
            # Threat Projection - bonus for being in attack range
            can_fireball_next = chebyshev_dist(sim_pos, opp_pos) <= 5
            can_melee_next = manhattan_dist(sim_pos, opp_pos) == 1
            
            if can_melee_next:
                score += 20.0
            elif can_fireball_next:
                score += 10.0
            
            # HP Advantage Management
            hp_diff = my_hp - opp_hp
            new_dist_to_opp = chebyshev_dist(sim_pos, opp_pos)
            
            if hp_diff > 20:
                # Winning - stay close but not suicidal
                if new_dist_to_opp > 5:
                    score -= 15  # Don't let them escape
            elif hp_diff < -20:
                # Losing - prefer fireball range
                if new_dist_to_opp < 2:
                    score -= 10
                elif 3 <= new_dist_to_opp <= 5:
                    score += 5
            
            # V9: ANTI-RUNNER - Don't chase, use range and minions
            if RUNNER_BEHAVIOR:
                # Bonus for maintaining fireball pressure
                if can_fireball_next:
                    score += 8
                # Penalty for getting too close (they'll just teleport away)
                if new_dist_to_opp <= 2:
                    score -= 5  # Don't waste moves chasing
                # V9.2: Earlier urgency vs runners - need to close out matches
                if turn > 50 and hp_diff > 0:
                    # We're ahead - push for damage
                    if can_melee_next:
                        score += 25  # Strong push for melee finisher
                    elif can_fireball_next:
                        score += 15  # Push fireball pressure
            
            # Summon value (V9: Much higher vs runners!)
            if act_type == "summon":
                if len(my_minions) == 0:
                    score += 35  # V8: Higher priority for first summon
                    if turn <= 2:
                        score += 25  # V8: Extra bonus for early summon
                    # V9: Extra bonus vs runners - minions are persistent chasers!
                    if RUNNER_BEHAVIOR:
                        score += 30  # Much higher priority - minions chase for us
                    # V9.7: Re-summon after turn 15 if minions died
                    elif turn > 15:
                        score += 20  # High priority re-summon
                elif len(my_minions) < 2:
                    # V9.7: Much higher priority for second minion vs runners
                    if RUNNER_BEHAVIOR:
                        score += 45  # Very high priority - sustained pressure wins
                    else:
                        score += 20  # Higher than V9.2
                else:
                    score += 5  # Third minion rarely needed
                # Don't summon in finisher mode
                if FINISHER_MODE:
                    score -= 40
                    
            return score

        # --- Evaluate All Options ---
        valid_moves = get_valid_moves(my_pos)
        
        best_score = -99999
        best_action = {"move": [0, 0], "spell": None}
        
        for dx, dy in valid_moves:
            move_vec = [dx, dy]
            new_pos = [my_pos[0] + dx, my_pos[1] + dy]
            
            # Option A: Just Move
            s = score_action("wait", move_vec=move_vec)
            if s > best_score:
                best_score = s
                best_action = {"move": move_vec, "spell": None}
                
            # Option B: Move + Fireball
            if cooldowns["fireball"] == 0 and my_mana >= 30:
                if chebyshev_dist(new_pos, opp_pos) <= 5:
                    s = score_action("fireball", target=opp_pos, move_vec=move_vec)
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "fireball", "target": opp_pos}}

            # Option C: Move + Melee (CRITICAL in V7 - check minions first!)
            if cooldowns["melee_attack"] == 0:
                targets = []
                
                # V7: Check enemy minions FIRST - they're a priority to kill!
                for m in enemy_minions:
                    if manhattan_dist(new_pos, m["position"]) == 1:
                        targets.append(("minion", m["position"]))
                
                # Then check wizard
                if manhattan_dist(new_pos, opp_pos) == 1:
                    targets.append(("wizard", list(opp_pos)))
                
                for target_type, target_pos in targets:
                    s = score_action("melee_attack", target=target_pos, move_vec=move_vec)
                    # V8: Even higher bonus for killing minions
                    if target_type == "minion":
                        s += 45  # Kill that minion - critical vs Mih Bot!
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "melee_attack", "target": target_pos}}

            # Option D: Move + Shield
            if cooldowns["shield"] == 0 and my_mana >= 20 and not self_data.get("shield_active"):
                dist_opp = chebyshev_dist(new_pos, opp_pos)
                if dist_opp <= 4 or my_hp < 50:
                    s = score_action("shield", move_vec=move_vec)
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "shield"}}
            
            # Option E: Move + Heal (V8: heal earlier when fighting aggressive bots)
            heal_threshold = 85 if len(enemy_minions) > 0 else 80  # More proactive vs minion users
            if cooldowns["heal"] == 0 and my_mana >= 25 and my_hp < heal_threshold:
                s = score_action("heal", move_vec=move_vec)
                if s > best_score:
                    best_score = s
                    best_action = {"move": move_vec, "spell": {"name": "heal"}}
                    
            # Option F: Move + Summon (V8: Prioritize early summon on turn 1-2)
            EARLY_SUMMON = turn <= 2 and len(my_minions) == 0
            if cooldowns["summon"] == 0 and my_mana >= 50 and (EARLY_SUMMON or not FINISHER_MODE):
                s = score_action("summon", move_vec=move_vec)
                if EARLY_SUMMON:
                    s += 40  # Strong preference for turn 1 summon
                if s > best_score:
                    best_score = s
                    summon_pos = None
                    for sdx in [-1, 0, 1]:
                        for sdy in [-1, 0, 1]:
                            if sdx == 0 and sdy == 0:
                                continue
                            sp = [new_pos[0] + sdx, new_pos[1] + sdy]
                            if 0 <= sp[0] < BOARD_SIZE and 0 <= sp[1] < BOARD_SIZE:
                                summon_pos = sp
                                break
                        if summon_pos:
                            break
                    if summon_pos:
                        best_action = {"move": move_vec, "spell": {"name": "summon", "target": summon_pos}}

        # --- Blink (V7: Check minion safety!) ---
        if cooldowns["blink"] == 0 and my_mana >= 10:
            for bx in range(-2, 3):
                for by in range(-2, 3):
                    if manhattan_dist([0, 0], [bx, by]) > 2 or (bx == 0 and by == 0):
                        continue
                    tx, ty = my_pos[0] + bx, my_pos[1] + by
                    if 0 <= tx < BOARD_SIZE and 0 <= ty < BOARD_SIZE:
                        s = score_action("blink", target=[tx, ty])
                        
                        # V7: Penalty for blinking near enemy minions
                        if nearest_enemy_minion_dist([tx, ty]) <= 1:
                            s -= 30  # Don't blink into minion danger
                            
                        if s > best_score:
                            best_score = s
                            best_action = {"move": [0, 0], "spell": {"name": "blink", "target": [tx, ty]}}

        # --- Teleport (V7: Check minion safety!) ---
        if cooldowns["teleport"] == 0 and my_mana >= 20:
            # Teleport to artifacts
            for a in artifacts:
                s = score_action("teleport", target=a["position"])
                
                # V7: Penalty for teleporting near enemy minions
                if nearest_enemy_minion_dist(a["position"]) <= 1:
                    s -= 40  # Don't teleport into minion danger
                    
                if s > best_score:
                    best_score = s
                    best_action = {"move": [0, 0], "spell": {"name": "teleport", "target": a["position"]}}
            
            # Also consider teleporting near opponent (but safe from minions!)
            if FINISHER_MODE or (opp_hp < 50 and my_hp > 40):
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        tx, ty = opp_pos[0] + dx, opp_pos[1] + dy
                        if 0 <= tx < BOARD_SIZE and 0 <= ty < BOARD_SIZE:
                            if manhattan_dist([tx, ty], opp_pos) >= 1:  # Not on top of them
                                # V7: Only if safe from minions
                                if nearest_enemy_minion_dist([tx, ty]) > 1:
                                    s = score_action("teleport", target=[tx, ty])
                                    if s > best_score:
                                        best_score = s
                                        best_action = {"move": [0, 0], "spell": {"name": "teleport", "target": [tx, ty]}}

        return best_action
