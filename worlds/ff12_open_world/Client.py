import time
from typing import List

import ModuleUpdate

ModuleUpdate.update()

import os
import asyncio
import json
from pymem import pymem

from NetUtils import ClientStatus, NetworkItem
from CommonClient import gui_enabled, logger, get_base_parser, CommonContext, server_loop

from .Items import FF12OW_BASE_ID, item_data_table, inv_item_table
from .Locations import location_data_table, FF12OpenWorldLocationData


# Copied from KH2 Client
class FF12OpenWorldContext(CommonContext):
    # command_processor: int = FF12OpenWorldCommandProcessor
    game = "Final Fantasy 12 Open World"
    items_handling = 0b111  # Indicates you get items sent from other worlds.

    def __init__(self, server_address, password):
        super(FF12OpenWorldContext, self).__init__(server_address, password)

        self.debug_time = None
        self.ff12_items_received: List[NetworkItem] = []
        self.prev_map_and_time = None
        self.sending = None
        self.ff12slotdata = None
        self.ff12_seed_save = None
        self.ff12seedname = None
        self.server_connected = False
        self.ff12connected = False
        if "localappdata" in os.environ:
            self.game_communication_path = os.path.expandvars(r"%localappdata%\FF12OWAP")
        # hooked object
        self.ff12 = None

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(FF12OpenWorldContext, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    async def connection_closed(self):
        self.ff12connected = False
        self.server_connected = False
        if self.ff12seedname is not None and self.auth is not None:
            with open(self.get_save_path(),
                      'w') as f:
                f.write(json.dumps(self.ff12_seed_save, indent=4))
        await super(FF12OpenWorldContext, self).connection_closed()

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.ff12connected = False
        self.server_connected = False
        if self.ff12seedname not in {None} and self.auth not in {None}:
            with open(self.get_save_path(),
                      'w') as f:
                f.write(json.dumps(self.ff12_seed_save, indent=4))
        await super(FF12OpenWorldContext, self).disconnect()

    @property
    def endpoints(self):
        if self.server:
            return [self.server]
        else:
            return []

    async def shutdown(self):
        if self.ff12seedname not in {None} and self.auth not in {None}:
            with open(self.get_save_path(),
                      'w') as f:
                f.write(json.dumps(self.ff12_seed_save, indent=4))
        await super(FF12OpenWorldContext, self).shutdown()

    def ff12_story_address(self):
        return self.ff12.base_address

    def ff12_write_byte(self, address, value):
        return self.ff12.write_bytes(self.ff12.base_address + address, value.to_bytes(1, "little"), 1)

    def ff12_read_byte(self, address, use_base=True):
        if use_base:
            return int.from_bytes(self.ff12.read_bytes(self.ff12.base_address + address, 1), "little")
        else:
            return int.from_bytes(self.ff12.read_bytes(address, 1), "little")

    def ff12_read_bit(self, address, bit, use_base=True) -> bool:
        return (self.ff12_read_byte(address, use_base) >> bit) & 1 == 1

    def ff12_read_short(self, address, use_base=True):
        if use_base:
            return int.from_bytes(self.ff12.read_bytes(self.ff12.base_address + address, 2), "little")
        else:
            return int.from_bytes(self.ff12.read_bytes(address, 2), "little")

    def ff12_write_short(self, address, value, use_base=True):
        if use_base:
            return self.ff12.write_bytes(self.ff12.base_address + address, value.to_bytes(2, "little"), 2)
        else:
            return self.ff12.write_bytes(address, value.to_bytes(2, "little"), 2)

    def ff12_read_int(self, address, use_base=True):
        if use_base:
            return int.from_bytes(self.ff12.read_bytes(self.ff12.base_address + address, 4), "little")
        else:
            return int.from_bytes(self.ff12.read_bytes(address, 4), "little")

    def ff12_write_int(self, address, value, use_base=True):
        if use_base:
            return self.ff12.write_bytes(self.ff12.base_address + address, value.to_bytes(4, "little"), 4)
        else:
            return self.ff12.write_bytes(address, value.to_bytes(4, "little"), 4)

    def on_package(self, cmd: str, args: dict):
        if cmd in {"RoomInfo"}:
            self.ff12seedname = args['seed_name']
            if not os.path.exists(self.game_communication_path):
                os.makedirs(self.game_communication_path)
            if not os.path.exists(self.get_save_path()):
                self.ff12_seed_save = {
                }
                with open(self.get_save_path(),
                          'wt') as f:
                    pass
                # self.locations_checked = set()
            elif os.path.exists(self.get_save_path()):
                with open(self.get_save_path(), 'r') as f:
                    self.ff12_seed_save = json.load(f)
                    if self.ff12_seed_save is None:
                        self.ff12_seed_save = {
                        }
                    # self.locations_checked = set(self.kh2_seed_save_cache["LocationsChecked"])
            # self.serverconneced = True

        if cmd in {"Connected"}:
            asyncio.create_task(self.send_msgs([{"cmd": "GetDataPackage", "games": ["Final Fantasy 12 Open World"]}]))
            self.ff12slotdata = args['slot_data']
            self.locations_checked = set(args["checked_locations"])

        if cmd in {"ReceivedItems"}:
            self.find_game()
            if self.server_connected:
                # Get the items past the start index in args items
                for index, item in enumerate(args["items"], start=args["index"]):
                    if index >= len(self.ff12_items_received):
                        self.ff12_items_received.append(item)
                    else:
                        self.ff12_items_received[index] = item

        if cmd in {"RoomUpdate"}:
            if "checked_locations" in args:
                new_locations = set(args["checked_locations"])
                self.locations_checked |= new_locations

        if cmd in {"DataPackage"}:
            self.find_game()
            self.server_connected = True
            asyncio.create_task(self.send_msgs([{'cmd': 'Sync'}]))

    def find_game(self):
        if not self.ff12connected:
            try:
                self.ff12 = pymem.Pymem(process_name="FFXII_TZA")
                logger.info("You are now auto-tracking")
                self.ff12connected = True
            except Exception as e:
                if self.ff12connected:
                    self.ff12connected = False
                logger.info("Game is not open (Try running the client as an admin).")
                logger.info(e)

    def get_save_path(self) -> str:
        return os.path.join(self.game_communication_path, f"ff12save{self.ff12seedname}{self.auth}.json")

    def get_current_map(self) -> int:
        return self.ff12_read_short(0x20454C4)

    def is_in_game(self) -> bool:
        # Check if the game has been on this map for more than 5 seconds
        self.prev_map_and_time = self.prev_map_and_time or (self.get_current_map(), time.time())

        if self.prev_map_and_time[0] != self.get_current_map() or self.get_current_map() <= 12:
            self.prev_map_and_time = (self.get_current_map(), time.time())
            return False
        else:
            return time.time() - self.prev_map_and_time[1] > 5

    def get_current_game_state(self) -> int:
        # 0 - Field
        # 1 - Dialog/Cutscene
        # 4 - Menu
        # 5 - Load Screen
        pointer1 = self.ff12_read_int(0x01E5FFE0)
        return self.ff12_read_byte(pointer1 + 0x3A, False)

    def get_party_address(self) -> int:
        return self.ff12_read_int(0x02D9F190) + 0x08

    def get_save_data_address(self) -> int:
        return self.ff12.base_address + 0x02044480

    def get_scenario_flag(self) -> int:
        return self.ff12_read_short(0x02044480)

    def get_item_index(self) -> int:
        return self.ff12_read_int(self.get_save_data_address() + 0x696, use_base=False)

    def set_item_index(self, index):
        self.ff12_write_int(self.get_save_data_address() + 0x696, index, use_base=False)

    def get_item_add_id(self) -> int:
        return self.ff12_read_short(self.get_save_data_address() + 0x69A, use_base=False)

    def get_item_add_count(self) -> int:
        return self.ff12_read_int(self.get_save_data_address() + 0x69C, use_base=False)

    def set_item_add_id(self, item_id: int) -> None:
        if item_id >= FF12OW_BASE_ID + 98304:  # Gil
            self.ff12_write_short(self.get_save_data_address() + 0x69A,
                                  0xFFFE, use_base=False)
        else:
            self.ff12_write_short(self.get_save_data_address() + 0x69A,
                                  item_id - FF12OW_BASE_ID, use_base=False)

    def set_item_add_count(self, count: int) -> None:
        self.ff12_write_int(self.get_save_data_address() + 0x69C, count, use_base=False)

    def is_chara_in_party(self, chara) -> bool:
        return self.ff12_read_bit(self.get_party_address() + chara * 0x1C8, 4, False)

    def get_item_count_received(self, item_name: str) -> int:
        return len([item for item in self.ff12_items_received[:self.get_item_index()] if
                    item.item == item_data_table[item_name].code])

    def has_item_received(self, item_name: str) -> bool:
        return self.get_item_count_received(item_name) > 0

    def get_item_count(self, item_name: str) -> int:
        int_id = item_data_table[item_name].code - FF12OW_BASE_ID
        if int_id < 0x1000:  # Normal items
            return self.ff12_read_short(0x02097054 + int_id * 2)
        elif 0x2000 <= int_id < 0x3000:  # Loot items
            return self.ff12_read_short(0x0209741C + (int_id - 0x2000) * 2)
        elif 0x8000 <= int_id < 0x9000:  # Key items
            byte_index = (int_id - 0x8000) // 8
            bit_index = (int_id - 0x8000) % 8
            return 1 if self.ff12_read_bit(0x02097054 + 0x7F8 + byte_index, bit_index) else 0
        else:
            return 0

    def has_item_in_game(self, item_name: str) -> bool:
        return self.get_item_count(item_name) > 0

    def get_leviathan_progress(self) -> int:
        # Check if currently in Leviathan
        if 0x37A <= self.get_scenario_flag() <= 0x44C:
            return self.get_scenario_flag()

        # Otherwise use the stored flag
        lev_flag = self.ff12_read_short(self.get_save_data_address() + 0xDFF7, False)
        if lev_flag > 10000:  # Used the 2nd checkpoint
            return lev_flag - 10000
        elif lev_flag == 0:  # Not yet started
            return 0
        else:  # Used the 1st checkpoint
            return lev_flag

    def get_escape_progress(self) -> int:
        esc_flag = self.ff12_read_short(self.get_save_data_address() + 0xDFF4, False)

        # Check if stored progress is after beating Mimic Queen
        if self.ff12_read_byte(self.get_save_data_address() + 0xA04, False) >= 2:
            return 0x208  # Close to beating mimic queen
        # Check if currently in the escape sequence after beating Firemane
        elif 0x11D < self.get_scenario_flag() < 0x208:
            return self.get_scenario_flag()
        # Check if the stored progress in the escape sequence after beating Firemane
        elif 0x11D < esc_flag < 0x208:
            return esc_flag
        # Check if stored progress is after beating Firemane
        elif self.ff12_read_byte(self.get_save_data_address() + 0xA06, False) >= 2:
            return 0x11D  # Close to beating Firemane
        # Check if currently in the escape sequence before beating Firemane
        elif 6110 < self.get_scenario_flag() <= 6110 + 70:
            return self.get_scenario_flag() - 6110
        # Check if the stored progress in the escape sequence before beating Firemane
        elif 6110 < esc_flag <= 6110 + 70:
            return esc_flag - 6110
        else:
            return 0

    def get_draklor_progress(self) -> int:
        # Check if currently in Leviathan
        if 0xD48 <= self.get_scenario_flag() <= 0x1036:
            return self.get_scenario_flag()

        # Otherwise use the stored flag
        darklor_flag = self.ff12_read_short(self.get_save_data_address() + 0xDFF9, False)
        if darklor_flag == 0:  # Not yet started
            return 0
        else:
            return darklor_flag

    async def check_locations(self):
        try:
            # Do not check on main menu
            if not self.is_in_game():
                return
            for location_name, data in location_data_table.items():
                if location_name in self.locations_checked:
                    continue
                elif data.type == "inventory":
                    if self.is_chara_in_party(int(data.str_id)):
                        self.sending.append(data.address)
                elif data.type == "reward":
                    if self.is_reward_met(location_name, data):
                        self.sending.append(data.address)
                elif data.type == "treasure":
                    treasures: list[str] = self.ff12slotdata["treasures"]
                    if location_name not in treasures:
                        continue
                    treasure_index = treasures.index(location_name)
                    byte_index = treasure_index // 8
                    bit_index = treasure_index % 8
                    if self.ff12_read_bit(self.get_save_data_address() + 0x14B4 + byte_index, bit_index, False):
                        self.sending.append(data.address)

            # Victory, Final Boss
            if self.ff12_read_byte(self.get_save_data_address() + 0xA2E, False) >= 2 \
                    and not self.finished_game:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                self.finished_game = True

        except Exception as e:
            if self.ff12connected:
                self.ff12connected = False
            logger.info(e)

    def is_reward_met(self, location_name: str, location_data: FF12OpenWorldLocationData):
        if location_data.str_id == "9000" or \
                location_data.str_id == "916B" or \
                location_data.str_id == "916C":  # Tomaj Checks
            return self.get_scenario_flag() >= 6110
        elif location_data.str_id == "9002":  # Shadestone check
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 0, False)
        elif location_data.str_id == "9001":  # Sunstone check (if received Shadestone but the item is lost)
            return self.has_item_received("Shadestone") and not self.has_item_in_game("Shadestone")
        elif location_data.str_id == "905E":  # Crescent Stone (if received Sunstone but the item is lost)
            return self.has_item_received("Sunstone") and not self.has_item_in_game("Sunstone")
        elif location_data.str_id == "905F":  # Dalan SotO
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 1, False)
        elif location_data.str_id == "911E":  # SotO turn in
            return self.has_item_received("Sword of the Order") and not self.has_item_in_game("Sword of the Order")
        elif location_data.str_id == "9060":  # Judges Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA27, False) >= 2
        elif location_data.str_id == "9061":  # Systems Access Key
            return self.ff12_read_bit(self.get_save_data_address() + 0x14D4 + 4, 0, False)
        elif location_data.str_id == "912C":  # Manufacted Nethicite
            return self.get_leviathan_progress() >= 0x3E8
        elif location_data.str_id == "912D":  # Eksir Berries
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 2, False)
        elif location_data.str_id == "9190":  # Belias Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA19, False) >= 2
        elif location_data.str_id == "912E":  # Dawn Shard
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 3, False)
        elif location_data.str_id == "918E":  # Vossler Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA3B, False) >= 2
        elif location_data.str_id == "912F":  # Goddess's Magicite
            return self.get_escape_progress() >= 15
        elif location_data.str_id == "9130":  # Tube Fuse
            return self.get_escape_progress() >= 0x13F
        elif location_data.str_id == "911F":  # Garif Reward
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 4, False)
        elif location_data.str_id == "9131":  # Lente's Tear (Tiamat Boss)
            return self.ff12_read_byte(self.get_save_data_address() + 0xA08, False) >= 2
        elif location_data.str_id == "9191":  # Mateus Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA21, False) >= 2
        elif location_data.str_id == "9132":  # Sword of Kings
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 6, False)
        elif location_data.str_id == "9133":  # Start Mandragoras
            # Kid or Dad
            return self.ff12_read_byte(self.get_save_data_address() + 0x684, False) == 1 or \
                self.ff12_read_byte(self.get_save_data_address() + 0x681, False) == 1
        elif location_data.str_id == "9052":  # Turn in Mandragoras
            return self.ff12_read_byte(self.get_save_data_address() + 0x683, False) == 1
        elif location_data.str_id == "918D":  # Cid 1 Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA29, False) >= 2
        elif 0x9134 <= int(location_data.str_id, 16) <= 0x914F:  # Pinewood Chops
            return (self.ff12_read_byte(self.get_save_data_address() + 0xDFF6, False) >
                    int(location_data.str_id, 16) - 0x9134)
        elif location_data.str_id == "9150":  # Sandalwood Chop
            return self.ff12_read_bit(self.get_save_data_address() + 0xA42, 7, False)
        elif location_data.str_id == "9151":  # Lab Access Card
            return self.get_draklor_progress() >= 0xD48
        elif location_data.str_id == "9192":  # Shemhazai Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA20, False) >= 2
        elif location_data.str_id == "9152":  # Treaty Blade
            return self.ff12_read_bit(self.get_save_data_address() + 0xDFFB, 0, False)
        elif 0x9153 <= int(location_data.str_id, 16) <= 0x916A:  # Black Orbs
            return (self.ff12_read_byte(self.get_save_data_address() + 0xDFFC, False) >
                    int(location_data.str_id, 16) - 0x9153)
        elif location_data.str_id == "9003":  # Hunt 1
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 0, False) >= 70
        elif location_data.str_id == "9004":  # Hunt 2
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 1, False) >= 70
        elif location_data.str_id == "9005":  # Hunt 3
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 2, False) >= 90
        elif location_data.str_id == "9006":  # Hunt 4
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 3, False) >= 100
        elif location_data.str_id == "9007":  # Hunt 5
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 4, False) >= 90
        elif location_data.str_id == "9008":  # Hunt 6
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 5, False) >= 100
        elif location_data.str_id == "9009":  # Hunt 7
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 6, False) >= 100
        elif location_data.str_id == "900A":  # Hunt 8
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 7, False) >= 100
        elif location_data.str_id == "900B":  # Hunt 9
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 8, False) >= 100
        elif location_data.str_id == "900C":  # Hunt 10
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 9, False) >= 100
        elif location_data.str_id == "900D":  # Hunt 11
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 10, False) >= 100
        elif location_data.str_id == "900E":  # Hunt 12
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 11, False) >= 100
        elif location_data.str_id == "900F":  # Hunt 13
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 12, False) >= 90
        elif location_data.str_id == "9010":  # Hunt 14
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 13, False) >= 100
        elif location_data.str_id == "9011":  # Hunt 15
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 14, False) >= 100
        elif location_data.str_id == "9012":  # Hunt 16
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 15, False) >= 90
        elif location_data.str_id == "9013":  # Hunt 17
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 16, False) >= 50
        elif location_data.str_id == "9014":  # Hunt 18
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 17, False) >= 50
        elif location_data.str_id == "9015":  # Hunt 19
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 18, False) >= 100
        elif location_data.str_id == "9016":  # Hunt 20
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 19, False) >= 150
        elif location_data.str_id == "9017":  # Hunt 21
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 20, False) >= 150
        elif location_data.str_id == "9018":  # Hunt 22
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 21, False) >= 150
        elif location_data.str_id == "9019":  # Hunt 23
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 22, False) >= 150
        elif location_data.str_id == "901A":  # Hunt 24
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 23, False) >= 50
        elif location_data.str_id == "901B":  # Hunt 25
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 24, False) >= 50
        elif location_data.str_id == "901C":  # Hunt 26
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 25, False) >= 90
        elif location_data.str_id == "901D":  # Hunt 27
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 26, False) >= 90
        elif location_data.str_id == "901E":  # Hunt 28
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 27, False) >= 90
        elif location_data.str_id == "901F":  # Hunt 29
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 28, False) >= 100
        elif location_data.str_id == "9020":  # Hunt 30
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 29, False) >= 100
        elif location_data.str_id == "9021":  # Hunt 31
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 30, False) >= 90
        elif location_data.str_id == "9022":  # Hunt 32
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 31, False) >= 150
        elif location_data.str_id == "9023":  # Hunt 33
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 32, False) >= 100
        elif location_data.str_id == "9024":  # Hunt 34
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 33, False) >= 90
        elif location_data.str_id == "9025":  # Hunt 35
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 34, False) >= 100
        elif location_data.str_id == "9026":  # Hunt 36
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 35, False) >= 100
        elif location_data.str_id == "9027":  # Hunt 37
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 36, False) >= 90
        elif location_data.str_id == "9028":  # Hunt 38
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 37, False) >= 110
        elif location_data.str_id == "9029":  # Hunt 39
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 38, False) >= 50
        elif location_data.str_id == "902A":  # Hunt 40
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 39, False) >= 130
        elif location_data.str_id == "902B":  # Hunt 42
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 40, False) >= 100
        elif location_data.str_id == "902C":  # Hunt 43
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 41, False) >= 150
        elif location_data.str_id == "902D":  # Hunt 44
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 42, False) >= 100
        elif location_data.str_id == "902E":  # Hunt 45
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 43, False) >= 100
        elif location_data.str_id == "9112":  # Hunt 41
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 128 + 44, False) >= 100
        elif 0x902F <= int(location_data.str_id, 16) <= 0x903A:  # Clan Rank Rewards
            return (self.ff12_read_byte(self.get_save_data_address() + 0x418, False) >
                    int(location_data.str_id, 16) - 0x902F)
        elif location_data.str_id == "903B":  # Clan Boss Flans
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 0, False)
        elif location_data.str_id == "903C":  # Clan Boss Firemane
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 1, False)
        elif location_data.str_id == "903D":  # Clan Boss Earth Tyrant
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 2, False)
        elif location_data.str_id == "903E":  # Clan Boss Mimic Queen
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 3, False)
        elif location_data.str_id == "903F":  # Clan Boss Demon Wall 1
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 4, False)
        elif location_data.str_id == "9040":  # Clan Boss Demon Wall 2
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 5, False)
        elif location_data.str_id == "9041":  # Clan Boss Elder Wyrm
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 6, False)
        elif location_data.str_id == "9042":  # Clan Boss Tiamat
            return self.ff12_read_bit(self.get_save_data_address() + 0x419, 7, False)
        elif location_data.str_id == "9043":  # Clan Boss Vinuskar
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 0, False)
        elif location_data.str_id == "9044":  # Clan Boss King Bomb
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 1, False)
        elif location_data.str_id == "9045":  # Clan Boss Mandragoras
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 3, False)
        elif location_data.str_id == "9046":  # Clan Boss Ahriman
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 2, False)
        elif location_data.str_id == "9047":  # Clan Boss Hell Wyrm
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 4, False)
        elif location_data.str_id == "9048":  # Clan Boss Rafflesia
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 5, False)
        elif location_data.str_id == "9049":  # Clan Boss Daedalus
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 6, False)
        elif location_data.str_id == "904A":  # Clan Boss Tyrant
            return self.ff12_read_bit(self.get_save_data_address() + 0x41A, 7, False)
        elif location_data.str_id == "904B":  # Clan Boss Hydro
            return self.ff12_read_bit(self.get_save_data_address() + 0x41B, 0, False)
        elif location_data.str_id == "904C":  # Clan Boss Humbaba Mistant
            return self.ff12_read_bit(self.get_save_data_address() + 0x41B, 1, False)
        elif location_data.str_id == "904D":  # Clan Boss Fury
            return self.ff12_read_bit(self.get_save_data_address() + 0x41B, 2, False)
        elif location_data.str_id == "905A":  # Clan Boss Omega Mark XII
            return self.ff12_read_bit(self.get_save_data_address() + 0x41B, 3, False)
        elif 0x904E <= int(location_data.str_id, 16) <= 0x9051:  # Clan Espers (1,4,8,13)
            return (self.ff12_read_byte(self.get_save_data_address() + 0x41C, False) >
                    int(location_data.str_id, 16) - 0x904E)
        elif location_data.str_id == "916D":  # Flowering Cactoid Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 130, False) >= 70
        elif location_data.str_id == "916E":  # Barheim Key
            return self.ff12_read_byte(self.get_save_data_address() + 0x68B, False) >= 11
        elif location_data.str_id == "9081":  # Deliver Cactus Flower
            return self.ff12_read_byte(self.get_save_data_address() + 0x68B, False) >= 3
        elif location_data.str_id == "908A":  # Cactus Family
            return self.ff12_read_byte(self.get_save_data_address() + 0x686, False) >= 7
        elif location_data.str_id == "916F":  # Get Stone of the Condemner
            return self.ff12_read_byte(self.get_save_data_address() + 0x680, False) >= 1
        elif location_data.str_id == "9170":  # Get Wind Globe
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 53, False) >= 50
        elif location_data.str_id == "9171":  # Get Windvane
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 53, False) >= 60
        elif location_data.str_id == "9172":  # White Mousse Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 133, False) >= 50
        elif location_data.str_id == "9173":  # Sluice Gate Key
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 133, False) >= 120
        elif location_data.str_id == "9174":  # Enkelados Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 137, False) >= 50
        elif location_data.str_id == "9062":  # Give Errmonea Leaf
            return self.ff12_read_byte(self.get_save_data_address() + 0x4AE, False) >= 1
        elif location_data.str_id == "9175":  # Merchant's Armband
            return self.ff12_read_byte(self.get_save_data_address() + 0x6FD, False) >= 2
        elif location_data.str_id == "9176":  # Get Pilika's Diary
            return self.ff12_read_byte(self.get_save_data_address() + 0x6FD, False) >= 3
        elif location_data.str_id == "908D":  # Give Pilika's Diary
            return self.ff12_read_byte(self.get_save_data_address() + 0x6FD, False) >= 4
        elif location_data.str_id == "9177":  # Vorpal Bunny Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 141, False) >= 50
        elif location_data.str_id == "9178":  # Croakadile Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 138, False) >= 50
        elif location_data.str_id == "9179":  # Lindwyrm Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 149, False) >= 100
        elif location_data.str_id == "917A":  # Get Silent Urn
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 163, False) >= 50
        elif location_data.str_id == "917B":  # Orthros Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 162, False) >= 70
        elif location_data.str_id == "917D":  # Site 3 Key
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 165, False) >= 50
        elif location_data.str_id == "917E":  # Site 11 Key
            return self.ff12_read_bit(self.get_save_data_address() + 0xDFFB, 2, False)
        elif location_data.str_id == "917F":  # Fafnir Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 158, False) >= 70
        elif location_data.str_id == "9180":  # Marilith Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 136, False) >= 70
        elif location_data.str_id == "9181":  # Vyraal Drop
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 148, False) >= 100
        elif location_data.str_id == "9182":  # Dragon Scale
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 148, False) >= 150
        elif location_data.str_id == "9183":  # Ageworn Key check (if received Dragon Scale but the item is lost)
            return self.has_item_received("Dragon Scale") and not self.has_item_in_game("Dragon Scale")
        elif location_data.str_id == "9184":  # Ann's Letter
            return self.ff12_read_byte(self.get_save_data_address() + 0x5A6, False) >= 1
        elif location_data.str_id == "906C":  # Ann's Sisters
            return self.ff12_read_byte(self.get_save_data_address() + 0x5A6, False) >= 7
        elif location_data.str_id == "9185":  # Dusty Letter
            return self.ff12_read_bit(self.get_save_data_address() + 0x423, 2, False)
        elif location_data.str_id == "917C":  # Blackened Fragment
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 162, False) >= 100
        elif location_data.str_id == "9186":  # Dull Fragment
            return self.ff12_read_bit(self.get_save_data_address() + 0x423, 1, False)
        elif location_data.str_id == "9187":  # Grimy Fragment
            return self.ff12_read_byte(self.get_save_data_address() + 0x416, False) >= 7
        elif location_data.str_id == "9188":  # Moonsilver Medallion
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 59, False) >= 20
        elif location_data.str_id == "9189" or \
                location_data.str_id == "918A" or \
                location_data.str_id == "918B":  # Nabreus Medallions
            return self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 57, False) >= 100
        elif location_data.str_id == "918C":  # Medallion of Might (Humbaba Mistant and Fury bosses)
            return self.ff12_read_byte(self.get_save_data_address() + 0xA0F, False) >= 2 and \
                self.ff12_read_byte(self.get_save_data_address() + 0xA10, False) >= 2
        elif location_data.str_id == "9056":  # Viera Rendevous
            return self.ff12_read_byte(self.get_save_data_address() + 0x40E, False) >= 6
        elif location_data.str_id == "9058":  # Ktjn Reward
            return self.ff12_read_bit(self.get_save_data_address() + 0x409, 0, False)
        elif location_data.str_id == "906A":  # Jovy Reward
            return self.ff12_read_byte(self.get_save_data_address() + 0x5B8, False) >= 6
        elif location_data.str_id == "906E":  # Outpost Glint 1
            return self.ff12_read_byte(self.get_save_data_address() + 0x691, False) >= 1
        elif location_data.str_id == "906F":  # Outpost Glint 2
            return self.ff12_read_byte(self.get_save_data_address() + 0x692, False) >= 1
        elif location_data.str_id == "9057":  # Outpost Glint 3
            return self.ff12_read_byte(self.get_save_data_address() + 0x693, False) >= 1
        elif location_data.str_id == "9070":  # Outpost Glint 4
            return self.ff12_read_byte(self.get_save_data_address() + 0x694, False) >= 1
        elif location_data.str_id == "9059":  # Outpost Glint 5
            return self.ff12_read_byte(self.get_save_data_address() + 0x695, False) >= 1
        elif location_data.str_id == "908F":  # Footrace
            return self.ff12_read_byte(self.get_save_data_address() + 0x73C, False) >= 1
        elif location_data.str_id == "9194":  # Adrammelech Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA25, False) >= 2
        elif location_data.str_id == "9195":  # Zalera Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA1D, False) >= 2
        elif location_data.str_id == "9196":  # Cuchulainn Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA1C, False) >= 2
        elif location_data.str_id == "9197":  # Zeromus Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA22, False) >= 2
        elif location_data.str_id == "9198":  # Exodus Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA23, False) >= 2
        elif location_data.str_id == "9199":  # Chaos Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA1A, False) >= 2
        elif location_data.str_id == "919A":  # Ultima Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA24, False) >= 2
        elif location_data.str_id == "919B":  # Zodiark Boss
            return self.ff12_read_byte(self.get_save_data_address() + 0xA1B, False) >= 2
        elif 0x9090 <= int(location_data.str_id, 16) <= 0x90AE:  # Trophy Drops
            trophy_index = int(location_data.str_id, 16) - 0x9090
            return self.ff12_read_byte(self.get_save_data_address() + 0xC90 + trophy_index, False) >= 2
        elif 0x90F9 <= int(location_data.str_id, 16) <= 0x90FE:  # Rare Game Defeats (5,10,15,20,25,30)
            return self.ff12_read_byte(self.get_save_data_address() + 0x725, False) > \
                (int(location_data.str_id, 16) - 0x90F9) + 1
        elif location_data.str_id == "90F3":  # Atak >=16
            if self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 71, False) < 170:
                return False
            max_trophies = self.get_max_trophies()
            return self.ff12_read_byte(self.get_save_data_address() + 0xb14, False) == max_trophies and \
                max_trophies >= 16
        elif location_data.str_id == "90F4":  # Atak <16
            if self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 71, False) < 170:
                return False
            max_trophies = self.get_max_trophies()
            return self.ff12_read_byte(self.get_save_data_address() + 0xb14, False) == max_trophies and \
                max_trophies < 16
        elif location_data.str_id == "90F5":  # Blok >=16
            if self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 71, False) < 170:
                return False
            max_trophies = self.get_max_trophies()
            return self.ff12_read_byte(self.get_save_data_address() + 0xb15, False) == max_trophies and \
                max_trophies >= 16
        elif location_data.str_id == "90F6":  # Blok <16
            if self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 71, False) < 170:
                return False
            max_trophies = self.get_max_trophies()
            return self.ff12_read_byte(self.get_save_data_address() + 0xb15, False) == max_trophies and \
                max_trophies < 16
        elif location_data.str_id == "90F7":  # Stok >=16
            if self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 71, False) < 170:
                return False
            max_trophies = self.get_max_trophies()
            return self.ff12_read_byte(self.get_save_data_address() + 0xb16, False) == max_trophies and \
                max_trophies >= 16
        elif location_data.str_id == "90F8":  # Stok <16
            if self.ff12_read_byte(self.get_save_data_address() + 0x1064 + 71, False) < 170:
                return False
            max_trophies = self.get_max_trophies()
            return self.ff12_read_byte(self.get_save_data_address() + 0xb16, False) == max_trophies and \
                max_trophies < 16
        elif 0x90FF <= int(location_data.str_id, 16) <= 0x911D:  # Hunt Club Outfitters
            outfitter_index = int(location_data.str_id, 16) - 0x90FF
            return self.ff12_read_byte(self.get_save_data_address() + 0xAF2 + outfitter_index, False) >= 1

    def get_max_trophies(self):
        return max(
            self.ff12_read_byte(self.get_save_data_address() + 0xb14, False),
            self.ff12_read_byte(self.get_save_data_address() + 0xb15, False),
            self.ff12_read_byte(self.get_save_data_address() + 0xb16, False))

    async def give_items(self):
        try:
            start_index = self.get_item_index()
            for index in range(start_index, len(self.ff12_items_received)):
                if not self.is_in_game() or self.get_current_game_state() != 0:
                    return
                item = self.ff12_items_received[index]

                self.set_item_add_id(item.item)
                self.set_item_add_count(item_data_table[inv_item_table[item.item]].amount)
                start_time = time.time()
                # If it takes more than 10 seconds, error out
                while time.time() - start_time < 10:
                    if self.get_item_add_id() == 0xFFFF and self.get_item_add_count() == 0:
                        break
                    await asyncio.sleep(0.1)
                if self.get_item_add_id() != 0xFFFF:
                    raise Exception("Failed to give item in time. The lua script may be missing.")
                # Sleep 200 ms
                await asyncio.sleep(0.2)
        except Exception as e:
            if self.ff12connected:
                self.ff12connected = False
            logger.info(e)

    async def debug_info(self):
        self.debug_time = self.debug_time or time.time()
        if time.time() - self.debug_time < 5:
            return
        self.debug_time = time.time()
        try:
            logger.info("Current Map ID: " + str(self.get_current_map()))
            logger.info("Current State: " + str(self.get_current_game_state()))
            logger.info("Party: " + str([c for c in range(6) if self.is_chara_in_party(c)]))
            logger.info("Items: " + str(
                [item + ": " + str(self.get_item_count(item)) for item in item_data_table.keys() if
                 self.has_item_in_game(item)]))
            pass
        except Exception as e:
            if self.ff12connected:
                self.ff12connected = False
            logger.info(e)

    def run_gui(self):
        """Import kivy UI system and start running it as self.ui_task."""
        from kvui import GameManager

        class FF12OpenWorldManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago")
            ]
            base_title = "Archipelago FF12 Open World Client"

        self.ui = FF12OpenWorldManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


