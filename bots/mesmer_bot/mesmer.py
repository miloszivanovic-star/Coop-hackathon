from __future__ import annotations

from typing import Any, Dict, List, Optional

from bots.bot_interface import BotInterface
from game.rules import BOARD_SIZE, SPELLS


class MesmerBot(BotInterface):
    def __init__(self):
        self._name = "Mesmer"
        self._sprite_path = "assets/wizards/mesmer-original.png"
        self._minion_sprite_path = "assets/minions/mesmer.png"
        self._turn = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def sprite_path(self) -> Optional[str]:
        return self._sprite_path

    @property
    def minion_sprite_path(self) -> Optional[str]:
        return self._minion_sprite_path

    def decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self._turn += 1

        me = state["self"]
        opp = state["opponent"]
        artifacts = state.get("artifacts", [])
        minions = state.get("minions", [])
        board_size = state.get("board_size", BOARD_SIZE)

        my_pos = list(me["position"])
        opp_pos = list(opp["position"])
        cd = me["cooldowns"]
        mana = me["mana"]
        hp = me["hp"]
        shield_active = me.get("shield_active", False)

        opp_cd = opp["cooldowns"]
        opp_mana = opp["mana"]
        opp_hp = opp["hp"]
        opp_shield = opp.get("shield_active", False)

        enemy_minions = [m for m in minions if m["owner"] != me["name"]]
        own_minions = [m for m in minions if m["owner"] == me["name"]]

        phase = self._phase()

        move = [0, 0]
        spell: Optional[Dict[str, Any]] = None

        dist_opp = self.cheb(my_pos, opp_pos)
        adj_opp = self.manhattan(my_pos, opp_pos) == 1
        opp_fireball_ready = opp_cd.get("fireball", 0) == 0 and opp_mana >= SPELLS["fireball"]["cost"]
        my_fireball_ready = cd.get("fireball", 0) == 0 and mana >= SPELLS["fireball"]["cost"]
        my_melee_ready = cd.get("melee_attack", 0) == 0
        blink_ready = cd.get("blink", 0) == 0 and mana >= SPELLS["blink"]["cost"]

        # 1) Fast kills
        if adj_opp and my_melee_ready and opp_hp <= SPELLS["melee_attack"]["damage"]:
            spell = {"name": "melee_attack", "target": opp_pos}
        elif my_fireball_ready and dist_opp <= SPELLS["fireball"]["range"] and not opp_shield:
            if opp_hp <= SPELLS["fireball"]["damage"]:
                spell = {"name": "fireball", "target": opp_pos}

        if not spell:
            lethal_fireball = opp_fireball_ready and dist_opp <= SPELLS["fireball"]["range"]
            low_hp = hp <= 50
            if hp <= 35 and cd.get("heal", 0) == 0 and mana >= SPELLS["heal"]["cost"]:
                spell = {"name": "heal"}
            elif (
                low_hp
                and cd.get("shield", 0) == 0
                and mana >= SPELLS["shield"]["cost"]
                and not shield_active
                and (lethal_fireball or adj_opp or self._nearby_enemy(my_pos, enemy_minions))
            ):
                spell = {"name": "shield"}

        # 2) Board presence
        if not spell and not own_minions and cd.get("summon", 0) == 0 and mana >= SPELLS["summon"]["cost"] + 5 and hp >= 45:
            spell = {"name": "summon"}

        # 3) Artifact races
        artifact_target = self._best_artifact(my_pos, opp_pos, artifacts)
        if not spell and artifact_target:
            my_d = self.cheb(my_pos, artifact_target["position"])
            opp_d = self.cheb(opp_pos, artifact_target["position"])
            need_resource = mana <= 70 or hp <= 75
            racing = opp_d <= my_d

            if cd.get("teleport", 0) == 0 and mana >= SPELLS["teleport"]["cost"] and (racing or my_d > 2):
                spell = {"name": "teleport", "target": artifact_target["position"]}
            elif blink_ready and my_d > 2:
                blink_pos = self._step_blink(my_pos, artifact_target["position"], board_size)
                if blink_pos:
                    spell = {"name": "blink", "target": blink_pos}
            if not spell and (need_resource or racing):
                move = self.move_toward(my_pos, artifact_target["position"], board_size)

        # 4) Pressure
        if not spell:
            if adj_opp and my_melee_ready:
                spell = {"name": "melee_attack", "target": opp_pos}
            elif my_melee_ready and enemy_minions:
                adj_minions = [m for m in enemy_minions if self.manhattan(my_pos, m["position"]) == 1]
                if adj_minions:
                    target = min(adj_minions, key=lambda m: m["hp"])
                    spell = {"name": "melee_attack", "target": target["position"]}

        if not spell and my_fireball_ready:
            fb_target = self._fireball_target(my_pos, opp, enemy_minions)
            if fb_target:
                spell = {"name": "fireball", "target": fb_target}

        # 5) Positioning
        if move == [0, 0]:
            threats = [opp_pos] + [m["position"] for m in enemy_minions]
            cautious = hp <= 55 or opp_fireball_ready
            want_space = cautious and (dist_opp <= 3 or self._nearby_enemy(my_pos, enemy_minions, radius=2))

            if want_space:
                if blink_ready:
                    blink_pos = self._escape_blink(my_pos, threats, board_size)
                    if blink_pos:
                        spell = spell or {"name": "blink", "target": blink_pos}
                    else:
                        move = self._escape_step(my_pos, threats, own_minions, board_size, opp_fireball_ready)
                else:
                    move = self._escape_step(my_pos, threats, own_minions, board_size, opp_fireball_ready)
            elif phase == "late" and hp > 60 and mana >= 40 and dist_opp > 1:
                move = self.move_toward(my_pos, opp_pos, board_size)
            elif phase == "mid" and artifact_target:
                move = self.move_toward(my_pos, artifact_target["position"], board_size)
            else:
                center = [board_size // 2, board_size // 2]
                move = self.move_toward(my_pos, center, board_size)

        if move != [0, 0] and opp_fireball_ready and self._adjacent_to_any(self._apply_move(my_pos, move, board_size), own_minions):
            move = self._escape_step(my_pos, [opp_pos], own_minions, board_size, opp_fireball_ready)

        return {"move": move, "spell": spell}

    def _phase(self) -> str:
        if self._turn >= 12:
            return "late"
        if self._turn >= 5:
            return "mid"
        return "early"

    @staticmethod
    def cheb(a: List[int], b: List[int]) -> int:
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    @staticmethod
    def manhattan(a: List[int], b: List[int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _apply_move(pos: List[int], move: List[int], board_size: int) -> List[int]:
        new_pos = [pos[0] + move[0], pos[1] + move[1]]
        if 0 <= new_pos[0] < board_size and 0 <= new_pos[1] < board_size:
            return new_pos
        return pos

    def move_toward(self, start: List[int], target: List[int], board_size: int) -> List[int]:
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        move = [step_x, step_y]
        return self._apply_move(start, move, board_size) != start and move or [0, 0]

    def move_away(self, start: List[int], target: List[int], board_size: int) -> List[int]:
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        step_x = -1 if dx >= 0 else 1
        step_y = -1 if dy >= 0 else 1
        move = [step_x, step_y]
        return self._apply_move(start, move, board_size) != start and move or [0, 0]

    def _nearby_enemy(self, my_pos: List[int], enemies: List[Dict[str, Any]], radius: int = 1) -> bool:
        return any(self.manhattan(my_pos, e["position"]) <= radius for e in enemies)

    def _adjacent_to_any(self, pos: List[int], entities: List[Dict[str, Any]]) -> bool:
        return any(self.manhattan(pos, e["position"]) == 1 for e in entities)

    def _best_artifact(self, my_pos: List[int], opp_pos: List[int], artifacts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not artifacts:
            return None

        def score(artifact: Dict[str, Any]) -> int:
            my_d = self.cheb(my_pos, artifact["position"])
            opp_d = self.cheb(opp_pos, artifact["position"])
            return (opp_d - my_d) * 10 - my_d

        return max(artifacts, key=score)

    def _fireball_target(self, my_pos: List[int], opp: Dict[str, Any], enemy_minions: List[Dict[str, Any]]) -> Optional[List[int]]:
        opp_pos = opp["position"]
        opp_shield = opp.get("shield_active", False)
        in_range_entities = [e for e in enemy_minions + [opp] if self.cheb(my_pos, e["position"]) <= SPELLS["fireball"]["range"]]

        if not in_range_entities:
            return None

        # Prefer lethal on opp, then lowest HP target, avoiding shield if possible
        lethal_on_opp = not opp_shield and opp["hp"] <= SPELLS["fireball"]["damage"]
        if lethal_on_opp:
            return opp_pos

        best = min(in_range_entities, key=lambda e: e["hp"])
        if best is opp and opp_shield:
            return None
        return best["position"]

    def _escape_step(
        self, my_pos: List[int], threats: List[List[int]], own_minions: List[Dict[str, Any]], board_size: int, avoid_splash: bool
    ) -> List[int]:
        best_move = [0, 0]
        best_score = -10.0

        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidate = [dx, dy]
                new_pos = self._apply_move(my_pos, candidate, board_size)
                if new_pos == my_pos and candidate != [0, 0]:
                    continue

                min_dist = min(self.cheb(new_pos, t) for t in threats)
                score = min_dist - (1 if avoid_splash and any(self.manhattan(new_pos, m["position"]) == 1 for m in own_minions) else 0)

                if score > best_score:
                    best_score = score
                    best_move = candidate

        return best_move

    def _step_blink(self, my_pos: List[int], target: List[int], board_size: int) -> Optional[List[int]]:
        limit = SPELLS["blink"]["distance"]
        candidates = []
        for dx in range(-limit, limit + 1):
            for dy in range(-limit, limit + 1):
                if max(abs(dx), abs(dy)) == 0 or max(abs(dx), abs(dy)) > limit:
                    continue
                pos = [my_pos[0] + dx, my_pos[1] + dy]
                if 0 <= pos[0] < board_size and 0 <= pos[1] < board_size:
                    candidates.append(pos)
        if not candidates:
            return None
        return min(candidates, key=lambda p: self.cheb(p, target))

    def _escape_blink(self, my_pos: List[int], threats: List[List[int]], board_size: int) -> Optional[List[int]]:
        limit = SPELLS["blink"]["distance"]
        best_pos = None
        best_score = -1
        for dx in range(-limit, limit + 1):
            for dy in range(-limit, limit + 1):
                if max(abs(dx), abs(dy)) == 0 or max(abs(dx), abs(dy)) > limit:
                    continue
                pos = [my_pos[0] + dx, my_pos[1] + dy]
                if not (0 <= pos[0] < board_size and 0 <= pos[1] < board_size):
                    continue
                score = min(self.cheb(pos, t) for t in threats)
                if score > best_score:
                    best_score = score
                    best_pos = pos
        return best_pos
