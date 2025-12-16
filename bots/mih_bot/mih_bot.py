"""
Mih Bot V4 - Scoring System Edition

STRATEGY: Use IvraBot's SCORING SYSTEM approach
- Evaluate all possible move+spell combinations
- Score based on: survival, damage dealt, positioning, artifacts
- Pick highest scoring action

KEY DIFFERENCES FROM PREVIOUS ATTEMPTS:
- NO hardcoded modes that force bad decisions
- Every decisi            # Teleport to artifacts - PRIORITIZE denying health to wounded opponents
            if cooldowns["teleport"] == 0 and mana >= 20:
                for a in artifacts:
                    s = score_action([0, 0], "teleport", a["position"])
                    # INTERCEPTOR BONUS: if opponent is wounded and this is a health artifact
                    # they are very likely to teleport here - get there first!
                    if a["type"] == "health" and opp_hp < 50:
                        s += 100  # Strong priority to intercept
                    candidates.append((s, [0, 0], {"name": "teleport", "target": a["position"]})) evaluated holistically
- Survival is weighted VERY high to avoid deaths
- Aggression scales with opponent HP damage
"""

from bots.bot_interface import BotInterface


class MihBot(BotInterface):
    def __init__(self):
        self._name = "Mih Bot"
        self._sprite_path = "assets/wizards/mih_bot.svg"
        self._minion_sprite_path = "assets/minions/mih_minion.svg"

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

        # Constants
        FIREBALL_DMG = 20
        MELEE_DMG = 5
        HEAL_AMT = 20
        SHIELD_BLOCK = 20

        # Helpers
        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        def is_valid(pos):
            return 0 <= pos[0] < board_size and 0 <= pos[1] < board_size

        # =====================================================
        # EARLY GAME POSITIONING CHECK
        # If we're far from opponent (started second), optimize opening
        # =====================================================
        dist_to_opp = chebyshev(self_pos, opp_pos)
        is_opening = hp == 100 and opp_hp == 100
        my_minions_list = [m for m in minions if m["owner"] == self_data["name"]]
        has_minion_early = len(my_minions_list) > 0
        
        if is_opening and dist_to_opp > 6:
            # PRIORITY 1: Summon minion if we don't have one (helps close gap)
            if not has_minion_early and cooldowns.get("summon", 99) == 0 and mana >= 50:
                # Move toward opponent while summoning
                move_dir = [0, 0]
                if opp_pos[0] > self_pos[0]: move_dir[0] = 1
                elif opp_pos[0] < self_pos[0]: move_dir[0] = -1
                if opp_pos[1] > self_pos[1]: move_dir[1] = 1
                elif opp_pos[1] < self_pos[1]: move_dir[1] = -1
                return {"move": move_dir, "spell": {"name": "summon"}}
            
            # PRIORITY 2: Use blink to close gap quickly
            if cooldowns.get("blink", 99) == 0 and mana >= 10:
                # Blink toward opponent
                best_blink = None
                best_dist = dist_to_opp
                for bx in range(-2, 3):
                    for by in range(-2, 3):
                        if bx == 0 and by == 0:
                            continue
                        target = [self_pos[0] + bx, self_pos[1] + by]
                        if is_valid(target) and chebyshev(self_pos, target) <= 2:
                            new_dist = chebyshev(target, opp_pos)
                            if new_dist < best_dist:
                                best_dist = new_dist
                                best_blink = target
                if best_blink:
                    move_dir = [0, 0]
                    if opp_pos[0] > self_pos[0]: move_dir[0] = 1
                    elif opp_pos[0] < self_pos[0]: move_dir[0] = -1
                    if opp_pos[1] > self_pos[1]: move_dir[1] = 1
                    elif opp_pos[1] < self_pos[1]: move_dir[1] = -1
                    return {"move": move_dir, "spell": {"name": "blink", "target": best_blink}}

        # =====================================================
        # PRIORITY CHECK: Can we kill opponent THIS TURN?
        # This prevents them from escaping with teleport/blink
        # =====================================================
        effective_opp_hp = opp_hp
        if opp_shield:
            effective_opp_hp = opp_hp + SHIELD_BLOCK  # Account for shield
        
        # Check for fireball kill
        can_fireball = cooldowns["fireball"] == 0 and mana >= 30
        in_fireball_range = chebyshev(self_pos, opp_pos) <= 5
        
        if can_fireball and in_fireball_range and effective_opp_hp <= FIREBALL_DMG:
            # EXECUTE! Fireball will kill them
            return {"move": [0, 0], "spell": {"name": "fireball", "target": opp_pos}}
        
        # Check for melee kill - move adjacent then melee
        can_melee = cooldowns["melee_attack"] == 0
        if can_melee and effective_opp_hp <= MELEE_DMG:
            # Find a move that puts us adjacent to opponent
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    new_pos = [self_pos[0] + dx, self_pos[1] + dy]
                    if is_valid(new_pos) and manhattan(new_pos, opp_pos) == 1:
                        return {"move": [dx, dy], "spell": {"name": "melee_attack", "target": opp_pos}}
        
        # Check for fireball + splash combo (opponent near minion or wall)
        # Splash damage is 4 for adjacent cells
        if can_fireball and in_fireball_range and effective_opp_hp <= FIREBALL_DMG + 4:
            # Direct hit is most reliable for kill
            if effective_opp_hp <= FIREBALL_DMG:
                return {"move": [0, 0], "spell": {"name": "fireball", "target": opp_pos}}
        # Identify minions
        my_minions = [m for m in minions if m["owner"] == self_data["name"]]
        enemy_minions = [m for m in minions if m["owner"] != self_data["name"]]
        has_minion = len(my_minions) > 0

        # Detect early game by HP (no damage taken yet)
        is_early_game = hp == 100 and opp_hp == 100
        
        # Calculate our distance from center to detect start position disadvantage
        center = [4, 4]
        our_center_dist = abs(self_pos[0] - center[0]) + abs(self_pos[1] - center[1])
        opp_center_dist = abs(opp_pos[0] - center[0]) + abs(opp_pos[1] - center[1])
        we_are_far_from_center = our_center_dist > opp_center_dist + 2

        # Dynamic weights based on game state (IvraBot-inspired)
        W_SURVIVAL = 3.0   # Lower base survival - be aggressive
        W_AGGRO = 20.0     # High base aggro weight
        
        # EARLY GAME: If we started far, be slightly more aggressive to close gap
        if is_early_game and we_are_far_from_center:
            W_AGGRO = 30.0  # Push harder early when at disadvantage
        
        # Track turns using mana regeneration pattern (10 per turn from 100 start)
        # Estimate turn: late game if both have used significant resources
        hp_lost = (100 - hp) + (100 - opp_hp)
        is_late_game = hp_lost > 60 or mana == 100  # Deep in fight
        
        # LATE GAME AGGRESSION: Force decisive action
        if is_late_game:
            W_AGGRO = 50.0  # Much more aggressive late
            W_SURVIVAL = 2.0  # Accept more risk
        
        # Increase survival when critically low HP
        if hp < 30:
            W_SURVIVAL = 12.0
        if hp < 20:
            W_SURVIVAL = 25.0
            
        # BLOODLUST MODE - trigger finisher earlier to prevent escape
        if opp_hp < 80 and hp > 30:
            W_AGGRO = 60.0  # Start pressuring earlier
        if opp_hp < 60 and hp > 25:
            W_AGGRO = 100.0
        if opp_hp < 45 and hp > 20:
            W_AGGRO = 180.0  # FINISHER mode - kill before they escape!
        
        # Check if opponent likely to teleport to health artifact
        health_artifacts = [a for a in artifacts if a["type"] == "health"]
        opp_likely_to_escape = opp_hp <= 40 and cooldowns.get("teleport", 99) == 0 and health_artifacts
        
        def calculate_incoming_threat(pos, has_shield):
            """Calculate max damage we might take at this position."""
            threat = 0
            
            # Fireball threat
            if opp_mana >= 30 and opp_cooldowns.get("fireball", 99) == 0:
                if chebyshev(pos, opp_pos) <= 5:
                    fb_dmg = FIREBALL_DMG
                    if has_shield:
                        fb_dmg = max(0, fb_dmg - SHIELD_BLOCK)
                    threat = max(threat, fb_dmg)
            
            # Melee threat
            if manhattan(pos, opp_pos) == 1 and opp_cooldowns.get("melee_attack", 99) == 0:
                threat = max(threat, MELEE_DMG)
            
            # Minion threat
            for m in enemy_minions:
                if manhattan(pos, m["position"]) == 1:
                    threat += 10
            
            return threat

        def score_action(move_vec, spell_name, spell_target=None):
            """Score a move+spell combination."""
            new_pos = [self_pos[0] + move_vec[0], self_pos[1] + move_vec[1]]
            if not is_valid(new_pos):
                return -99999
            
            score = 0
            sim_hp = hp
            sim_mana = mana
            sim_opp_hp = opp_hp
            sim_shield = shield_active
            dmg_dealt = 0
            
            # Apply spell effects
            if spell_name == "fireball" and cooldowns["fireball"] == 0 and mana >= 30:
                sim_mana -= 30
                if chebyshev(new_pos, opp_pos) <= 5:
                    blocked = SHIELD_BLOCK if opp_shield else 0
                    dmg_dealt = max(0, FIREBALL_DMG - blocked)
                    sim_opp_hp -= dmg_dealt
                    
            elif spell_name == "melee_attack" and cooldowns["melee_attack"] == 0:
                if spell_target and manhattan(new_pos, spell_target) == 1:
                    dmg_dealt = MELEE_DMG
                    sim_opp_hp -= dmg_dealt
                    
            elif spell_name == "heal" and cooldowns["heal"] == 0 and mana >= 25:
                sim_mana -= 25
                sim_hp = min(100, sim_hp + HEAL_AMT)
                
            elif spell_name == "shield" and cooldowns["shield"] == 0 and mana >= 20:
                sim_mana -= 20
                sim_shield = True
                
            elif spell_name == "summon" and cooldowns["summon"] == 0 and mana >= 50:
                sim_mana -= 50
                score += 30  # Minion value
                
            elif spell_name == "blink" and cooldowns["blink"] == 0 and mana >= 10:
                if spell_target and is_valid(spell_target) and chebyshev(new_pos, spell_target) <= 2:
                    sim_mana -= 10
                    new_pos = spell_target
                else:
                    return -99999
                    
            elif spell_name == "teleport" and cooldowns["teleport"] == 0 and mana >= 20:
                if spell_target and is_valid(spell_target):
                    sim_mana -= 20
                    new_pos = spell_target
                else:
                    return -99999
            
            # Simulate incoming damage
            incoming = calculate_incoming_threat(new_pos, sim_shield)
            sim_hp -= incoming
            
            # CRITICAL: Check for death
            if sim_hp <= 0:
                return -10000
            
            # Check for win
            if sim_opp_hp <= 0:
                return 10000
            
            # Score components
            score += sim_hp * W_SURVIVAL  # Survival value
            score -= sim_opp_hp * W_AGGRO  # Damage dealt value
            score += sim_mana * 0.5  # Mana conservation
            
            # Distance penalty/bonus - favor fireball range
            dist = chebyshev(new_pos, opp_pos)
            if 3 <= dist <= 5:
                score += 25  # Optimal range for fireball - SAFE damage
            elif dist == 2:
                score += 15  # Close but not too dangerous
            elif dist <= 1:
                score += 5   # Melee only good if we're winning
            elif dist > 6:
                score -= 15  # Don't let them escape entirely
            
            # Artifact bonus - race to artifacts
            for a in artifacts:
                art_dist = manhattan(new_pos, a["position"])
                opp_art_dist = manhattan(opp_pos, a["position"])
                if art_dist == 0:
                    if a["type"] == "health":
                        # Huge bonus if we're hurt OR it denies opponent
                        hp_urgency = (100 - hp) / 2  # Up to +50 if low HP
                        denial_bonus = 40 if opp_hp < 50 else 20  # Deny if opponent wounded
                        score += 40 + hp_urgency + denial_bonus
                    elif a["type"] == "mana":
                        score += 30
                    else:
                        score += 20
                elif art_dist <= 3:
                    # Race to artifacts - bonus if we're closer than opponent
                    if a["type"] == "health" and opp_hp < 50:
                        # Strongly prefer getting to health before wounded opponent
                        score += 20 if art_dist < opp_art_dist else 5
                    else:
                        score += 8 - art_dist * 2
            
            # Center control - but reduced when already far (avoid double penalty)
            center_dist = manhattan(new_pos, [4, 4])
            current_center_dist = manhattan(self_pos, [4, 4])
            # Reward moving toward center if far, but don't over-penalize staying
            if center_dist < current_center_dist:
                score += 3  # Small bonus for moving toward center
            elif center_dist > 6:
                score -= 5  # Only penalize if very far from action
            
            return score

        # Generate all candidate actions
        candidates = []
        
        # All possible moves
        moves = [[0, 0]]
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                new_pos = [self_pos[0] + dx, self_pos[1] + dy]
                if is_valid(new_pos):
                    moves.append([dx, dy])
        
        for move in moves:
            new_pos = [self_pos[0] + move[0], self_pos[1] + move[1]]
            
            # No spell
            s = score_action(move, None)
            candidates.append((s, move, None))
            
            # Fireball
            if cooldowns["fireball"] == 0 and mana >= 30:
                if chebyshev(new_pos, opp_pos) <= 5:
                    s = score_action(move, "fireball", opp_pos)
                    candidates.append((s, move, {"name": "fireball", "target": opp_pos}))
            
            # Melee
            if cooldowns["melee_attack"] == 0:
                if manhattan(new_pos, opp_pos) == 1:
                    s = score_action(move, "melee_attack", opp_pos)
                    candidates.append((s, move, {"name": "melee_attack", "target": opp_pos}))
                # Also consider melee on minions
                for m in enemy_minions:
                    if manhattan(new_pos, m["position"]) == 1:
                        s = score_action(move, "melee_attack", m["position"])
                        candidates.append((s, move, {"name": "melee_attack", "target": m["position"]}))
            
            # Heal
            if cooldowns["heal"] == 0 and mana >= 25:
                s = score_action(move, "heal")
                candidates.append((s, move, {"name": "heal"}))
            
            # Shield
            if cooldowns["shield"] == 0 and mana >= 20 and not shield_active:
                s = score_action(move, "shield")
                candidates.append((s, move, {"name": "shield"}))
            
            # Summon
            if cooldowns["summon"] == 0 and mana >= 50 and not has_minion:
                s = score_action(move, "summon")
                candidates.append((s, move, {"name": "summon"}))
            
            # Blink to adjacent positions
            if cooldowns["blink"] == 0 and mana >= 10:
                for bx in range(-2, 3):
                    for by in range(-2, 3):
                        if bx == 0 and by == 0:
                            continue
                        blink_target = [self_pos[0] + bx, self_pos[1] + by]
                        if is_valid(blink_target) and chebyshev(self_pos, blink_target) <= 2:
                            s = score_action([0, 0], "blink", blink_target)
                            candidates.append((s, [0, 0], {"name": "blink", "target": blink_target}))
            
            # Teleport to artifacts
            if cooldowns["teleport"] == 0 and mana >= 20:
                for a in artifacts:
                    s = score_action([0, 0], "teleport", a["position"])
                    candidates.append((s, [0, 0], {"name": "teleport", "target": a["position"]}))
        
        # Pick best action
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0]
            return {"move": best[1], "spell": best[2]}
        
        # Fallback
        return {"move": [0, 0], "spell": None}