async def ff12_watcher(ctx: FF12OpenWorldContext):
    while not ctx.exit_event.is_set():
        try:
            if ctx.ff12connected and ctx.server_connected:
                ctx.sending = []
                #await asyncio.create_task(ctx.debug_info())
                await asyncio.create_task(ctx.check_locations())
                await asyncio.create_task(ctx.give_items())
                message = [{"cmd": 'LocationChecks', "locations": ctx.sending}]
                await ctx.send_msgs(message)
            elif not ctx.ff12connected and ctx.server_connected:
                logger.info("Game Connection lost. waiting 15 seconds until trying to reconnect.")
                ctx.ff12 = None
                while not ctx.ff12connected and ctx.server_connected:
                    await asyncio.sleep(15)
                    ctx.find_game()
        except Exception as e:
            if ctx.ff12connected:
                ctx.ff12connected = False
            logger.info(e)
        await asyncio.sleep(0.5)


def launch():
    async def main(args):
        ctx = FF12OpenWorldContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        progression_watcher = asyncio.create_task(
            ff12_watcher(ctx), name="FF12ProgressionWatcher")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await progression_watcher

        await ctx.shutdown()

    import colorama

    parser = get_base_parser(description="FF12 Open World Client, for text interfacing.")

    args, rest = parser.parse_known_args()
    colorama.init()
    asyncio.run(main(args))
    colorama.deinit()
