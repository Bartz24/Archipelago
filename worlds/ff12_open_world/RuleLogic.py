import dataclasses
from typing import Any, ClassVar, List

from BaseClasses import CollectionState
from rule_builder.rules import Rule
from .Items import item_data_table

DIFFICULTY_RANGE = 3

def state_has_at_least(possible: List[bool], count: int) -> bool:
    # Returns true if at least count of the possible are true
    return possible.count(True) >= count

def item_is_category(item_name : str, category : str) -> bool:
    if item_name not in item_data_table:
        return False
    return item_data_table[item_name].category == category

def state_has_category(state : CollectionState, player : int, category: str, count: int = 1) -> bool:
    category_possible = [item_is_category(item, category) for item in state.prog_items[player]]
    return state_has_at_least(category_possible, count)

def get_chara_count(state: CollectionState, player: int) -> int:
    count = 0
    if state.has("Vaan", player):
        count += 1
    if state.has("Balthier", player):
        count += 1
    if state.has("Fran", player):
        count += 1
    if state.has("Basch", player):
        count += 1
    if state.has("Ashe", player):
        count += 1
    if state.has("Penelo", player):
        count += 1
    if state.has("Guest", player):
        count += 1
    return count

def state_has_characters(state: CollectionState, difficulty: int, player: int) -> bool:
    chara_count = get_chara_count(state, player)
    if difficulty >= 7:
        return chara_count >= 6 and state.has("Second Board", player)
    if difficulty >= 5:
        return chara_count >= 5 and state.has("Second Board", player)
    if difficulty >= 4:
        return chara_count >= 4
    if difficulty >= 3:
        return chara_count >= 3
    return True


@dataclasses.dataclass()
class DifficultyAccessRule(Rule[Any], game="Final Fantasy 12 Open World"):
    difficulty: int

    def _instantiate(self, world):
        return self.Resolved(
            self.difficulty,
            world.difficulty_region_dependencies(self.difficulty),
            player=world.player,
            caching_enabled=getattr(world, "rule_caching_enabled", False),
        )

    class Resolved(Rule.Resolved):
        difficulty: int
        region_names: tuple[str, ...]
        force_recalculate: ClassVar[bool] = True

        def _evaluate(self, state: CollectionState) -> bool:
            world = state.multiworld.worlds[self.player]
            return world.state_has_difficulty_access(state, self.difficulty, self.player, DIFFICULTY_RANGE)

        def region_dependencies(self) -> dict[str, set[int]]:
            return {name: {id(self)} for name in self.region_names}

        def __str__(self) -> str:
            return f"Difficulty {self.difficulty} access"
