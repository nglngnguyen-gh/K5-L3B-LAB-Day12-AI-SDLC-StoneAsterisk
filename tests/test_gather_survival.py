"""Black-box tests for gather oxygen, choking and fainting."""

import json
import unittest

from helpers import Workdir, events, frames, read_jsonl, run_headless, snapshots, write_json
from chonoi.contract import load_contract
from chonoi.inputs import InputPlayer
from chonoi.items import validate_public_items
from chonoi.runner import Session


class GatherSurvival(unittest.TestCase):
    def test_v12_choke_loss_preserves_individuals_and_lifo(self):
        tuning = load_contract()["tuning"]
        tuning["freshness"] = {"initial": 100, "gather_decay_per_s": 0.5,
                               "quan_decay_per_s": 0.25, "spoiled_below": 30}
        fixture = [{"id": "I9", "kind": "ca_loc", "fresh": 99.5},
                   {"id": "I2", "kind": "ca_loc", "fresh": 30},
                   {"id": "I7", "kind": "bong_sung", "fresh": 23998 / 240}]
        for hold in (fixture, []):
            with self.subTest(hold=hold):
                s = Session("gather", tuning, {"player": {"pos": [50, 5], "hp": 1,
                            "oxygen_ticks": 0, "zero_oxy_ticks": 59}, "random_fish": False,
                            "monsters": []}, 1)
                # Cô lập logic mất hàng: phần khởi tạo giỏ v1.2 thuộc BLong1501.
                s.sim.hold = validate_public_items(hold, "gather.hold")
                result = s.step(InputPlayer([]).advance(0))
                faint = next(e for e in result if e["name"] == "faint")
                self.assertEqual(faint["data"]["lost"], list(reversed(hold)))
                self.assertEqual(s.sim.hold, [])

    def test_no_transition_at_rest_and_initial_empty(self):
        with Workdir() as w:
            rows, _, _ = self.run_case(w, {"player": {"pos": [50, 5], "oxygen_ticks": 0}}, ticks=2)
            self.assertEqual(events(rows), [])
            self.assertEqual(snapshots(rows)[-1]["player"]["zero_oxy_ticks"], 2)
            rows, _, _ = self.run_case(w, {"player": {"pos": [50, 0.5], "oxygen_ticks": 100}}, ticks=1, suffix="surface")
            self.assertEqual(events(rows), [])
            self.assertEqual(snapshots(rows)[-1]["player"]["oxygen_ticks"], 106)

    def test_dive_empty_and_faint_event_order_in_same_tick(self):
        tuning = load_contract()["tuning"]
        tuning["gather"]["choke_interval_ticks"] = 1
        session = Session("gather", tuning, {"player": {"pos": [50, 0.5], "oxygen_ticks": 1, "hp": 1}}, 7)
        inp = InputPlayer([{"tick": 0, "move": [0, 1]}]).advance(0)
        result = session.step(inp)
        self.assertEqual([e["name"] for e in result], ["dive", "oxygen_empty", "choke", "faint", "gather_end"])
        self.assertTrue(all(e["tick"] == 1 for e in result))
        self.assertEqual(result[1]["data"], {"oxygen_ticks": 0})
        self.assertEqual(result[2]["data"], {"hp": 0})

    def run_case(self, w, scenario, inputs=(), ticks=1, suffix=""):
        sc = write_json(w.path("sc" + suffix + ".json"), {"gather": scenario})
        inp = write_json(w.path("in" + suffix + ".json"), frames(*inputs))
        out = w.path("out" + suffix + ".jsonl")
        inv = w.path("inv" + suffix + ".json")
        code, err = run_headless("--mode", "gather", "--seed", "7", "--ticks", str(ticks),
                                 "--scenario", sc, "--inputs", inp, "--snapshot-every", "1",
                                 "--out", out, "--inventory-out", inv)
        self.assertEqual(code, 0, err)
        return read_jsonl(out), out, inv

    def test_oxygen_depletion_refill_and_limits(self):
        with Workdir() as w:
            rows, _, _ = self.run_case(w, {"player": {"pos": [50, 5], "oxygen_ticks": 2}}, ticks=4)
            ps = [s["player"] for s in snapshots(rows)]
            self.assertEqual([p["oxygen_ticks"] for p in ps], [2, 1, 0, 0, 0])
            self.assertEqual([e["tick"] for e in events(rows, "oxygen_empty")], [2])
            self.assertEqual([p["zero_oxy_ticks"] for p in ps], [0, 0, 1, 2, 3])
            rows, _, _ = self.run_case(w, {"player": {"pos": [50, 0], "oxygen_ticks": 1798}}, ticks=2, suffix="b")
            self.assertEqual([s["player"]["oxygen_ticks"] for s in snapshots(rows)], [1798, 1800, 1800])

    def test_dive_surface_and_final_depth(self):
        with Workdir() as w:
            rows, _, _ = self.run_case(w, {"player": {"pos": [50, 0.5], "oxygen_ticks": 100}},
                                        [{"tick": 0, "move": [0, 1]}, {"tick": 8, "move": [0, -1]}], ticks=30)
            ev = [e for e in events(rows) if e["name"] in ("dive", "surface")]
            self.assertEqual([e["name"] for e in ev], ["dive", "surface"])
            self.assertGreater(ev[0]["data"]["pos"][1], 0.5)
            self.assertLessEqual(ev[1]["data"]["pos"][1], 0.5)
            by_tick = {s["tick"]: s["player"] for s in snapshots(rows)}
            self.assertEqual(by_tick[ev[0]["tick"]]["oxygen_ticks"], 99)
            self.assertGreater(by_tick[ev[1]["tick"]]["oxygen_ticks"], by_tick[ev[1]["tick"]-1]["oxygen_ticks"])

    def test_choke_exact_tick_and_repeat(self):
        with Workdir() as w:
            rows, _, _ = self.run_case(w, {"player": {"pos": [50, 5], "oxygen_ticks": 1}}, ticks=120)
            self.assertEqual([e["tick"] for e in events(rows, "oxygen_empty")], [1])
            self.assertEqual([(e["tick"], e["data"]["hp"]) for e in events(rows, "choke")], [(60, 2), (120, 1)])
            s = {x["tick"]: x["player"] for x in snapshots(rows)}
            self.assertEqual(s[1]["zero_oxy_ticks"], 1)
            self.assertEqual(s[59]["zero_oxy_ticks"], 59)
            self.assertEqual(s[60]["zero_oxy_ticks"], 0)

    def test_surface_on_due_tick_prevents_choke(self):
        with Workdir() as w:
            sc = {"player": {"pos": [50, 0.51], "vel": [0, -4], "oxygen_ticks": 0, "zero_oxy_ticks": 59}}
            rows, _, _ = self.run_case(w, sc, [{"tick": 0, "move": [0, -1]}])
            self.assertEqual([e["name"] for e in events(rows)], ["surface"])
            p = snapshots(rows)[-1]["player"]
            self.assertEqual((p["hp"], p["zero_oxy_ticks"], p["oxygen_ticks"]), (3, 0, 6))

    def test_faint_lifo_order_final_snapshot_inventory_and_determinism(self):
        sc = {"player": {"pos": [2, 1], "oxygen_ticks": 0, "zero_oxy_ticks": 59, "hp": 1},
              "hold": ["ca_loc", "bong_sung", "ca_linh"], "time_left_ticks": 1,
              "fish": [{"id": "F1", "kind": "ca_loc", "pos": [2, 1]}]}
        with Workdir() as w:
            rows, out, inv = self.run_case(w, sc, [{"tick": 0, "interact": True, "catch": True}], ticks=2)
            rows2, out2, _ = self.run_case(w, sc, [{"tick": 0, "interact": True, "catch": True}], ticks=2, suffix="b")
            self.assertEqual([e["name"] for e in events(rows)], ["choke", "faint", "gather_end"])
            self.assertEqual(events(rows, "faint")[0]["data"], {"cause": "choke", "lost": ["ca_linh", "bong_sung", "ca_loc"], "hp": 0})
            self.assertEqual(events(rows, "gather_end")[0]["data"], {"reason": "fainted", "inventory": {"items": {}}})
            self.assertEqual([r["type"] for r in rows], ["snapshot", "event", "event", "event", "snapshot", "end"])
            self.assertEqual(snapshots(rows)[-1]["hold"], [])
            self.assertEqual(snapshots(rows)[-1]["player"]["hp"], 0)
            self.assertEqual(rows[-1]["reason"], "fainted")
            with open(inv, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"items": {}})
            with open(out, "rb") as a, open(out2, "rb") as b:
                self.assertEqual(a.read(), b.read())
            self.assertEqual(rows, rows2)


if __name__ == "__main__":
    unittest.main()
