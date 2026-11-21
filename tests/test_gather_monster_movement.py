"""AC-P2-20: di chuyển cá sấu trong gather độc lập."""

import copy
import unittest

from chonoi.contract import load_contract
from chonoi.inputs import InputPlayer
from chonoi.runner import Session
from chonoi.sim.gather import GatherSim
from chonoi.ids import IdAllocator
from chonoi.rng import Streams
from helpers import Workdir, events, read_jsonl, run_headless, write_json


class MonsterMovement(unittest.TestCase):
    def setUp(self):
        self.tuning = copy.deepcopy(load_contract()["tuning"])
        self.g = self.tuning["gather"]
        self.spec = self.g["monsters"]["species"]["ca_sau"]

    def session(self, player=(0, 0)):
        return Session("gather", self.tuning, {"player": {"pos": list(player)}, "random_fish": False}, 1)

    def step(self, session):
        session.step(InputPlayer([]).advance(0))

    def test_initial_layout_and_patrol_waypoint(self):
        s = self.session()
        m = s.sim.monsters[0]
        self.assertEqual([x["id"] for x in s.snapshot()["monsters"]], ["M1"])
        self.step(s)
        self.assertAlmostEqual(m["pos"][0], self.g["monsters"]["spawns"][0]["pos"][0] +
                               self.spec["patrol_speed"] / self.tuning["tick_hz"])
        m["pos"] = [m["waypoints"][1][0] - self.spec["patrol_speed"] / (2 * self.tuning["tick_hz"]),
                    m["waypoints"][1][1]]
        self.step(s)
        self.assertEqual(m["pos"], m["waypoints"][1])
        self.assertEqual(m["target_idx"], 0)
        self.step(s)
        self.assertLess(m["pos"][0], m["waypoints"][1][0])

    def test_detection_and_chase_exit_boundaries(self):
        s = self.session((60, 14))
        m = s.sim.monsters[0]
        self.step(s)
        self.assertEqual(m["state"], "chase")
        self.assertAlmostEqual(m["pos"][1], 24 - self.spec["chase_speed"] / self.tuning["tick_hz"])
        m["pos"] = [60, 24]
        s.sim.pos = [60 + self.spec["exit_radius"], 24]
        self.step(s)
        self.assertEqual(m["state"], "chase")
        m["pos"] = [60, 24]
        s.sim.pos = [60 + self.spec["exit_radius"] + 0.01, 24]
        self.step(s)
        self.assertEqual(m["state"], "patrol")
        m["state"] = "chase"
        s.sim.pos = [60, self.spec["depths"][0] - 0.01]
        self.step(s)
        self.assertEqual(m["state"], "patrol")

    def test_no_detection_outside_radius_or_above_depth(self):
        for player in ([60 + self.spec["detect_radius"] + 0.01, 24],
                       [60, self.spec["depths"][0] - 0.01]):
            with self.subTest(player=player):
                s = self.session(player)
                self.step(s)
                self.assertEqual(s.sim.monsters[0]["state"], "patrol")

    def test_depth_threshold_and_snapshot_id_order(self):
        spawns = self.g["monsters"]["spawns"]
        spawns[1]["from_day"] = spawns[0]["from_day"]
        spawns.reverse()
        s = self.session((60, self.spec["depths"][0]))
        m = next(m for m in s.sim.monsters if m["id"] == "M1")
        m["pos"] = [62, self.spec["depths"][0]]
        self.step(s)
        self.assertEqual(m["state"], "chase")
        self.assertEqual([m["id"] for m in s.snapshot()["monsters"]], ["M1", "M2"])

    def test_clamps_map_and_species_depth(self):
        s = self.session()
        m = s.sim.monsters[0]
        for pos, target, axis, expected in [
            ([0, 15], [-1, 15], 0, 0), ([100, 15], [101, 15], 0, 100),
            ([50, 10], [50, 9], 1, 10), ([50, 30], [50, 31], 1, 30),
        ]:
            with self.subTest(pos=pos):
                m.update(pos=pos[:], waypoints=[pos[:], target], target_idx=1, state="patrol")
                self.step(s)
                self.assertEqual(m["pos"][axis], expected)


