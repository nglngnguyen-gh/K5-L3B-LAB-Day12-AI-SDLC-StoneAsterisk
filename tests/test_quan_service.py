import unittest

from chonoi.contract import load_contract
from chonoi.inputs import LiveInputs
from chonoi.runner import Session


class QuanService(unittest.TestCase):
    def setUp(self):
        self.tuning = load_contract()["tuning"]

    def test_reserved_order_is_cooked_then_picked_and_served(self):
        scenario = {
            "player": {"pos": [2, 8]},
            "stock": {"bong_sung": 2},
            "random_customers": False,
            "customers": [{"id": "C1", "table_id": "T1", "dish_id": "goi_bong_sung", "order_tick": 1}],
        }
        session = Session("quan", self.tuning, scenario, 1)
        controls = LiveInputs()
        idle = session.step(controls.advance())
        self.assertNotIn("cook_started", [r["name"] for r in idle], "không interact thì bếp không tự nấu")
        controls.set(interact=True)
        started = session.step(controls.advance())
        controls.set(interact=False)
        controls.advance()
        self.assertEqual([r["name"] for r in started], ["cook_started"])
        self.assertEqual(started[0]["data"]["items"], {"bong_sung": 2})
        self.assertEqual(session.sim.stock["bong_sung"], 0)
        self.assertEqual(session.sim.customers[0]["order_status"], "assigned")

        ready_events = []
        for _ in range(4 * 60):
            ready_events.extend(session.step(controls.advance()))
        self.assertIn("dish_ready", [r["name"] for r in ready_events])
        controls.set(interact=True)
        picked = session.step(controls.advance())
        self.assertEqual([r["name"] for r in picked], ["dish_picked"])
        self.assertEqual(session.sim.hand["order_id"], "C1")

        controls.set(interact=False)
        controls.advance()
        session.sim.pos = list(self.tuning["quan"]["tables"][0]["pos"])
        controls.set(interact=True)
        served = session.step(controls.advance())
        self.assertEqual([r["name"] for r in served], ["served"])
        self.assertEqual(served[0]["data"]["tip"], 8)
        self.assertEqual(session.sim.customers[0]["order_status"], "served")

    def test_two_stoves_each_take_oldest_reserved_order(self):
        # AC-P2-30 (v1.1): B1 [2,8], B2 [5,8]; interact ở từng bếp lấy đơn reserved cũ nhất (order_tick, id bàn)
        scenario = {
            "player": {"pos": [2, 8]}, "random_customers": False, "stock": {"bong_sung": 2, "ca_loc": 1},
            "customers": [{"id": "C1", "table_id": "T2", "dish_id": "goi_bong_sung", "order_tick": 0},
                          {"id": "C2", "table_id": "T1", "dish_id": "ca_loc_nuong_trui", "order_tick": 0}],
        }
        session = Session("quan", self.tuning, scenario, 1)
        controls = LiveInputs()
        controls.set(interact=True)
        first = session.step(controls.advance())
        controls.set(interact=False)
        controls.advance()
        session.sim.pos = list(self.tuning["quan"]["stoves"][1]["pos"])
        controls.set(interact=True)
        second = session.step(controls.advance())
        got = [(r["data"]["stove_id"], r["data"]["order_id"]) for r in first + second if r["name"] == "cook_started"]
        self.assertEqual(got, [("B1", "C2"), ("B2", "C1")], "cùng order_tick -> id bàn T1 trước T2")
        self.assertEqual([st["state"] for st in session.sim.stoves], ["cooking", "cooking"])

    def test_cooking_consumes_reserved_ids_and_locks_freshness_price(self):
        scenario = {
            "random_customers": False,
            "stock": {"ca_linh": 3, "bong_dien_dien": 1},
            "customers": [{"id": "C1", "table_id": "T1", "dish_id": "lau_ca_linh_dien_dien"}],
        }
        session = Session("quan", self.tuning, scenario, 1)
        sim = session.sim
        sim.stock = [
            {"id": "I1", "kind": "ca_linh", "fresh_units": 21600},
            {"id": "I2", "kind": "ca_linh", "fresh_units": 19200},
            {"id": "I3", "kind": "ca_linh", "fresh_units": 24000},
            {"id": "I4", "kind": "bong_dien_dien", "fresh_units": 24000},
            {"id": "I5", "kind": "ca_linh", "fresh_units": 24000},
        ]
        sim.customers[0]["reserved"] = ["I3", "I1", "I4", "I2"]
        events = []

        self.assertTrue(sim._cook_at(sim.stoves[0], events))
        started = events[0][1]
        self.assertEqual(
            started["items"],
            [
                {"id": "I4", "kind": "bong_dien_dien", "fresh": 100},
                {"id": "I1", "kind": "ca_linh", "fresh": 90},
                {"id": "I2", "kind": "ca_linh", "fresh": 80},
                {"id": "I3", "kind": "ca_linh", "fresh": 100},
            ],
        )
        self.assertEqual([item["id"] for item in sim.stock], ["I5"])
        self.assertEqual(started["base_price"], 111)
        self.assertEqual(sim.stoves[0]["dish"]["base_price"], 111)

        sim.hand = dict(sim.stoves[0]["dish"])
        sim.pos = list(sim.tables[0]["pos"])
        controls = LiveInputs()
        controls.set(interact=True)
        sim._interact(controls.advance(), events)
        served = events[-1][1]
        self.assertEqual(served["base_price"], 111)
        self.assertEqual(served["tip"], 22)

    def test_finished_meal_is_paid_after_eating_ticks(self):
        scenario = {
            "random_customers": False,
            "customers": [{"id": "C1", "table_id": "T1", "dish_id": "goi_bong_sung", "state": "eating",
                            "order_status": "served", "eat_ticks_left": 1, "base_price": 40, "tip": 8}],
        }
        session = Session("quan", self.tuning, scenario, 1)
        rows = session.step(LiveInputs().advance())
        self.assertEqual([r["name"] for r in rows], ["paid"])
        self.assertEqual(rows[0]["data"], {"order_id": "C1", "table_id": "T1", "base_price": 40,
                                            "tip": 8, "amount": 48, "reason": "finished_eating"})
        self.assertEqual(session.sim.earned, 48)
        self.assertEqual(session.sim.reputation, 3.2)

    def test_serve_on_last_tick_then_closing_pays(self):
        scenario = {
            "time_left_ticks": 1, "random_customers": False, "player": {"pos": [9, 2]},
            "hand": {"order_id": "C1", "dish_id": "goi_bong_sung", "base_price": 40},
            "customers": [{"id": "C1", "table_id": "T1", "dish_id": "goi_bong_sung",
                           "order_status": "assigned", "reserved": {}}],
        }
        session = Session("quan", self.tuning, scenario, 1)
        controls = LiveInputs()
        controls.set(interact=True)
        rows = session.step(controls.advance())
        self.assertEqual([r["name"] for r in rows], ["served", "paid", "quan_end"])
        self.assertEqual(rows[1]["data"]["reason"], "closing")

    def test_nearest_object_not_interactable_skips_turn(self):
        # đứng ngay bếp B1 idle, không có đơn reserved; bàn T1 ở xa -> bỏ lượt, không event
        scenario = {"player": {"pos": [2, 8]}, "random_customers": False, "stock": {}}
        session = Session("quan", self.tuning, scenario, 1)
        controls = LiveInputs()
        controls.set(interact=True)
        self.assertEqual(session.step(controls.advance()), [])

    def test_closing_collects_eating_order_without_waiting_for_timer(self):
        scenario = {
            "time_left_ticks": 1,
            "random_customers": False,
            "customers": [{"id": "C1", "table_id": "T1", "dish_id": "goi_bong_sung", "state": "eating",
                            "order_status": "served", "eat_ticks_left": 5, "base_price": 40, "tip": 8}],
        }
        session = Session("quan", self.tuning, scenario, 1)
        rows = session.step(LiveInputs().advance())
        self.assertEqual([r["name"] for r in rows], ["paid", "quan_end"])
        self.assertEqual(rows[0]["data"]["reason"], "closing")
        self.assertEqual(session.sim.earned, 48)
        self.assertEqual(session.sim.reputation, 3.2)
        self.assertTrue(session.done)

if __name__ == "__main__":
    unittest.main()
