import random
from bots.bot_interface import BotInterface

class IvraBot(BotInterface):
    def __init__(self):
        self._name = "IvraBot"
        # Re-using sample assets for now, can be customized later if needed
        self._sprite_path = "assets/wizards/sample_bot1.png" 
        self._minion_sprite_path = "assets/minions/minion_1.png"

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
        cooldowns = self_data["cooldowns"]

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
            moves = [[0,0]] # Stay
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    nx, ny = pos[0]+dx, pos[1]+dy
                    if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                        moves.append([dx, dy])
            return moves

        # --- Threat Analysis ---
        # Calculate potential incoming damage this turn if we do NOTHING
        # Used to value defensive actions
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
        
        # --- Dynamic Weights (v12.0 Dual Evolution Winner) ---
        # The "Tank Buster" Strategy
        # Base Survival: 5.0 (Protected)
        # Bloodlust Aggro: 78.6 (Nuke them from orbit)
        
        W_SURVIVAL = 5.0 
        W_AGGRO = 15.0
        W_MANA = 0.0 
        
        # Defensive Shift
        if my_hp < 40: W_SURVIVAL = 1.0
        if my_hp < 20: W_SURVIVAL = 10.0
            
        # Offensive Shift (Bloodlust)
        # Threshold 62
        if opp_hp < 62 and my_hp > 30:
            W_AGGRO = 78.6 # Extreme Nuke Value

        # --- Candidate Generation & Scoring ---
        candidates = []

        # A candidate is (score, action_dict)
        
        # Helper to simulate state
        def score_action(act_type, target=None, move_vec=[0,0]):
            # Start with current state
            sim_hp = my_hp
            sim_opp_hp = opp_hp
            sim_mana = my_mana
            sim_pos = [my_pos[0] + move_vec[0], my_pos[1] + move_vec[1]]
            
            # 1. Apply Action Costs & Effects
            action_cost = 0
            dmg_dealt = 0
            healed = 0
            shielded = False
            escaped = False # Did we move out of range?
            
            if act_type == "fireball":
                action_cost = 30
                # Check hit chance? Assume hit if in range
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    blocked = 0
                    if opp_data.get("shield_active"): blocked = SHIELD_BLOCK
                    dmg_dealt = max(0, FIREBALL_DMG - blocked)
                    
            elif act_type == "melee_attack":
                action_cost = 0 # Free but 1 turn
                if manhattan_dist(sim_pos, target if target else opp_pos) == 1:
                    dmg_dealt = MELEE_DMG # Ignores shield
                    
            elif act_type == "heal":
                action_cost = 25
                healed = HEAL_AMT
                
            elif act_type == "shield":
                action_cost = 20
                shielded = True
                
            elif act_type == "blink":
                action_cost = 10
                sim_pos = target # Teleport there
                
            elif act_type == "teleport":
                action_cost = 20
                sim_pos = target

            elif act_type == "summon":
                action_cost = 50
                # Minion value is abstract
                pass

            # Update My State
            sim_mana -= action_cost 
            sim_hp = min(100, sim_hp + healed)
            
            # 2. Apply Enemy Retaliation (Simulated)
            # Re-calc threats based on NEW position
            
            # Fireball Threat
            incoming = 0
            if opp_data["mana"] >= 30 and opp_data["cooldowns"]["fireball"] == 0:
                if chebyshev_dist(sim_pos, opp_pos) <= 5:
                    dmg = FIREBALL_DMG
                    if shielded or self_data.get("shield_active"): # Shield blocks fireball
                         dmg = max(0, dmg - SHIELD_BLOCK)
                    incoming += dmg
            
            # Melee Threat
            if manhattan_dist(sim_pos, opp_pos) == 1 and opp_data["cooldowns"]["melee_attack"] == 0:
                incoming += MELEE_DMG # Ignores shield
                
            # Minion Threat (Simplified)
            for m in minions:
                if m["owner"] != self.name and manhattan_dist(sim_pos, m["position"]) == 1:
                    incoming += MELEE_DMG # Ignores shield

            sim_hp -= incoming
            sim_opp_hp -= dmg_dealt
            
            # 3. Calculate Score
            
            # Win/Loss Check
            if sim_hp <= 0: return -10000.0 # Death is bad
            if sim_opp_hp <= 0: return 10000.0 # Win is good
            
            score = 0.0
            
            # HP Score (Weighted by Adaptive Weights)
            score += sim_hp * W_SURVIVAL
            
            # Opp HP Score (We want it low)
            score -= sim_opp_hp * W_AGGRO
            
            # Mana Score
            score += sim_mana * W_MANA
            
            # Artifact Control
            # Bonus for being close to artifacts
            if artifacts:
                closest_dist = min([manhattan_dist(sim_pos, a["position"]) for a in artifacts])
                if closest_dist == 0: score += 15 # Picked up
                else: score -= closest_dist * 0.5 # Penalty for distance
                
            # Positioning - Map Control (v9.0)
            # Center is [4.5, 4.5] roughly. Use [4,4] or [5,5].
            # Penalty for being far from center to avoid corners/edges where movement is limited.
            dist_to_center = manhattan_dist(sim_pos, [4, 5]) # Approximate center
            score -= dist_to_center * 1.0 # Gentle push to center

            # Opportunity - Threat Projection (v9.0)
            # Bonus for ENDING the turn in a position where we COULD attack (next turn), even if we don't attack now.
            # This encourages "Stalking".
            can_fireball_next = chebyshev_dist(sim_pos, opp_pos) <= 5
            can_melee_next = manhattan_dist(sim_pos, opp_pos) == 1
            if can_fireball_next or can_melee_next:
                score += 10.0 # Significant bonus for maintaining threat
            
            # Action Specific Bonuses
            if act_type == "summon":
                score += 15 # Value of a minion
                
            return score

        # --- Evaluate Options ---
        
        # 1. Spells + Move(0,0)
        # We simplify: we either Move OR Cast. (Or Move then Cast later? No, game is move+spell one dict)
        # Actually API is {"move": [dx,dy], "spell": {}}
        # We can move AND cast.
        # To simplify search space: 
        # Evaluate Best Cast at Current Pos.
        # Evaluate Best Move (with no cast? or best cast?)
        
        # Iteration:
        # Try all Spells (at current pos)
        # Try all Moves (without spell)
        # Try specific Moves + Specific Spells? Too many combos (9 moves * 7 spells = 63). 
        # Actually 63 is small for a computer. We can do it!
        
        valid_moves = get_valid_moves(my_pos)
        
        best_score = -99999
        best_action = {"move": [0,0], "spell": None}
        
        # Filter valid moves to optimization
        # If we are safe, we might skip checking every move.
        # But let's check all 9 moves.
        
        for dx, dy in valid_moves:
            # Check availability logic first to prune
            move_vec = [dx, dy]
            
            # Option A: Just Move (No Spell)
            s = score_action("wait", move_vec=move_vec)
            if s > best_score:
                best_score = s
                best_action = {"move": move_vec, "spell": None}
                
            # Option B: Move + Fireball
            if cooldowns["fireball"] == 0 and my_mana >= 30:
                 # Check target validity from NEW position?
                 # Rule: "Spell target is validated vs caster position AFTER move".
                 new_pos = [my_pos[0]+dx, my_pos[1]+dy]
                 if chebyshev_dist(new_pos, opp_pos) <= 5:
                     s = score_action("fireball", target=opp_pos, move_vec=move_vec)
                     if s > best_score:
                         best_score = s
                         best_action = {"move": move_vec, "spell": {"name": "fireball", "target": opp_pos}}

            # Option C: Move + Melee
            if cooldowns["melee_attack"] == 0:
                 new_pos = [my_pos[0]+dx, my_pos[1]+dy]
                 # Find target
                 target = None
                 if manhattan_dist(new_pos, opp_pos) == 1:
                     target = opp_pos
                 # Check minions
                 # (Simplified: prioritize wizard)
                 if target:
                     s = score_action("melee_attack", target=target, move_vec=move_vec)
                     if s > best_score:
                         best_score = s
                         best_action = {"move": move_vec, "spell": {"name": "melee_attack", "target": target}}

            # Option D: Move + Shield
            if cooldowns["shield"] == 0 and my_mana >= 20 and not self_data.get("shield_active"):
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

        # Special Case: Blink/Teleport (Move is usually 0,0 for these as they ARE movement)
        if cooldowns["blink"] == 0 and my_mana >= 10:
             # Try random spots or smart spots
             # Try spots away from threat?
             # Try all 8 spots at dist 2?
             for bx in [-2, -1, 0, 1, 2]:
                 for by in [-2, -1, 0, 1, 2]:
                     if abs(bx) + abs(by) == 0: continue
                     if manhattan_dist([0,0], [bx,by]) > 2: continue # Blink range
                     
                     tx, ty = my_pos[0]+bx, my_pos[1]+by
                     if 0 <= tx < BOARD_SIZE and 0 <= ty < BOARD_SIZE:
                         s = score_action("blink", target=[tx, ty])
                         if s > best_score:
                             best_score = s
                             best_action = {"move": [0,0], "spell": {"name": "blink", "target": [tx, ty]}}

        if cooldowns["teleport"] == 0 and my_mana >= 20:
             # Just try teleporting to artifacts
             for a in artifacts:
                 s = score_action("teleport", target=a["position"])
                 if s > best_score:
                     best_score = s
                     best_action = {"move": [0,0], "spell": {"name": "teleport", "target": a["position"]}}

        return best_action
