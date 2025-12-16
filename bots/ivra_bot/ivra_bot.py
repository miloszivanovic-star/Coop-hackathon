import random
from bots.bot_interface import BotInterface

class IvraBot(BotInterface):
    def __init__(self):
        self._name = "IvraBot"
        # Re-using sample assets for now, can be customized later if needed
        self._sprite_path = "assets/wizards/sample_bot1.png" 
        self._minion_sprite_path = "assets/minions/minion_1.png"

        # Adaptiveness tuning
        # Base EMA update rate; actual per-turn rate is adjusted dynamically based on signal strength.
        # Lowered slightly to avoid overreacting vs high-volatility opponents.
        self._base_adapt_rate = 0.11

        # NEW: Opponent modeling - tracks opponent behavior across turns
        self.opponent_profile = {
            "aggression_score": 0.5,  # 0=defensive, 1=aggressive
            "spell_usage": {"fireball": 0, "heal": 0, "shield": 0, "teleport": 0, "blink": 0, "summon": 0},
            "avg_distance": 5.0,  # Average distance they maintain
            "artifact_priority": 0.5,  # How much they prioritize artifacts
            "mana_conservation": 0.5,  # How conservatively they use mana
            "last_hp": 100,
            "last_mana": 100,
            "last_position": None,
            "turns_observed": 0,
            "damage_dealt_to_us": 0,
            "times_healed": 0,
            "times_used_shield": 0,
            "total_distance_samples": 0,

            # EMA signals (more adaptive, less noisy)
            "ema_aggression": 0.5,
            "ema_fireball_rate": 0.0,
            "ema_heal_rate": 0.0,
            "ema_shield_rate": 0.0,
            "ema_mobility_rate": 0.0,
            "ema_damage_to_us": 0.0,
            "ema_dist_to_us": 5.0,
            "_ema_cast_rate": 0.0,
            "last_dist_to_us": None,
            "last_turn_mana": None,
            "last_turn_hp": None,
        }

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
        
        my_pos = self_data["position"]
        opp_pos = opp_data["position"]
        my_hp = self_data["hp"]
        opp_hp = opp_data["hp"]
        my_mana = self_data["mana"]
        opp_mana = opp_data["mana"]
        cooldowns = self_data["cooldowns"]
        turn_count = state.get("turn", 0)

        # Save our current position for opponent profiling (distance-to-us signal)
        self._my_pos_for_profile = my_pos

        # Constants
        FIREBALL_DMG = 20
        MELEE_DMG = 10
        HEAL_AMT = 20
        SHIELD_BLOCK = 20
        BOARD_SIZE = 10

        # NEW: Update opponent profile
        self._update_opponent_profile(opp_data, opp_pos, my_hp, turn_count)
        
        # NEW: Get adaptive strategy based on opponent profile
        strategy = self._get_adaptive_strategy()

        # --- Helpers ---
        def manhattan_dist(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
            
        def chebyshev_dist(a, b):
             return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

        def get_valid_moves(pos):
            moves = [[0,0]] # Stay
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    nx, ny = pos[0]+dx, pos[1]+dy
                    if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                        moves.append([dx, dy])
            return moves
        
        # NEW: Check if position will cause collision
        def will_collide(pos):
            if pos == opp_pos:
                return True
            for m in minions:
                if m["position"] == pos:
                    return True
            return False
        
        # NEW: Get artifact value based on current state AND opponent style
        def get_artifact_value(artifact):
            artifact_type = artifact["type"]
            base_value = 30

            # If we are in closeout mode, de-prioritize most artifacts except immediate H/CC
            closeout = strategy.get("closeout", 0.0)
            
            if artifact_type == "health":
                # More valuable when low HP
                if my_hp < 50:
                    base_value = 120
                elif my_hp < 80:
                    base_value = 80
                else:
                    base_value = 50
                # If opponent is aggressive, health is even more valuable
                base_value *= (1 + strategy["defensiveness"] * 0.3)

                # In closeout, don't run across the map for health unless we are actually low
                if closeout > 0.6 and my_hp >= 70:
                    base_value *= 0.55
                    
            elif artifact_type == "cooldown":
                # Very valuable for spell spam
                base_value = 100
                # More valuable against spell-heavy opponents
                if self.opponent_profile["spell_usage"].get("fireball", 0) > 3:
                    base_value *= 1.2

                # Closeout likes cooldown (more pressure)
                base_value *= (1 + 0.25 * closeout)
                    
            elif artifact_type == "mana":
                # More valuable when low mana
                if my_mana < 40:
                    base_value = 90
                elif my_mana < 70:
                    base_value = 60
                else:
                    base_value = 35
                # More valuable if we're in spell-trading mode
                if strategy["aggression"] > 0.7:
                    base_value *= 1.15

                # Closeout: don't over-chase mana if we're already healthy on mana
                if closeout > 0.6 and my_mana >= 60:
                    base_value *= 0.60
                    
            return base_value

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
        
        # --- Enhanced Dynamic Weights with Adaptive Strategy ---
        # Base weights are now adjusted by opponent profile
        base_aggro = 18.0 * strategy["aggression"]
        base_survival = 5.0 * (1 + strategy["defensiveness"])
        
        W_SURVIVAL = base_survival
        W_AGGRO = base_aggro
        W_MANA = 0.0 
        
        # Defensive Shift - only when critically low
        if my_hp < 35: W_SURVIVAL = base_survival * 0.2
        if my_hp < 18: W_SURVIVAL = base_survival * 2.0
            
        # NEW: Anti-Draw Mode - Be more aggressive earlier in late game
        if turn_count > 65:
            W_AGGRO = base_aggro * 6.5  # Scale with adaptive aggression

        # If opponent is highly mobile/heal-y, push harder to end (prevents endless artifact loops)
        if turn_count > 55 and (strategy.get("closeout", 0.0) > 0.55):
            W_AGGRO *= 1.35
        
        # Offensive Shift (Bloodlust) - more aggressive when opponent is wounded
        if opp_hp < 65 and my_hp > 30:
            W_AGGRO = base_aggro * 4.5
        
        # FINISHER MODE - kill when we have the advantage
        FINISHER_MODE = opp_hp < 35 and my_hp > 20
        if FINISHER_MODE:
            W_AGGRO = base_aggro * 10.0
        
        # NEW: PUNISH HEAL MODE - Extra aggressive if they heal often
        heal_punish_multiplier = 1.0 + (self.opponent_profile["times_healed"] * 0.1)
        PUNISH_HEAL_MODE = opp_hp < 45 and opp_data["mana"] >= 25 and opp_data["cooldowns"]["heal"] == 0
        if PUNISH_HEAL_MODE:
            W_AGGRO = base_aggro * 12.0 * heal_punish_multiplier

        # --- Helper to simulate state ---
        def score_action(act_type, target=None, move_vec=[0,0]):
            sim_hp = my_hp
            sim_opp_hp = opp_hp
            sim_mana = my_mana
            sim_pos = [my_pos[0] + move_vec[0], my_pos[1] + move_vec[1]]
            
            # NEW: Heavy penalty for collision positions
            if will_collide(sim_pos):
                return -5000.0
            
            # ...existing action scoring code...
            
            action_cost = 0
            dmg_dealt = 0
            healed = 0
            shielded = False
            
            if act_type == "fireball":
                action_cost = 30
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    blocked = 0
                    if opp_data.get("shield_active"): blocked = SHIELD_BLOCK
                    dmg_dealt = max(0, FIREBALL_DMG - blocked)
                    
            elif act_type == "melee_attack":
                action_cost = 0
                if manhattan_dist(sim_pos, target if target else opp_pos) == 1:
                    dmg_dealt = MELEE_DMG
                    
            elif act_type == "heal":
                action_cost = 25
                healed = HEAL_AMT
                
            elif act_type == "shield":
                action_cost = 20
                shielded = True
                
            elif act_type == "blink":
                action_cost = 10
                sim_pos = target
                
            elif act_type == "teleport":
                action_cost = 20
                sim_pos = target

            elif act_type == "summon":
                action_cost = 50

            sim_mana -= action_cost 
            sim_hp = min(100, sim_hp + healed)
            
            # Simulate enemy retaliation
            incoming = 0
            if opp_data["mana"] >= 30 and opp_data["cooldowns"]["fireball"] == 0:
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    dmg = FIREBALL_DMG
                    if shielded or self_data.get("shield_active"):
                         dmg = max(0, dmg - SHIELD_BLOCK)
                    incoming += dmg
            
            if manhattan_dist(sim_pos, opp_pos) == 1 and opp_data["cooldowns"]["melee_attack"] == 0:
                incoming += MELEE_DMG
                
            for m in minions:
                if m["owner"] != self.name and manhattan_dist(sim_pos, m["position"]) == 1:
                    incoming += MELEE_DMG

            sim_hp -= incoming
            sim_opp_hp -= dmg_dealt
            
            # Calculate Score
            if sim_hp <= 0: return -10000.0
            if sim_opp_hp <= 0: return 10000.0
            
            score = 0.0
            score += sim_hp * W_SURVIVAL
            score -= sim_opp_hp * W_AGGRO
            score += sim_mana * W_MANA

            # Positioning - Map Control
            dist_to_center = manhattan_dist(sim_pos, [4, 5])
            score -= dist_to_center * 1.0

            # Opportunity - Threat Projection
            can_fireball_next = chebyshev_dist(sim_pos, opp_pos) <= 5
            can_melee_next = manhattan_dist(sim_pos, opp_pos) == 1
            if can_fireball_next or can_melee_next:
                score += 10.0
            
            # NEW: Minion value bonus (they provide pressure)
            if act_type == "summon":
                score += 30  # Increased from 25

            # --- Strategy-driven positioning ---
            # Use a smooth penalty for being too far from the desired spacing.
            # In closeout, bias more strongly toward engaging / maintaining pressure.
            desired = float(strategy.get("range_preference", 3.0))
            closeout = float(strategy.get("closeout", 0.0))
            dist_to_opp = manhattan_dist(sim_pos, opp_pos)

            spacing_penalty = abs(dist_to_opp - desired)
            score -= spacing_penalty * (1.4 + 2.2 * closeout)

            # Extra penalty for running very far away in closeout mode
            if closeout > 0.6 and dist_to_opp > desired + 2:
                score -= 8.0 * (dist_to_opp - (desired + 2))

            # --- Strategy-driven artifact control (unifies logic with get_artifact_value) ---
            if artifacts:
                best_art = None
                best_art_score = -1e9

                for a in artifacts:
                    aval = float(get_artifact_value(a))
                    d = manhattan_dist(sim_pos, a["position"])
                    # Convert value + distance into a single term.
                    # Higher artifact_priority -> more willing to route toward artifacts.
                    # closeout inside get_artifact_value already dampens chase.
                    art_term = (aval * float(strategy.get("artifact_priority", 0.7))) - (d * 6.0)
                    if a["type"] == "health" and my_hp < 70:
                        art_term += 14.0
                    if art_term > best_art_score:
                        best_art_score = art_term
                        best_art = a

                if best_art is not None:
                    # Add the best artifact term as a bounded bonus.
                    score += max(-30.0, min(60.0, best_art_score))

                    # If we are standing on an artifact, give an extra immediate bonus.
                    if manhattan_dist(sim_pos, best_art["position"]) == 0:
                        score += max(25.0, min(90.0, float(get_artifact_value(best_art))))

            return score

        # --- Evaluate Options ---
        valid_moves = get_valid_moves(my_pos)
        
        best_score = -99999
        best_action = {"move": [0,0], "spell": None}
        
        # IMPROVED: Much more aggressive teleport usage for artifacts
        if cooldowns["teleport"] == 0 and my_mana >= 20 and artifacts:
            for a in artifacts:
                # Don't teleport if it would cause collision
                if will_collide(a["position"]):
                    continue

                artifact_value = get_artifact_value(a)
                dist = manhattan_dist(my_pos, a["position"])

                # Teleport if artifact is valuable and more than 2 steps away
                # This makes teleport much more useful for grabbing items
                if artifact_value >= 60 and dist > 2:
                    s = score_action("teleport", target=a["position"])
                    # Add bonus based on artifact value
                    s += artifact_value * 1.5
                    if s > best_score:
                        best_score = s
                        best_action = {"move": [0,0], "spell": {"name": "teleport", "target": a["position"]}}
                # Also teleport for any artifact if it's far away
                elif dist > 4:
                    s = score_action("teleport", target=a["position"])
                    s += artifact_value
                    if s > best_score:
                        best_score = s
                        best_action = {"move": [0,0], "spell": {"name": "teleport", "target": a["position"]}}
        
        for dx, dy in valid_moves:
            move_vec = [dx, dy]
            new_pos = [my_pos[0]+dx, my_pos[1]+dy]
            
            # Skip collision positions early
            if will_collide(new_pos):
                continue
            
            # Move only
            s = score_action("wait", move_vec=move_vec)
            if s > best_score:
                best_score = s
                best_action = {"move": move_vec, "spell": None}
            
            # FIXED: Move + Fireball with proper distance check from NEW position
            if cooldowns["fireball"] == 0 and my_mana >= 30:
                 # Check distance from the NEW position after moving
                 dist_from_new_pos = chebyshev_dist(new_pos, opp_pos)
                 if dist_from_new_pos <= 5:
                     s = score_action("fireball", target=opp_pos, move_vec=move_vec)
                     # NEW: Extra bonus in punish heal mode
                     if PUNISH_HEAL_MODE:
                         s += 100
                     if s > best_score:
                         best_score = s
                         best_action = {"move": move_vec, "spell": {"name": "fireball", "target": opp_pos}}

            # Move + Melee
            if cooldowns["melee_attack"] == 0:
                 targets = []
                 if manhattan_dist(new_pos, opp_pos) == 1:
                     targets.append(("wizard", opp_pos))
                 for m in minions:
                     if m["owner"] != self.name and manhattan_dist(new_pos, m["position"]) == 1:
                         targets.append(("minion", m["position"]))
                 
                 for target_type, target_pos in targets:
                     s = score_action("melee_attack", target=target_pos, move_vec=move_vec)
                     if target_type == "minion":
                         s += 35  # Increased from 30 - prioritize clearing enemy minions
                     # NEW: Extra bonus in punish heal mode
                     if target_type == "wizard" and PUNISH_HEAL_MODE:
                         s += 100
                     if s > best_score:
                         best_score = s
                         best_action = {"move": move_vec, "spell": {"name": "melee_attack", "target": target_pos}}

            # Move + Shield
            if cooldowns["shield"] == 0 and my_mana >= 20 and not self_data.get("shield_active"):
                s = score_action("shield", move_vec=move_vec)
                if s > best_score:
                    best_score = s
                    best_action = {"move": move_vec, "spell": {"name": "shield"}}
            
            # Move + Heal - be smarter about when to heal
            if cooldowns["heal"] == 0 and my_mana >= 25 and my_hp < 100:
                # Only heal if we're below 75 HP or in danger
                if my_hp < 75 or total_threat > 15:
                    s = score_action("heal", move_vec=move_vec)
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "heal"}}
                    
            # Move + Summon (NEW: Better timing)
            # Only summon early-mid game or when we have mana advantage
            if cooldowns["summon"] == 0 and my_mana >= 50:
                my_minion_count = sum(1 for m in minions if m["owner"] == self.name)
                opp_minion_count = sum(1 for m in minions if m["owner"] != self.name)
                
                # Summon if: early game OR we're behind in minions OR we have mana advantage
                if turn_count < 30 or my_minion_count < opp_minion_count or my_mana > opp_data["mana"] + 30:
                    s = score_action("summon", move_vec=move_vec)
                    if s > best_score:
                        best_score = s
                        best_action = {"move": move_vec, "spell": {"name": "summon"}}

        # Blink (for repositioning or artifact grabbing)
        if cooldowns["blink"] == 0 and my_mana >= 10:
             # Try blinking to artifacts
             for a in artifacts:
                 if manhattan_dist(my_pos, a["position"]) <= 2:
                     s = score_action("blink", target=a["position"])
                     if s > best_score:
                         best_score = s
                         best_action = {"move": [0,0], "spell": {"name": "blink", "target": a["position"]}}
             
             # Try blinking away from danger
             if total_threat > 20:
                 for bx in [-2, -1, 0, 1, 2]:
                     for by in [-2, -1, 0, 1, 2]:
                         if abs(bx) + abs(by) == 0: continue
                         if manhattan_dist([0,0], [bx,by]) > 2: continue
                         
                         tx, ty = my_pos[0]+bx, my_pos[1]+by
                         if 0 <= tx < BOARD_SIZE and 0 <= ty < BOARD_SIZE:
                             if manhattan_dist([tx, ty], opp_pos) > manhattan_dist(my_pos, opp_pos):
                                 s = score_action("blink", target=[tx, ty])
                                 if s > best_score:
                                     best_score = s
                                     best_action = {"move": [0,0], "spell": {"name": "blink", "target": [tx, ty]}}

        return best_action
    
    def _update_opponent_profile(self, opp_data, opp_pos, my_hp, turn_count):
        """Update our understanding of the opponent's playstyle.

        Uses EMA signals so the bot adapts quickly when the opponent shifts strategy,
        while remaining stable under noise.
        """
        profile = self.opponent_profile
        profile["turns_observed"] += 1

        def clamp(x: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, x))

        def ema(prev: float, obs: float, rate: float) -> float:
            return (1.0 - rate) * prev + rate * obs

        opp_hp = opp_data["hp"]
        opp_mana = opp_data["mana"]

        # Initialize last turn trackers
        if profile.get("last_turn_mana") is None:
            profile["last_turn_mana"] = profile.get("last_mana", opp_mana)
        if profile.get("last_turn_hp") is None:
            profile["last_turn_hp"] = profile.get("last_hp", opp_hp)

        # --- Signals: distance-to-us (range preference) ---
        my_pos = getattr(self, "_my_pos_for_profile", None)
        if my_pos is not None and opp_pos is not None:
            dist_to_us = abs(opp_pos[0] - my_pos[0]) + abs(opp_pos[1] - my_pos[1])
            profile["last_dist_to_us"] = dist_to_us
        else:
            dist_to_us = profile.get("last_dist_to_us", 5)

        if dist_to_us is None:
            dist_to_us = 5

        # --- Signals: damage to us this turn ---
        dmg_to_us = 0.0
        if my_hp < profile["last_hp"]:
            dmg_to_us = float(profile["last_hp"] - my_hp)
            profile["damage_dealt_to_us"] += int(dmg_to_us)

        # --- Signals: spell usage by mana deltas (best effort) ---
        mana_spent = max(0, int(profile["last_turn_mana"] - opp_mana))

        # A dynamic adapt rate: react faster on big events (damage spikes / large mana spends)
        event_strength = 0.0
        if dmg_to_us > 0:
            event_strength += min(1.0, dmg_to_us / 10.0)
        if mana_spent > 0:
            event_strength += min(1.0, mana_spent / 50.0)
        rate = clamp(self._base_adapt_rate + 0.10 * event_strength, 0.10, 0.28)

        used_fireball = 1.0 if mana_spent >= 30 else 0.0
        used_heal = 1.0 if (mana_spent >= 25 and opp_hp > profile["last_turn_hp"]) else 0.0
        used_summon = 1.0 if mana_spent >= 50 else 0.0
        used_shield = 1.0 if (mana_spent >= 20 and bool(opp_data.get("shield_active"))) else 0.0
        used_mobility = 1.0 if (mana_spent >= 10 and (not used_fireball) and (not used_heal) and (not used_summon) and (not used_shield)) else 0.0

        # Keep existing counters so the rest of the bot still works
        if used_fireball:
            profile["spell_usage"]["fireball"] += 1
        if used_heal:
            profile["spell_usage"]["heal"] += 1
            profile["times_healed"] += 1
        if used_shield:
            profile["spell_usage"]["shield"] += 1
            profile["times_used_shield"] += 1
        if used_summon:
            profile["spell_usage"]["summon"] += 1
        if used_mobility:
            # Can't reliably separate teleport vs blink; record as teleport for compatibility
            profile["spell_usage"]["teleport"] += 1

        # Update EMAs
        profile["ema_dist_to_us"] = ema(profile.get("ema_dist_to_us", 5.0), float(dist_to_us), rate)
        profile["ema_damage_to_us"] = ema(profile.get("ema_damage_to_us", 0.0), dmg_to_us, rate)
        profile["ema_fireball_rate"] = ema(profile.get("ema_fireball_rate", 0.0), used_fireball, rate)
        profile["ema_heal_rate"] = ema(profile.get("ema_heal_rate", 0.0), used_heal, rate)
        profile["ema_shield_rate"] = ema(profile.get("ema_shield_rate", 0.0), used_shield, rate)
        profile["ema_mobility_rate"] = ema(profile.get("ema_mobility_rate", 0.0), used_mobility, rate)

        casted = 1.0 if mana_spent > 0 else 0.0
        profile["_ema_cast_rate"] = ema(profile.get("_ema_cast_rate", 0.0), casted, rate)
        profile["mana_conservation"] = clamp(1.0 - profile["_ema_cast_rate"], 0.0, 1.0)

        # Aggression heuristic as continuous value, then EMA it
        damage_term = clamp(profile["ema_damage_to_us"] / 10.0, 0.0, 1.0)
        fireball_term = clamp(profile["ema_fireball_rate"], 0.0, 1.0)
        heal_term = clamp(profile["ema_heal_rate"], 0.0, 1.0)
        raw_aggr = 0.18 + 0.62 * damage_term + 0.48 * fireball_term - 0.35 * heal_term
        raw_aggr = clamp(raw_aggr, 0.0, 1.0)
        profile["ema_aggression"] = ema(profile.get("ema_aggression", 0.5), raw_aggr, rate)
        profile["aggression_score"] = profile["ema_aggression"]

        # Backward-compatible avg_distance field (now represents distance-to-us preference)
        profile["avg_distance"] = profile["ema_dist_to_us"]

        # Update last known state
        profile["last_hp"] = opp_hp
        profile["last_mana"] = opp_mana
        profile["last_position"] = opp_pos.copy() if isinstance(opp_pos, list) else list(opp_pos)
        profile["last_turn_mana"] = opp_mana
        profile["last_turn_hp"] = opp_hp

    def _get_adaptive_strategy(self):
        """Determine strategy based on opponent profile.

        Uses continuous adjustments instead of hard buckets. This typically improves
        performance against opponents that change tempo mid-match.
        """
        profile = self.opponent_profile

        def clamp(x: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, x))

        # Base strategy (slightly aggressive baseline)
        aggression = 0.62
        defensiveness = 0.38
        artifact_priority = 0.72
        range_preference = 3.0
        spell_conservation = 0.25

        # Early game: keep stable
        if profile.get("turns_observed", 0) < 6:
            return {
                "aggression": aggression,
                "defensiveness": defensiveness,
                "artifact_priority": artifact_priority,
                "range_preference": range_preference,
                "spell_conservation": spell_conservation,
            }

        aggr = float(profile.get("ema_aggression", profile.get("aggression_score", 0.5)))
        heal_rate = float(profile.get("ema_heal_rate", 0.0))
        fireball_rate = float(profile.get("ema_fireball_rate", 0.0))
        shield_rate = float(profile.get("ema_shield_rate", 0.0))
        mobility_rate = float(profile.get("ema_mobility_rate", 0.0))
        dist_pref = float(profile.get("ema_dist_to_us", 5.0))

        # Closeout signal: we should stop looping artifacts and force trades
        # Triggered by opponents who either heal a lot or are very mobile.
        closeout = clamp(0.55 * mobility_rate + 0.45 * heal_rate, 0.0, 1.0)

        # Aggressive opponent -> we get more defensive and prefer range
        defensiveness += (aggr - 0.55) * 0.45
        aggression += (0.55 - aggr) * 0.35
        range_preference += (aggr - 0.55) * 1.0

        # Healers -> punish (push aggression and spend spells)
        aggression += heal_rate * 0.28
        spell_conservation -= heal_rate * 0.12

        # Fireball-heavy -> survive: more defensive, more range, more artifacts
        defensiveness += fireball_rate * 0.38
        range_preference += fireball_rate * 1.4
        artifact_priority += fireball_rate * 0.12

        # Shield spam -> slightly more artifact control, and don't overspend spells into shield
        artifact_priority += shield_rate * 0.08
        spell_conservation += shield_rate * 0.06

        # Mobility -> contest artifacts harder & slightly reduce range (avoid endless chasing)
        artifact_priority += mobility_rate * 0.14
        aggression += mobility_rate * 0.10
        range_preference -= mobility_rate * 0.5

        # If they keep far distance naturally, adjust to not over-chase
        range_preference += clamp((dist_pref - 4.0) / 3.0, -0.3, 0.6)

        # Apply closeout: reduce artifact chasing and increase aggression slightly
        artifact_priority *= (1.0 - 0.22 * closeout)
        aggression += 0.10 * closeout
        spell_conservation -= 0.05 * closeout

        return {
            "aggression": aggression,
            "defensiveness": defensiveness,
            "artifact_priority": artifact_priority,
            "range_preference": range_preference,
            "spell_conservation": spell_conservation,
            "closeout": closeout,
        }