class MonsterCombat(unittest.TestCase):
    def setUp(self):
        self.t = copy.deepcopy(load_contract()["tuning"])
        self.spec = self.t["gather"]["monsters"]["species"]["ca_sau"]
        self.m = {"id": "M2", "kind": "ca_sau", "pos": [50, 20],
                  "waypoints": [[50, 20], [54, 20]]}

    def make(self, monsters=None, **overrides):
        scenario = {"player": {"pos": [50, 20]}, "random_fish": False,
                    "monsters": [copy.deepcopy(self.m)] if monsters is None else monsters}
        scenario.update(overrides)
        return Session("gather", self.t, scenario, 1)

    def step(self, s):
        return s.step(InputPlayer([]).advance(0))

    def test_v12_hit_and_fatal_loss_keep_lifo_id_and_fresh(self):
        from chonoi.items import validate_public_items

        self.t["freshness"] = {"initial": 100, "gather_decay_per_s": 0.5,
                               "quan_decay_per_s": 0.25, "spoiled_below": 30}
        fixture = [{"id": "I8", "kind": "ca_loc", "fresh": 40},
                   {"id": "I3", "kind": "ca_loc", "fresh": 99.5},
                   {"id": "I1", "kind": "bong_sung", "fresh": 23998 / 240},
                   {"id": "I5", "kind": "ca_linh", "fresh": 30}]
        for hold, hp in ((fixture, 3), (fixture, 1), ([], 1)):
            with self.subTest(count=len(hold), hp=hp):
                s = self.make(player={"pos": [50, 20], "hp": hp})
                s.sim.hold = validate_public_items(hold, "gather.hold")
                result = self.step(s)
                hit = next(e for e in result if e["name"] == "monster_hit")
                count = len(hold) // 2
                self.assertEqual(hit["data"]["lost"], list(reversed(hold))[:count])
                if hp == 1:
                    faint = next(e for e in result if e["name"] == "faint")
                    self.assertEqual(faint["data"]["lost"], list(reversed(hold))[count:])
                    self.assertFalse({it["id"] for it in hit["data"]["lost"]} &
                                     {it["id"] for it in faint["data"]["lost"]})
                    self.assertEqual(s.sim.hold, [])
                else:
                    self.assertEqual(s.sim.hold, validate_public_items(hold[:len(hold)-count]))

    def test_day_parameter_and_fixture_replacement(self):
        for day, expected in [(1, ["M1"]), (2, ["M1"]), (3, ["M1", "M2"])]:
            sim = GatherSim(self.t, {"random_fish": False}, Streams(1), IdAllocator(), day=day)
            self.assertEqual([m["id"] for m in sim.snapshot()["monsters"]], expected)
        self.assertEqual(self.make(monsters=[]).snapshot()["monsters"], [])
        self.assertEqual([m["id"] for m in self.make().snapshot()["monsters"]], ["M2"])

    def test_hit_lifo_tie_and_invulnerability(self):
        other = dict(self.m, id="M1")
        s = self.make(monsters=[self.m, other], hold=["ca_loc", "ca_linh", "bong_sung"])
        ev = self.step(s)
        self.assertEqual(ev[0]["data"], {"monster_id": "M1", "hp": 2, "lost": ["bong_sung"], "pos": [50.0, 20.0]})
        self.assertEqual(s.sim.hold, ["ca_loc", "ca_linh"])
        self.assertEqual(s.sim.invuln_ticks, self.t["gather"]["monsters"]["invuln_ticks"])
        self.assertEqual(s.sim.monsters[1]["recoil_dir"], [1.0, 0.0])
        self.assertEqual(self.step(s), [])
        self.assertEqual(s.sim.monsters[0]["state"], "chase")
        s.sim.invuln_ticks = 1
        self.assertEqual(self.step(s)[0]["name"], "monster_hit")

    def test_recoil_steps_direction_and_no_hit_on_final_step(self):
        s = self.make()
        self.step(s)
        m = s.sim.monsters[0]
        x = m["pos"][0]
        s.sim.invuln_ticks = 1000
        for _ in range(self.spec["recoil_ticks"]):
            self.step(s)
        self.assertAlmostEqual(m["pos"][0] - x, self.spec["recoil_dist"])
        self.assertEqual((m["state"], m["state_ticks_left"], m["recoil_dir"]), ("patrol", 0, None))
        fixture = dict(self.m, state="recoil", state_ticks_left=1, recoil_dir=[1, 0])
        s = self.make(monsters=[fixture])
        self.assertEqual(self.step(s), [])
        self.assertEqual(self.step(s)[0]["name"], "monster_hit")

    def test_hit_range_after_movement_and_depth_gate(self):
        radius = self.spec["hit_radius"]
        for distance, should_hit in [(radius, True), (radius + 0.01, False)]:
            with self.subTest(distance=distance):
                m = dict(self.m, pos=[50 + distance, 20])
                s = self.make(monsters=[m])
                # Giữ nguyên vị trí quái để xét chính xác ngưỡng chạm sau di chuyển.
                s.sim.t["monsters"]["species"]["ca_sau"]["chase_speed"] = 0
                self.assertEqual(bool(self.step(s)), should_hit)
        s = self.make(player={"pos": [50, self.spec["depths"][0] - 0.01]},
                      monsters=[dict(self.m, pos=[50, self.spec["depths"][0]])])
        self.assertEqual(self.step(s), [])

    def test_invulnerability_expires_exactly_at_configured_tick(self):
        s = self.make(monsters=[self.m, dict(self.m, id="M1")])
        self.step(s)
        for _ in range(self.t["gather"]["monsters"]["invuln_ticks"] - 1):
            self.assertFalse(any(e["name"] == "monster_hit" for e in self.step(s)))
        self.assertEqual([e["name"] for e in self.step(s)], ["monster_hit"])

    def test_faint_after_choke_hit_before_time(self):
        s = self.make(player={"pos": [50, 20], "hp": 2, "oxygen_ticks": 0, "zero_oxy_ticks": 59},
                      hold=["ca_loc", "ca_linh", "bong_sung"], time_left_ticks=1)
        ev = self.step(s)
        self.assertEqual([e["name"] for e in ev], ["choke", "monster_hit", "faint", "gather_end"])
        self.assertEqual(ev[1]["data"]["lost"], ["bong_sung"])
        self.assertEqual(ev[2]["data"], {"cause": "monster", "lost": ["ca_linh", "ca_loc"], "hp": 0})
        self.assertEqual(ev[3]["data"], {"reason": "fainted", "inventory": {"items": {}}})

    def test_fatal_choke_prevents_hit_even_when_invulnerable(self):
        s = self.make(player={"pos": [50, 20], "hp": 1, "oxygen_ticks": 0,
                              "zero_oxy_ticks": 59, "invuln_ticks": 10})
        self.assertEqual([e["name"] for e in self.step(s)], ["choke", "faint", "gather_end"])

    def test_headless_monster_faint_and_inventory(self):
        import json
        with Workdir() as w:
            sc = write_json(w.path("scenario.json"), {"gather": {"player": {"pos": [60, 24], "hp": 1},
                            "hold": ["ca_loc", "ca_linh", "bong_sung"], "random_fish": False}})
            out, inv = w.path("out.jsonl"), w.path("inventory.json")
            code, err = run_headless("--mode", "gather", "--seed", "1", "--ticks", "2",
                                     "--scenario", sc, "--out", out, "--inventory-out", inv)
            self.assertEqual(code, 0, err)
            ev = events(read_jsonl(out))
            self.assertEqual([e["name"] for e in ev], ["monster_hit", "faint", "gather_end"])
            with open(inv, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"items": {}})


if __name__ == "__main__":
    unittest.main()
