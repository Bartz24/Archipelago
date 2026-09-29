from typing import Dict
from dataclasses import dataclass
from Options import Choice, Range, Toggle, PerGameCommonOptions, StartInventoryPool


class AllowSeitengrat(Toggle):
    """Allow Seitengrat to appear in the item pool and bazaars."""
    display_name = "Allow Seitengrat"
    default = 0


class ShuffleMainParty(Toggle):
    """Shuffle the 6 main party members around."""
    display_name = "Shuffle Main Party"
    default = 1


class ProgressiveScaling(Toggle):
    """In addition to the progression scaling, also scale the progression based on the number of party members, 
    the second license board has been unlocked, and progressive access to slightly easier regions to unlock more difficult areas."""
    display_name = "Difficulty Progressive Scaling"
    default = 1


class IncludeTreasures(Toggle):
    """Allows treasures to contain progression and useful items."""
    display_name = "Treasures"
    default = 0


class TreasureCount(Range):
    """How many of the game's 1581 treasures become checks.
    Treasures are picked at random, and the ones not picked are emptied.
    Every treasure is one time only, so the count is not limited by the game's
    256 respawn ids: the mod banks them per map."""
    display_name = "Treasure Count"
    range_start = 0
    range_end = 1581
    default = 255


class IncludeChops(Toggle):
    """Allows pinewood chops and sandalwood chop checks to contain progression and useful items.
    Note: The Bahamut Unlock Goal for collecting pinewood chops will still
    require the player to collect the 28 chops for the Writ of Transit."""
    display_name = "Chops"
    default = 0


class IncludeBlackOrbs(Toggle):
    """Allows Pharos floor 1 and Subterra black orb checks to contain progression and useful items."""
    display_name = "Black Orbs"
    default = 0


class IncludeTrophyRareGames(Toggle):
    """Allows trophy rare game checks to contain progression and useful items.
    Includes: Rare Game drops and Number of Rare Game Killed checks."""
    display_name = "Trophy Rare Games"
    default = 0


class IncludeHuntRewards(Toggle):
    """Allows Hunt rewards and drops to contain progression and useful items."""
    display_name = "Hunt Rewards and Drops"
    default = 0


class IncludeClanHallRewards(Toggle):
    """Allows Clan Hall rewards to contain progression and useful items."""
    display_name = "Clan Hall Rewards"
    default = 0


class MaxTrialStage(Range):
    """The highest Trial Mode stage whose rewards can contain progression and useful items.
    Rewards for later stages only get filler, so the trials can be stopped at this stage without
    missing anything. Stages come in steps of 10; values in between round down.
    0 excludes every trial reward, 100 includes them all."""
    display_name = "Highest Trial Stage with Important Rewards"
    range_start = 0
    range_end = 100
    default = 100


class BahamutUnlock(Choice):
    """Determines where the Writ of Transit is placed to unlock travel to the Bahamut to beat the game.
    Defeat Cid 2: Climb the Pharos and defeat Cid 2 (Requires 2 magicites and 1 story sword).
    Collect Pinewood Chops: Collect 28 pinewood chops from the multiworld and turn in for the Sandalwood Chop check.
    Collect Espers: Collect all 13 espers and turn in for the Clan Hall Control 13 Espers check.
    Defeat Shadowseer: Defeat the Shadowseer in the Pharos and turn in for the Hunt 44: Shadowseer check.
    Defeat Yiazmat: Defeat Yiazmat in Ridorana and turn in for the Hunt 45: Yiazmat check.
    Defeat Omega: Defeat Omega Mark XII in the Great Crystal and turn in for the Clan Boss: Omega Mark XII check.
    Random Location: The Writ of Transit can be anywhere in the multiworld."""
    display_name = "Bahamut Unlock Goal"
    option_defeat_cid_2 = 0
    option_collect_pinewood_chops = 1
    option_collect_espers = 2
    option_defeat_shadowseer = 3
    option_defeat_yiazmat = 4
    option_defeat_omega = 5
    option_random_location = 6
    default = 0


@dataclass
class FF12OpenWorldGameOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    shuffle_main_party: ShuffleMainParty
    difficulty_progressive_scaling: ProgressiveScaling
    include_treasures: IncludeTreasures
    treasure_count: TreasureCount
    include_chops: IncludeChops
    include_black_orbs: IncludeBlackOrbs
    include_trophy_rare_games: IncludeTrophyRareGames
    include_hunt_rewards: IncludeHuntRewards
    include_clan_hall_rewards: IncludeClanHallRewards
    max_trial_stage: MaxTrialStage
    allow_seitengrat: AllowSeitengrat
    bahamut_unlock: BahamutUnlock
