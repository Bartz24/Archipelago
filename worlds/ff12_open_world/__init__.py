import json
import os
from typing import List, Mapping, Any, Dict

from BaseClasses import Region, Tutorial, ItemClassification, CollectionState, Callable
from worlds.AutoWorld import WebWorld, World
from worlds.generic.Rules import add_rule
from worlds.LauncherComponents import launch_subprocess, components, Component, Type

from .Items import FF12OpenWorldItem, item_data_table, FF12OW_BASE_ID, item_table, filler_items, filler_weights
from .Locations import FF12OpenWorldLocation, location_data_table, location_table
from .Options import FF12OpenWorldGameOptions
from .Regions import region_data_table
from .Rules import rule_data_table
from .Events import event_data_table, FF12OpenWorldEventData
from .RuleLogic import state_has_characters


def launch_client():
    from .Client import launch
    launch_subprocess(launch, name="FF12 Open World Client")


components.append(Component("FF12 Open World Client", "FF12OpenWorldClient",
                            func=launch_client, component_type=Type.CLIENT))

FF12OW_VERSION = "0.1.0"
character_names = ["Vaan", "Ashe", "Fran", "Balthier", "Basch", "Penelo"]


class FF12OpenWorldWebWorld(WebWorld):
    theme = "ocean"

    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Final Fantasy 12 Open World multiworld.",
        "English",
        "multiworld_en.md",
        "multiworld/en",
        ["Bartz24"]
    )]


