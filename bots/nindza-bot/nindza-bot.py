"""
Nindza Tigar - The Ninja Tiger Bot V5

STRATEGY: Hybrid of IvraBot's "Tank Buster" + MihBot's aggressive style
- Score-based decision making with threat simulation
- BLOODLUST MODE: Extreme aggression when opponent < 80 HP
- FINISHER MODE: Maximum aggression when opponent < 45 HP (W_AGGRO=180)
- Kill priority checks for guaranteed kills
- Early game optimization: Summon + Blink to close distance
- Enemy minion targeting (fireball priority when close)
- Artifact denial: Strong teleport priority for health artifacts

PERFORMANCE (200 match tests):
- 90% win rate vs IvraBot
- 60% win rate vs RincewindBot  
- 37% win rate vs MihBot (mirror match)
- 100% vs Sample Bots
"""

from bots.bot_interface import BotInterface


class NindzaTigar(BotInterface):
    def __init__(self):
        self._name = "Nindza Tigar"
        self._sprite_path = "assets/wizards/nindza-tigar.png"
        self._minion_sprite_path = "assets/minions/nindza_minion.svg"

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

        my_pos = self_data["position"]
        opp_pos = opp_data["position"]
        my_hp = self_data["hp"]
        opp_hp = opp_data["hp"]
        my_mana = self_data["mana"]
        cooldowns = self_data["cooldowns"]
        shield_active = self_data.get("shield_active", False)
        opp_shield = opp_data.get("shield_active", False)

        # Constants
        FIREBALL_DMG = 20
        MELEE_DMG = 10  # For threat calculation (minions deal 10)
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

        def is_valid(pos):
            return 0 <= pos[0] < BOARD_SIZE and 0 <= pos[1] < BOARD_SIZE

        # =====================================================
        # EARLY GAME OPTIMIZATION (from MihBot)
        # If far from opponent, close the gap aggressively
        # =====================================================
        dist_to_opp = chebyshev_dist(my_pos, opp_pos)
        is_opening = my_hp == 100 and opp_hp == 100
        my_minions = [m for m in minions if m["owner"] == self.name]
        has_minion = len(my_minions) > 0
        
        if is_opening and dist_to_opp > 6:
            # Calculate move toward opponent
            move_dir = [0, 0]
            if opp_pos[0] > my_pos[0]: move_dir[0] = 1
            elif opp_pos[0] < my_pos[0]: move_dir[0] = -1
            if opp_pos[1] > my_pos[1]: move_dir[1] = 1
            elif opp_pos[1] < my_pos[1]: move_dir[1] = -1
            
            # PRIORITY 1: Summon minion while moving toward opponent
            if not has_minion and cooldowns.get("summon", 99) == 0 and my_mana >= 50:
                return {"move": move_dir, "spell": {"name": "summon"}}
            
            # PRIORITY 2: Blink toward opponent for faster closing
            if cooldowns.get("blink", 99) == 0 and my_mana >= 10:
                best_blink = None
                best_dist = dist_to_opp
                for bx in range(-2, 3):
                    for by in range(-2, 3):
                        if bx == 0 and by == 0:
                            continue
                        target = [my_pos[0] + bx, my_pos[1] + by]
                        if is_valid(target) and chebyshev_dist(my_pos, target) <= 2:
                            new_dist = chebyshev_dist(target, opp_pos)
                            if new_dist < best_dist:
                                best_dist = new_dist
                                best_blink = target
                if best_blink:
                    return {"move": move_dir, "spell": {"name": "blink", "target": best_blink}}
            
            # PRIORITY 3: Just move toward opponent
            return {"move": move_dir, "spell": None}

        # =====================================================
        # PRIORITY CHECK: Can we kill opponent THIS TURN?
        # This prevents them from escaping with teleport/blink
        # =====================================================
        effective_opp_hp = opp_hp
        if opp_shield:
            effective_opp_hp = opp_hp + SHIELD_BLOCK
        
        # Check for fireball kill
        can_fireball = cooldowns.get("fireball", 99) == 0 and my_mana >= 30
        in_fireball_range = chebyshev_dist(my_pos, opp_pos) <= 5
        
        if can_fireball and in_fireball_range and effective_opp_hp <= FIREBALL_DMG:
            # EXECUTE! Fireball will kill them
            return {"move": [0, 0], "spell": {"name": "fireball", "target": opp_pos}}
        
        # Check for melee kill (minions deal 10, wizard melee also 10 based on game logs)
        can_melee = cooldowns.get("melee_attack", 99) == 0
        if can_melee and opp_hp <= 10:  # Melee ignores shield
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    new_pos = [my_pos[0] + dx, my_pos[1] + dy]
                    if is_valid(new_pos) and manhattan_dist(new_pos, opp_pos) == 1:
                        return {"move": [dx, dy], "spell": {"name": "melee_attack", "target": opp_pos}}

        # --- Threat Analysis ---
        threat_fireball = 0
        if opp_data["mana"] >= 30 and opp_data["cooldowns"]["fireball"] == 0 and chebyshev_dist(my_pos, opp_pos) <= 5:
            threat_fireball = FIREBALL_DMG
        
        threat_melee = 0
        if manhattan_dist(my_pos, opp_pos) == 1 and opp_data["cooldowns"]["melee_attack"] == 0:
            threat_melee = MELEE_DMG
            
        threat_minions = 0
        for m in minions:
            if m["owner"] != self.name and manhattan_dist(my_pos, m["position"]) == 1:
                threat_minions += MELEE_DMG

        total_threat = max(threat_fireball, threat_melee) + threat_minions
        
        # Identify minions
        my_minions = [m for m in minions if m["owner"] == self.name]
        enemy_minions = [m for m in minions if m["owner"] != self.name]
        
        # Detect game phase
        hp_lost = (100 - my_hp) + (100 - opp_hp)
        is_late_game = hp_lost > 60 or my_mana == 100
        
        # --- Dynamic Weights (MihBot-style aggressive) ---
        W_SURVIVAL = 3.0   # Lower base survival - be aggressive
        W_AGGRO = 20.0     # High base aggro weight
        W_MANA = 0.0 
        
        # Late game aggression - force decisive action
        if is_late_game:
            W_AGGRO = 50.0
            W_SURVIVAL = 2.0
        
        # Defensive Shift when critically low
        if my_hp < 30:
            W_SURVIVAL = 12.0
        if my_hp < 20:
            W_SURVIVAL = 25.0
            
        # BLOODLUST MODE - trigger finisher earlier (MihBot thresholds)
        if opp_hp < 80 and my_hp > 30:
            W_AGGRO = 60.0
        if opp_hp < 60 and my_hp > 25:
            W_AGGRO = 100.0
        if opp_hp < 45 and my_hp > 20:
            W_AGGRO = 180.0  # FINISHER mode

        # --- Score Action ---
        def score_action(act_type, target=None, move_vec=[0, 0]):
            sim_hp = my_hp
            sim_opp_hp = opp_hp
            sim_mana = my_mana
            sim_pos = [my_pos[0] + move_vec[0], my_pos[1] + move_vec[1]]
            
            # Validate position
            if not is_valid(sim_pos):
                return -10000.0
            
            action_cost = 0
            dmg_dealt = 0
            healed = 0
            shielded = False
            
            if act_type == "fireball":
                action_cost = 30
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    blocked = SHIELD_BLOCK if opp_shield else 0
                    dmg_dealt = max(0, FIREBALL_DMG - blocked)
                    
            elif act_type == "melee_attack":
                action_cost = 0
                if manhattan_dist(sim_pos, target if target else opp_pos) == 1:
                    dmg_dealt = 10  # Melee ignores shield, deals 10 damage
                    
            elif act_type == "heal":
                action_cost = 25
                healed = HEAL_AMT
                
            elif act_type == "shield":
                action_cost = 20
                shielded = True
                
            elif act_type == "blink":
                action_cost = 10
                if target and is_valid(target) and chebyshev_dist(my_pos, target) <= 2:
                    sim_pos = target
                else:
                    return -10000.0
                
            elif act_type == "teleport":
                action_cost = 20
                if target and is_valid(target):
                    sim_pos = target
                else:
                    return -10000.0

            elif act_type == "summon":
                action_cost = 50

            # Check mana
            sim_mana -= action_cost
            if sim_mana < 0:
                return -10000.0
                
            sim_hp = min(100, sim_hp + healed)
            
            # Simulate enemy retaliation
            incoming = 0
            
            # Fireball Threat
            if opp_data["mana"] >= 30 and opp_data["cooldowns"]["fireball"] == 0:
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    dmg = FIREBALL_DMG
                    if shielded or shield_active:
                        dmg = max(0, dmg - SHIELD_BLOCK)
                    incoming = max(incoming, dmg)
            
            # Melee Threat
            if manhattan_dist(sim_pos, opp_pos) == 1 and opp_data["cooldowns"]["melee_attack"] == 0:
                incoming = max(incoming, MELEE_DMG)
                
            # Minion Threat
            for m in minions:
                if m["owner"] != self.name and manhattan_dist(sim_pos, m["position"]) == 1:
                    incoming += MELEE_DMG

            sim_hp -= incoming
            sim_opp_hp -= dmg_dealt
            
            # Win/Loss Check
            if sim_hp <= 0:
                return -10000.0
            if sim_opp_hp <= 0:
                return 10000.0
            
            score = 0.0
            
            # HP Score
            score += sim_hp * W_SURVIVAL
            score -= sim_opp_hp * W_AGGRO
            score += sim_mana * W_MANA
            
            # Artifact Control - prioritize health artifacts
            if artifacts:
                closest_dist = min([manhattan_dist(sim_pos, a["position"]) for a in artifacts])
                if closest_dist == 0: 
                    score += 15
                else: 
                    score -= closest_dist * 0.5
                
                # Extra bonus for health artifacts (deny opponent healing)
                for a in artifacts:
                    if a["type"] == "health":
                        health_dist = manhattan_dist(sim_pos, a["position"])
                        if health_dist == 0:
                            score += 40  # High priority for health artifacts
                        elif health_dist <= 3:
                            score += 20 - health_dist * 3
                
            # Positioning - Map Control
            dist_to_center = manhattan_dist(sim_pos, [4, 5])
            score -= dist_to_center * 1.0

            # Threat Projection - bonus for ending in attack range
            can_fireball_next = chebyshev_dist(sim_pos, opp_pos) <= 5
            can_melee_next = manhattan_dist(sim_pos, opp_pos) == 1
            if can_fireball_next or can_melee_next:
                score += 10.0
            
            # Summon bonus
            if act_type == "summon":
                score += 15
                
            return score

        # --- Evaluate Options ---
        valid_moves = get_valid_moves(my_pos)
        
        best_score = -99999
        best_action = {"move": [0, 0], "spell": None}
        
        for dx, dy in valid_moves:
            move_vec = [dx, dy]
            new_pos = [my_pos[0] + dx, my_pos[1] + dy]
            if not is_valid(new_pos):
                continue
            
            # Option A: Just Move (No Spell)
            s = score_action("wait", move_vec=move_vec)
            if s > best_score:
                best_score = s
                best_action = {"move": move_vec, "spell": None}
                
            # Option B: Move + Fireball (wizard or enemy minions)
            if cooldowns["fireball"] == 0 and my_mana >= 30:
                # Fireball the wizard
                if chebyshev_dist(new_pos, opp_pos) <= 5:
                    s = score_action("fireball", target=opp_pos, move_vec=move_vec)
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "fireball", "target": opp_pos}}
                
                # Also consider fireballing enemy minions
                for m in enemy_minions:
                    if chebyshev_dist(new_pos, m["position"]) <= 5:
                        s = score_action("fireball", target=m["position"], move_vec=move_vec)
                        # Big bonus for killing minions that are close to us
                        if manhattan_dist(my_pos, m["position"]) <= 2:
                            s += 100  # Enemy minion nearby is a threat!
                        if s > best_score:
                            best_score = s
                            best_action = {"move": move_vec, "spell": {"name": "fireball", "target": m["position"]}}

            # Option C: Move + Melee (wizard or minions)
            if cooldowns["melee_attack"] == 0:
                targets = []
                if manhattan_dist(new_pos, opp_pos) == 1:
                    targets.append(("wizard", opp_pos))
                for m in minions:
                    if m["owner"] != self.name and manhattan_dist(new_pos, m["position"]) == 1:
                        targets.append(("minion", m["position"]))
                
                for target_type, target_pos in targets:
                    s = score_action("melee_attack", target=target_pos, move_vec=move_vec)
                    # Bonus for killing enemy minions (they deal 10 damage per turn!)
                    if target_type == "minion":
                        s += 30
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "melee_attack", "target": target_pos}}

            # Option D: Move + Shield
            if cooldowns["shield"] == 0 and my_mana >= 20 and not shield_active:
                s = score_action("shield", move_vec=move_vec)
                if s > best_score:
                    best_score = s
                    best_action = {"move": move_vec, "spell": {"name": "shield"}}
            
            # Option E: Move + Heal
            if cooldowns["heal"] == 0 and my_mana >= 25 and my_hp < 100:
                s = score_action("heal", move_vec=move_vec)
                if s > best_score:
                    best_score = s
                    best_action = {"move": move_vec, "spell": {"name": "heal"}}
                    
            # Option F: Move + Summon
            if cooldowns["summon"] == 0 and my_mana >= 50:
                s = score_action("summon", move_vec=move_vec)
                if s > best_score:
                    best_score = s
                    best_action = {"move": move_vec, "spell": {"name": "summon"}}

        # Special Case: Blink
        if cooldowns["blink"] == 0 and my_mana >= 10:
            for bx in [-2, -1, 0, 1, 2]:
                for by in [-2, -1, 0, 1, 2]:
                    if abs(bx) + abs(by) == 0:
                        continue
                    if manhattan_dist([0, 0], [bx, by]) > 2:
                        continue
                    
                    tx, ty = my_pos[0] + bx, my_pos[1] + by
                    if is_valid([tx, ty]):
                        s = score_action("blink", target=[tx, ty])
                        if s > best_score:
                            best_score = s
                            best_action = {"move": [0, 0], "spell": {"name": "blink", "target": [tx, ty]}}

        # Special Case: Teleport to artifacts
        if cooldowns["teleport"] == 0 and my_mana >= 20:
            for a in artifacts:
                s = score_action("teleport", target=a["position"])
                # High priority for health artifacts
                if a["type"] == "health":
                    # Always valuable if we're hurt
                    if my_hp < 60:
                        s += 80
                    # Also valuable to deny opponent
                    if opp_hp < 50:
                        s += 100  # Strong priority to intercept
                if a["type"] == "cooldown":
                    s += 30  # Cooldown artifacts are also very valuable
                if s > best_score:
                    best_score = s
                    best_action = {"move": [0, 0], "spell": {"name": "teleport", "target": a["position"]}}

        return best_action