"""Tích hợp quái Day và scenario v1.1 qua headless."""

import copy
import os
import unittest

from helpers import Workdir, read_jsonl, run_headless, snapshots, write_json
from chonoi.contract import load_contract
from chonoi.day import DaySession
from chonoi.inputs import InputPlayer
from chonoi.items import validate_public_items


class MonsterIntegration(unittest.TestCase):
    def run_case(self, w, mode, scenario, ticks=0, extra=()):
        sc = write_json(w.path("scenario.json"), scenario)
        out = w.path("out.jsonl")
        code, err = run_headless("--mode", mode, "--seed", "1", "--ticks", str(ticks),
                                 "--scenario", sc, "--out", out, *extra)
        return code, err, out

    def test_day_spawns_and_standalone(self):
        with Workdir() as w:
            code, err, out = self.run_case(w, "gather", {"gather": {"random_fish": False}})
            self.assertEqual(code, 0, err)
            self.assertEqual([m["id"] for m in snapshots(read_jsonl(out))[0]["monsters"]], ["M1"])
        with Workdir() as w:
            code, err, out = self.run_case(w, "day", {"gather": {"time_left_ticks": 1, "random_fish": False},
                                                       "quan": {"time_left_ticks": 1}}, ticks=2450,
                                           extra=("--days", "5"))
            self.assertEqual(code, 0, err)
            starts = [s for s in snapshots(read_jsonl(out)) if s["phase"] == "gather" and s["phase_tick"] == 0]
            self.assertEqual([(s["day"], [m["id"] for m in s["monsters"]]) for s in starts],
                             [(1, ["M1"]), (2, ["M1"]), (3, ["M1", "M2"]),
                              (4, ["M1", "M2"]), (5, ["M1", "M2"])])

    def test_empty_and_recoil_fixture_via_cli(self):
        for monsters in ([], [{"id": "M9", "kind": "ca_sau", "pos": [50, 20],
                               "waypoints": [[50, 20], [54, 20]], "state": "recoil",
                               "state_ticks_left": 2, "recoil_dir": [1, 0]}]):
            with self.subTest(monsters=monsters), Workdir() as w:
                code, err, out = self.run_case(w, "gather", {"gather": {"monsters": monsters}})
                self.assertEqual(code, 0, err)
                self.assertEqual([m["id"] for m in snapshots(read_jsonl(out))[0]["monsters"]],
                                 [m["id"] for m in monsters])

    def test_monster_faint_hands_empty_stock_to_day_quan(self):
        with Workdir() as w:
            scenario = {"gather": {"player": {"pos": [60, 24], "hp": 1},
                                   "hold": ["ca_loc", "bong_sung"], "random_fish": False}}
            code, err, out = self.run_case(w, "day", scenario, ticks=1)
            self.assertEqual(code, 0, err)
            rows = read_jsonl(out)
            names = [r["name"] for r in rows if r["type"] == "event"]
            self.assertEqual(names[-4:], ["monster_hit", "faint", "gather_end", "phase_start"])
            lost = {r["name"]: r["data"]["lost"] for r in rows
                    if r["type"] == "event" and r["name"] in ("monster_hit", "faint")}
            self.assertEqual(lost, {"monster_hit": ["bong_sung"], "faint": ["ca_loc"]})
            self.assertEqual(snapshots(rows)[-1]["stock"], {})

    def test_day_monster_loss_v12_individuals(self):
        tuning = load_contract()["tuning"]
        tuning["freshness"] = {"initial": 100, "gather_decay_per_s": 0.5,
                               "quan_decay_per_s": 0.25, "spoiled_below": 30}
        hold = [{"id": "I9", "kind": "ca_loc", "fresh": 45},
                {"id": "I2", "kind": "ca_loc", "fresh": 99.5},
                {"id": "I7", "kind": "bong_sung", "fresh": 23998 / 240}]
        scenario = {"gather": {"player": {"pos": [60, 24], "hp": 1},
                               "random_fish": False}}
        session = DaySession(tuning, scenario, 1)
        # Cô lập mất hàng cho tới khi Gather khởi tạo và hao giỏ v1.2.
        session.sim.hold = validate_public_items(hold, "gather.hold")
        rows = session.step(InputPlayer([]).advance(0))
        lost = {r["name"]: r["data"]["lost"] for r in rows
                if r["name"] in ("monster_hit", "faint")}
        self.assertEqual(lost, {"monster_hit": [hold[2]], "faint": [hold[1], hold[0]]})
        self.assertFalse({item["id"] for item in lost["monster_hit"]} &
                         {item["id"] for item in lost["faint"]})

    def test_invalid_monsters_rejected_before_output(self):
        base = {"id": "M1", "kind": "ca_sau", "pos": [50, 20], "waypoints": [[50, 20], [54, 20]]}
        bad = [dict(base, target_idx=True), dict(base, state="recoil", state_ticks_left=0, recoil_dir=[1, 0]),
               dict(base, state="recoil", state_ticks_left=1, recoil_dir=[2, 0]),
               dict(base, state="stunned", state_ticks_left=0), dict(base, waypoints=[[50, 20]]),
               dict(base, pos=[50, 9]), dict(base, kind="unknown"), dict(base, extra=1)]
        groups = [[x] for x in bad] + [[base, copy.deepcopy(base)]]
        for group in groups:
            with self.subTest(group=group), Workdir() as w:
                code, _, out = self.run_case(w, "gather", {"gather": {"monsters": group}})
                self.assertEqual(code, 2)
                self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
