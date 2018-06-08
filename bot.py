import random

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer

def is_idle_extractor(vg):
    return vg.name == "Extractor" and vg.assigned_harvesters == 0 and vg.is_mine

class MyBot(sc2.BotAI):
    def __init__(self):
        self.drone_counter = 0
        self.spawning_pool_started = False
        self.moved_workers_to_gas = False
        self.moved_workers_from_gas = False
        self.queeen_started = False
        self.mboost_started = False
        self.attack_wave_counter = 0
        self.adrenal_glands_started = False
        self.num_extractors = 0
        self.first_overlord_built = False
        self.has_lair = False
    
    async def setup_extractors(self):
        drone = self.workers.prefer_idle
        if drone.empty:
            print("no workers left to assign to extractor")
            return
        drone = drone.random

        idle_extractors = self.state.vespene_geyser.filter(is_idle_extractor)
        idle_extractors = idle_extractors.prefer_close_to(drone.position)
        if idle_extractors.exists:
            print("assigning worker to idle extractor")
            err = await self.do(drone.gather(idle_extractors.first))
            return

        available = self.state.vespene_geyser.filter(lambda vg: vg.name != "Extractor")
        if available.empty:
            print("no available geysers")
            return
        
        if not self.can_afford(EXTRACTOR):
            print("can't afford extractor")
            return

        if not self.has_lair and self.num_extractors > 0:
            print("no need for an extractor yet")
            return

        drone = self.workers.prefer_idle
        if drone.empty:
            print("no workers left to build")
            return
        drone = drone.random
        target = available.closest_to(drone.position)
        err = await self.do(drone.build(EXTRACTOR, target))
        if not err:
            print("built extractor at", target.position)
            self.num_extractors += 1
            print("ok")

    async def run_zerg_upgrade_logic(self):
        if self.vespene >= 100:
            sp = self.units(SPAWNINGPOOL).ready
            if sp.exists and self.minerals >= 100 and not self.mboost_started:
                await self.do(sp.first(RESEARCH_ZERGLINGMETABOLICBOOST))
                self.mboost_started = True

            hatcheries = self.units(HATCHERY).ready
            if self.mboost_started and not self.units(LAIR).exists and self.can_afford(UPGRADETOLAIR_LAIR):
                print("UPGRADING TO LAIR")
                self.has_lair = True
                await self.do(hatcheries.first(UPGRADETOLAIR_LAIR))

            lairs = self.units(LAIR).ready
            if self.mboost_started and lairs.exists and not self.units(HIVE).exists and self.can_afford(UPGRADETOHIVE_HIVE):
                print("UPGRADING TO HIVE")
                await self.do(lairs.first(UPGRADETOHIVE_HIVE))


            if self.vespene >= 200 and self.mboost_started and self.units(HIVE).ready.exists:
                if not self.adrenal_glands_started:
                    await self.do(sp.first(RESEARCH_ZERGLINGADRENALGLANDS))
                    self.adrenal_glands_started = True
                    print("UPGRADE ZERGLINGADRENALGLANDS")
                if not self.moved_workers_from_gas:
                    self.moved_workers_from_gas = True
                    for drone in self.workers:
                        m = self.state.mineral_field.closer_than(10, drone.position)
                        await self.do(drone.gather(m.random, queue=True))

    async def should_wait_for_spawning_pool(self):
        if self.spawning_pool_started:
            return False
        if self.can_afford(SPAWNINGPOOL):
            hatchery = self.units(HATCHERY).ready.first
            for d in range(8, 15):
                pos = hatchery.position.to2.towards(self.game_info.map_center, -d)
                if await self.can_place(SPAWNINGPOOL, pos):
                    drone = self.workers.closest_to(pos)
                    err = await self.do(drone.build(SPAWNINGPOOL, pos))
                    if not err:
                        self.spawning_pool_started = True
                        return False
                    else:
                        return True
        else:
            return True

    async def wait_for_overlord(self):
        larvae = self.units(LARVA)
        if self.first_overlord_built:
            return False
        if self.can_afford(OVERLORD) and larvae.exists:
            await self.do(larvae.random.train(OVERLORD))
            self.first_overlord_built = True
            return False
        return True

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send("(glhf)")

        if await self.should_wait_for_spawning_pool():
            return
        if await self.wait_for_overlord():
            return
        if iteration % 100 == 0 and self.attack_wave_counter >= 1:
            await self.setup_extractors()

        if not self.units(HATCHERY).ready.exists:
            for unit in self.workers | self.units(ZERGLING) | self.units(QUEEN):
                await self.do(unit.attack(self.enemy_start_locations[0]))
            return

        if self.units(HATCHERY).idle.exists:
            hatchery = self.units(HATCHERY).idle.first
        else:
            hatchery = self.units(HATCHERY).ready.first
        larvae = self.units(LARVA)

        target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position

        attack_wave_size = 18
        idle_zerglings = self.units(ZERGLING).idle
        attackers = []
        if self.attack_wave_counter == 0 and len(idle_zerglings) >= 6:
            print("sending first attack wave")
            attackers = idle_zerglings[0:6]
            self.attack_wave_counter += 1
        elif len(idle_zerglings) >= attack_wave_size:
            self.attack_wave_counter += 1
            print("sending attack wave ", self.attack_wave_counter)
            attackers = idle_zerglings

        for zl in attackers:
            await self.do(zl.attack(target))

        for queen in self.units(QUEEN).idle:
            abilities = await self.get_available_abilities(queen)
            if AbilityId.EFFECT_INJECTLARVA in abilities:
                await self.do(queen(EFFECT_INJECTLARVA, hatchery))

        if iteration % 60 == 0:
            await self.run_zerg_upgrade_logic()

        if self.supply_left < 2 and self.attack_wave_counter >= 1:
            if self.can_afford(OVERLORD) and larvae.exists:
                await self.do(larvae.random.train(OVERLORD))

        if self.attack_wave_counter >= 1 and len(self.units(DRONE)) < 16 and self.can_afford(DRONE) and larvae.exists:
            await self.do(larvae.random.train(DRONE))

        if self.units(SPAWNINGPOOL).ready.exists:
            if larvae.exists and self.can_afford(ZERGLING):
                await self.do(larvae.random.train(ZERGLING))

        if self.units(EXTRACTOR).ready.exists and not self.moved_workers_to_gas:
            self.moved_workers_to_gas = True
            extractor = self.units(EXTRACTOR).first
            for drone in self.workers.random_group_of(3):
                await self.do(drone.gather(extractor))

        if self.minerals > 500:
            for d in range(4, 15):
                pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                pos = pos.offset([0, random.choice([d, -d])])
                if await self.can_place(HATCHERY, pos):
                    self.spawning_pool_started = True
                    print("building hatchery at", pos)
                    await self.do(self.workers.random.build(HATCHERY, pos))
                    break

        if self.drone_counter < 3:
            if self.can_afford(DRONE):
                self.drone_counter += 1
                await self.do(larvae.random.train(DRONE))

        elif not self.queeen_started and self.units(SPAWNINGPOOL).ready.exists:
            if self.can_afford(QUEEN):
                r = await self.do(hatchery.train(QUEEN))
                if not r:
                    self.queeen_started = True

def main():
    sc2.run_game(sc2.maps.get("Abyssal Reef LE"), [
        Bot(Race.Zerg, MyBot()),
        Computer(Race.Terran, Difficulty.Medium)
    ], realtime=False, save_replay_as="ZvT.SC2Replay")

if __name__ == '__main__':
    main()
