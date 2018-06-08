import random

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer

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
    
    async def setup_extractors(self):
        drone = self.workers.prefer_idle.random
        idle_extractors = self.state.vespene_geyser.filter(lambda vg: vg.name == "Extractor" and vg.assigned_harvesters == 0)
        idle_extractors = idle_extractors.prefer_close_to(drone.position)
        if idle_extractors.exists:
            print("assigning worker to idle extractor")
            err = await self.do(drone.gather(idle_extractors.first))

        available = self.state.vespene_geyser.filter(lambda vg: vg.name != "Extractor")
        if available.empty:
            print("no available geysers")
            return
        
        if not self.can_afford(EXTRACTOR):
            print("can't afford extractor")
            return

        drone = self.workers.prefer_idle.random
        target = available.closest_to(drone.position)
        print("building extractor at", target.position)
        err = await self.do(drone.build(EXTRACTOR, target))
        if not err:
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


    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send("(glhf)")
        
        if iteration % 100 == 0 and self.attack_wave_counter >= 1:
            await self.setup_extractors()

        if not self.units(HATCHERY).ready.exists:
            for unit in self.workers | self.units(ZERGLING) | self.units(QUEEN):
                await self.do(unit.attack(self.enemy_start_locations[0]))
            return

        hatchery = self.units(HATCHERY).ready.first
        larvae = self.units(LARVA)

        target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
        attack_wave_size = 10
        if len(self.units(ZERGLING).idle) >= attack_wave_size:
            print("sending attack wave ", self.attack_wave_counter)
            for zl in self.units(ZERGLING).idle:
                await self.do(zl.attack(target))
            self.attack_wave_counter += 1

        for queen in self.units(QUEEN).idle:
            abilities = await self.get_available_abilities(queen)
            if AbilityId.EFFECT_INJECTLARVA in abilities:
                await self.do(queen(EFFECT_INJECTLARVA, hatchery))

        if iteration % 60 == 0:
            await self.run_zerg_upgrade_logic()

        if self.supply_left < 2:
            if self.can_afford(OVERLORD) and larvae.exists:
                await self.do(larvae.random.train(OVERLORD))

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
                if await self.can_place(HATCHERY, pos):
                    self.spawning_pool_started = True
                    await self.do(self.workers.random.build(HATCHERY, pos))
                    break

        if self.drone_counter < 3:
            if self.can_afford(DRONE):
                self.drone_counter += 1
                await self.do(larvae.random.train(DRONE))

        if not self.spawning_pool_started:
            if self.can_afford(SPAWNINGPOOL):
                for d in range(4, 15):
                    pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                    if await self.can_place(SPAWNINGPOOL, pos):
                        drone = self.workers.closest_to(pos)
                        err = await self.do(drone.build(SPAWNINGPOOL, pos))
                        if not err:
                            self.spawning_pool_started = True
                            break

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
