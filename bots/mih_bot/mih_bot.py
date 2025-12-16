"""
Mih Bot V4 - Scoring System Edition

STRATEGY: Evaluate all possible move+spell combinations with weighted scoring.
- Score based on: survival, damage dealt, positioning, artifacts
- Dynamic weight adjustment based on game state
- BLOODLUST MODE when opponent is wounded
- Opening optimization for second position

KEY FEATURES:
- Dynamic aggression weights
- Finisher mode for low-HP opponents  
- Position-aware opening
- Artifact racing
"""

from bots.bot_interface import BotInterface


class MihBot(BotInterface):
    def __init__(self):
        self._name = "Mih Bot"
        self._sprite_path = "assets/wizards/mihb-wizard.png"
        self._minion_sprite_path = "assets/minions/mihb-minion.png"

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

        FIREBALL_DMG = 20
        MELEE_DMG = 5
        HEAL_AMT = 20
        SHIELD_BLOCK = 20

        def chebyshev(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        def is_valid(pos):
            return 0 <= pos[0] < board_size and 0 <= pos[1] < board_size

        dist_to_opp = chebyshev(self_pos, opp_pos)
        is_opening = hp == 100 and opp_hp == 100
        my_minions_list = [m for m in minions if m["owner"] == self_data["name"]]
        has_minion_early = len(my_minions_list) > 0
        
        if is_opening and dist_to_opp > 6:
            if not has_minion_early and cooldowns.get("summon", 99) == 0 and mana >= 50:
                move_dir = [0, 0]
                if opp_pos[0] > self_pos[0]: move_dir[0] = 1
                elif opp_pos[0] < self_pos[0]: move_dir[0] = -1
                if opp_pos[1] > self_pos[1]: move_dir[1] = 1
                elif opp_pos[1] < self_pos[1]: move_dir[1] = -1
                return {"move": move_dir, "spell": {"name": "summon"}}
            
            if cooldowns.get("blink", 99) == 0 and mana >= 10:
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

        effective_opp_hp = opp_hp
        if opp_shield:
            effective_opp_hp = opp_hp + SHIELD_BLOCK
        
        can_fireball = cooldowns["fireball"] == 0 and mana >= 30
        in_fireball_range = chebyshev(self_pos, opp_pos) <= 5
        
        if can_fireball and in_fireball_range and effective_opp_hp <= FIREBALL_DMG:
            return {"move": [0, 0], "spell": {"name": "fireball", "target": opp_pos}}
        
        can_melee = cooldowns["melee_attack"] == 0
        if can_melee and effective_opp_hp <= MELEE_DMG:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    new_pos = [self_pos[0] + dx, self_pos[1] + dy]
                    if is_valid(new_pos) and manhattan(new_pos, opp_pos) == 1:
                        return {"move": [dx, dy], "spell": {"name": "melee_attack", "target": opp_pos}}

        my_minions = [m for m in minions if m["owner"] == self_data["name"]]
        enemy_minions = [m for m in minions if m["owner"] != self_data["name"]]
        has_minion = len(my_minions) > 0

        is_early_game = hp == 100 and opp_hp == 100
        
        center = [4, 4]
        our_center_dist = abs(self_pos[0] - center[0]) + abs(self_pos[1] - center[1])
        opp_center_dist = abs(opp_pos[0] - center[0]) + abs(opp_pos[1] - center[1])
        we_are_far_from_center = our_center_dist > opp_center_dist + 2

        W_SURVIVAL = 3.0
        W_AGGRO = 20.0
        
        if is_early_game and we_are_far_from_center:
            W_AGGRO = 30.0
        
        hp_lost = (100 - hp) + (100 - opp_hp)
        is_late_game = hp_lost > 60 or mana == 100
        
        if is_late_game:
            W_AGGRO = 50.0
            W_SURVIVAL = 2.0
        
        if hp < 30:
            W_SURVIVAL = 12.0
        if hp < 20:
            W_SURVIVAL = 25.0
            
        if opp_hp < 80 and hp > 30:
            W_AGGRO = 60.0
        if opp_hp < 60 and hp > 25:
            W_AGGRO = 100.0
        if opp_hp < 45 and hp > 20:
            W_AGGRO = 180.0
        
        def calculate_incoming_threat(pos, has_shield):
            threat = 0
            if opp_mana >= 30 and opp_cooldowns.get("fireball", 99) == 0:
                if chebyshev(pos, opp_pos) <= 5:
                    fb_dmg = FIREBALL_DMG
                    if has_shield:
                        fb_dmg = max(0, fb_dmg - SHIELD_BLOCK)
                    threat = max(threat, fb_dmg)
            if manhattan(pos, opp_pos) == 1 and opp_cooldowns.get("melee_attack", 99) == 0:
                threat = max(threat, MELEE_DMG)
            for m in enemy_minions:
                if manhattan(pos, m["position"]) == 1:
                    threat += 10
            return threat

        def score_action(move_vec, spell_name, spell_target=None):
            new_pos = [self_pos[0] + move_vec[0], self_pos[1] + move_vec[1]]
            if not is_valid(new_pos):
                return -99999
            
            score = 0
            sim_hp = hp
            sim_mana = mana
            sim_opp_hp = opp_hp
            sim_shield = shield_active
            
            if spell_name == "fireball" and cooldowns["fireball"] == 0 and mana >= 30:
                sim_mana -= 30
                if chebyshev(new_pos, opp_pos) <= 5:
                    blocked = SHIELD_BLOCK if opp_shield else 0
                    dmg_dealt = max(0, FIREBALL_DMG - blocked)
                    sim_opp_hp -= dmg_dealt
                    
            elif spell_name == "melee_attack" and cooldowns["melee_attack"] == 0:
                if spell_target and manhattan(new_pos, spell_target) == 1:
                    sim_opp_hp -= MELEE_DMG
                    
            elif spell_name == "heal" and cooldowns["heal"] == 0 and mana >= 25:
                sim_mana -= 25
                sim_hp = min(100, sim_hp + HEAL_AMT)
                
            elif spell_name == "shield" and cooldowns["shield"] == 0 and mana >= 20:
                sim_mana -= 20
                sim_shield = True
                
            elif spell_name == "summon" and cooldowns["summon"] == 0 and mana >= 50:
                sim_mana -= 50
                score += 30
                
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
            
            incoming = calculate_incoming_threat(new_pos, sim_shield)
            sim_hp -= incoming
            
            if sim_hp <= 0:
                return -10000
            
            if sim_opp_hp <= 0:
                return 10000
            
            score += sim_hp * W_SURVIVAL
            score -= sim_opp_hp * W_AGGRO
            score += sim_mana * 0.5
            
            dist = chebyshev(new_pos, opp_pos)
            if 3 <= dist <= 5:
                score += 25
            elif dist == 2:
                score += 15
            elif dist <= 1:
                score += 5
            elif dist > 6:
                score -= 15
            
            for a in artifacts:
                art_dist = manhattan(new_pos, a["position"])
                opp_art_dist = manhattan(opp_pos, a["position"])
                if art_dist == 0:
                    if a["type"] == "health":
                        hp_urgency = (100 - hp) / 2
                        denial_bonus = 40 if opp_hp < 50 else 20
                        score += 40 + hp_urgency + denial_bonus
                    elif a["type"] == "mana":
                        score += 30
                    else:
                        score += 20
                elif art_dist <= 3:
                    if a["type"] == "health" and opp_hp < 50:
                        score += 20 if art_dist < opp_art_dist else 5
                    else:
                        score += 8 - art_dist * 2
            
            center_dist = manhattan(new_pos, [4, 4])
            current_center_dist = manhattan(self_pos, [4, 4])
            if center_dist < current_center_dist:
                score += 3
            elif center_dist > 6:
                score -= 5
            
            return score

        candidates = []
        
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
            
            s = score_action(move, None)
            candidates.append((s, move, None))
            
            if cooldowns["fireball"] == 0 and mana >= 30:
                if chebyshev(new_pos, opp_pos) <= 5:
                    s = score_action(move, "fireball", opp_pos)
                    candidates.append((s, move, {"name": "fireball", "target": opp_pos}))
            
            if cooldowns["melee_attack"] == 0:
                if manhattan(new_pos, opp_pos) == 1:
                    s = score_action(move, "melee_attack", opp_pos)
                    candidates.append((s, move, {"name": "melee_attack", "target": opp_pos}))
                for m in enemy_minions:
                    if manhattan(new_pos, m["position"]) == 1:
                        s = score_action(move, "melee_attack", m["position"])
                        candidates.append((s, move, {"name": "melee_attack", "target": m["position"]}))
            
            if cooldowns["heal"] == 0 and mana >= 25:
                s = score_action(move, "heal")
                candidates.append((s, move, {"name": "heal"}))
            
            if cooldowns["shield"] == 0 and mana >= 20 and not shield_active:
                s = score_action(move, "shield")
                candidates.append((s, move, {"name": "shield"}))
            
            if cooldowns["summon"] == 0 and mana >= 50 and not has_minion:
                s = score_action(move, "summon")
                candidates.append((s, move, {"name": "summon"}))
            
            if cooldowns["blink"] == 0 and mana >= 10:
                for bx in range(-2, 3):
                    for by in range(-2, 3):
                        if bx == 0 and by == 0:
                            continue
                        blink_target = [self_pos[0] + bx, self_pos[1] + by]
                        if is_valid(blink_target) and chebyshev(self_pos, blink_target) <= 2:
                            s = score_action([0, 0], "blink", blink_target)
                            candidates.append((s, [0, 0], {"name": "blink", "target": blink_target}))
            
            if cooldowns["teleport"] == 0 and mana >= 20:
                for a in artifacts:
                    s = score_action([0, 0], "teleport", a["position"])
                    candidates.append((s, [0, 0], {"name": "teleport", "target": a["position"]}))
        
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0]
            return {"move": best[1], "spell": best[2]}
        
        return {"move": [0, 0], "spell": None}