class FF12OpenWorldWorld(World):
    """TODO"""

    game = "Final Fantasy 12 Open World"
    data_version = 3
    web = FF12OpenWorldWebWorld()
    options_dataclass = FF12OpenWorldGameOptions
    options: FF12OpenWorldGameOptions
    location_name_to_id = location_table
    item_name_to_id = item_table
    selected_treasures = []
    used_items: set[str] = set()
    character_order = list(range(6))

    def create_item(self, name: str) -> FF12OpenWorldItem:
        return FF12OpenWorldItem(name, item_data_table[name].classification, item_data_table[name].code, self.player)

    def create_items(self) -> None:
        self.used_items.clear()
        item_pool: List[FF12OpenWorldItem] = []
        progression_items = [name for name, data in item_data_table.items()
                             if data.classification & ItemClassification.progression and
                             name != "Writ of Transit"]
        if self.options.bahamut_unlock == "random_location":
            progression_items.append("Writ of Transit")

        for name in progression_items:
            for _ in range(item_data_table[name].duplicateAmount):
                item_pool.append(self.create_item(name))

        abilities = [name for name, data in item_data_table.items()
                     if item_data_table["Cure"].code <= data.code <= item_data_table["Gil Toss"].code]
        # Select a random 50% to 75% of the abilities
        ability_count = self.multiworld.random.randint(len(abilities) // 2, len(abilities) * 3 // 4)
        selected_abilities = self.multiworld.random.sample(abilities, k=ability_count)
        for name in selected_abilities:
            self.used_items.add(name)
            for _ in range(item_data_table[name].duplicateAmount):
                item_pool.append(self.create_item(name))

        other_useful_items = [name for name, data in item_data_table.items()
                              if data.classification & ItemClassification.useful and name not in abilities]
        for name in other_useful_items:
            self.used_items.add(name)
            for _ in range(item_data_table[name].duplicateAmount):
                item_pool.append(self.create_item(name))

        # Get count of non event locations
        non_events = len([location for location in self.multiworld.get_locations(self.player)
                          if location.name not in event_data_table.keys()])

        # Add filler items to the pool
        for _ in range(non_events - len(item_pool) - 1):
            filler = self.get_filler_item_name()
            self.used_items.add(filler)
            item_pool.append(self.create_item(filler))

        self.multiworld.itempool += item_pool

    def create_regions(self) -> None:
        # Create regions.
        for region_name in region_data_table.keys():
            region = Region(region_name, self.player, self.multiworld)
            self.multiworld.regions.append(region)

        # Add connections
        for region_name, data in region_data_table.items():
            region = self.multiworld.get_region(region_name, self.player)
            region.add_exits(region_data_table[region_name].connecting_regions)

        # Select 255 random treasure type locations.
        treasure_names = [name for name, data in location_data_table.items()
                          if data.type == "treasure"]
        locations_to_add = self.multiworld.random.sample(treasure_names,
                                                         k=255)

        self.selected_treasures = [loc for loc in locations_to_add]

        # Select 50% of the random secondary reward locations (2nd and 3rd indices).
        secondary_reward_names = [name for name, data in location_data_table.items()
                                  if data.type == "reward" and data.secondary_index > 0]
        locations_to_add += self.multiworld.random.sample(secondary_reward_names,
                                                          k=len(secondary_reward_names) // 2)

        # Select 5-10 random starting inventory locations for each character.
        for character in range(6):
            starting_inventory_names = [name for name, data in location_data_table.items()
                                        if data.type == "inventory" and int(data.str_id) == character]
            locations_to_add += self.multiworld.random.sample(starting_inventory_names,
                                                              k=self.multiworld.random.randint(5, 10))

        # Add first fixed index rewards.
        locations_to_add += [name for name, data in location_data_table.items()
                             if data.type == "reward" and data.secondary_index == 0]

        # Place randomly selected locations.
        for location_name in locations_to_add:
            location_data = location_data_table[location_name]
            region = self.multiworld.get_region(location_data.region, self.player)
            region.add_locations({location_name: location_data.address}, FF12OpenWorldLocation)
            self.multiworld.get_location(location_name, self.player).progress_type = location_data.classification

        # Add events
        for event_name, data in event_data_table.items():
            region = self.multiworld.get_region("Ivalice", self.player)
            region.locations.append(FF12OpenWorldLocation(self.player, event_name, None, region))

    def get_filler_item_name(self) -> str:
        filler = self.multiworld.random.choices(filler_items, weights=filler_weights)[0]
        if filler == "Seitengrat" and not self.options.allow_seitengrat:
            filler = "Dhanusha"
        return filler

    def set_rules(self) -> None:
        # Set location rules
        for location in self.multiworld.get_locations(self.player):
            add_rule(location, self.create_rule(location.name))
            if self.options.character_progression_scaling:
                add_rule(location, self.create_chara_rule(location.name))

        # Set event locked items
        for event_name, event_data in event_data_table.items():
            location = self.multiworld.get_location(event_name, self.player)
            location.place_locked_item(self.create_event(event_data.item))

        if self.options.bahamut_unlock == "defeat_cid_2":
            self.multiworld.get_location("Defeat Famfrit and Cid 2 (1)", self.player).place_locked_item(
                self.create_item("Writ of Transit"))
        elif self.options.bahamut_unlock == "collect_pinewood_chops":
            self.multiworld.get_location("Sandalwood Chop (1)", self.player).place_locked_item(
                self.create_item("Writ of Transit"))

        # Completion condition.
        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)

    def create_rule(self, location_name: str) -> Callable[[CollectionState], bool]:
        return lambda state: rule_data_table[location_name](state, self.player)

    def create_chara_rule(self, location_name: str) -> Callable[[CollectionState], bool]:
        if location_name in location_data_table.keys():
            return lambda state: state_has_characters(state,
                                                      location_data_table[location_name].difficulty,
                                                      self.player)
        elif location_name in event_data_table.keys():
            return lambda state: state_has_characters(state,
                                                      event_data_table[location_name].difficulty,
                                                      self.player)

    def create_event(self, event: str) -> FF12OpenWorldItem:
        name = event
        if name in character_names:
            name = character_names[self.character_order[character_names.index(name)]]
        return FF12OpenWorldItem(name, ItemClassification.progression, None, self.player)

    def generate_early(self) -> None:
        if self.options.shuffle_main_party:
            self.character_order = []
            all_characters = list(range(6))
            for _ in range(6):
                character = self.multiworld.random.choice(all_characters)
                self.character_order.append(character)
                all_characters.remove(character)

    def generate_output(self, output_directory: str) -> None:
        data = {
            "seed": self.multiworld.seed_name,  # to identify the seed
            "type": "archipelago",  # to identify the seed type
            "archipelago": {
                "version": FF12OW_VERSION,
                "used_items": list(self.used_items),  # Lets the seed generator fill shops with unused items
                # Store selected treasures for tracking
                "treasures": [
                    {"map": location_data_table[loc].str_id, "index": location_data_table[loc].secondary_index}
                    for loc in self.selected_treasures],
                "character_order": self.character_order,
                "allow_seitengrat": self.options.allow_seitengrat.value
            }
        }
        mod_name = self.multiworld.get_out_file_name_base(self.player)
        with open(os.path.join(output_directory, mod_name + ".json"), "w") as f:
            json.dump(data, f)

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "treasures": self.selected_treasures
        }
