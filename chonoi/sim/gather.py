"""Buổi sáng — Lặn & Hái (`gather`). KHUNG: bơi, chặn mép, đồng hồ, cập bến, xuất kho.

Mặt cắt dòng sông nhìn NGANG: vị trí `[x, d]` (x sang phải, `d` độ sâu hướng xuống, d = 0 là mặt nước).
`move = [x, d]`: thành phần thứ hai DƯƠNG = bơi xuống. Hướng mặt là góc từ +x, dương = xuống.

Đã làm sẵn để smoke test chạy được: bơi + tăng/giảm tốc, chặn mép (d không âm), đồng hồ và hết giờ,
cập bến (`interact` trong vùng bến -> `gather_end` reason `docked`), xuất kho, snapshot đầy đủ trường gather.

Nhóm viết tiếp (đúng thứ tự một bước trong PRD mục 13.8, "Gather"):
  TODO(nhóm, lát 1): bơi + oxy + biên + giỏ
      - oxy: dưới nước (d > surface_depth) trừ 1 tick/tick, mặt nước hồi oxygen_refill_per_tick, kẹp [0, max]
      - ngạt: oxy = 0 và đang dưới nước -> đếm zero_oxy_ticks, đủ choke_interval_ticks thì -1 Máu (choke)
      - Máu về 0 -> ngất (faint, gather_end reason `fainted`, mất toàn bộ giỏ, kho rỗng)
      - sự kiện dive / surface / oxygen_empty / choke / faint
      - giỏ: thứ tự nhặt (LIFO), sức chứa hold_capacity
  ĐÃ LÀM (lát 2, BLong1501): hái + bắt cá + cập bến + kho — test: tests/test_gather_slice2.py
      - hái nút ở mặt nước (gather, hold_full), nút mọc lại (node_regrown)
      - bắt đàn cá bằng `catch` (fish_caught, hold_full, hồi chiêu catch_cd_ticks, chỉ khi dưới nước)
      - cập bến xét TRƯỚC hái; ghi kho đúng một lần do runner lo
Các tính năng của phase sau chưa nằm trong khung này.
"""

import math

from ..ids import id_key, sort_by_id
from ..inventory import hold_to_items
from ..items import ItemIds, public_list
from .ramp import ramp_velocity

TICK = 60.0
AXES = ("x", "d")


class GatherSim:
    mode = "gather"
    phase = "gather"

    def __init__(self, tuning, scenario, streams, ids, day=1, item_ids=None):
        # v1.2: bộ cấp id cá thể I1, I2, … dùng chung cả lượt (`day` truyền vào; chạy riêng thì tự tạo)
        self.item_ids = item_ids if item_ids is not None else ItemIds()
        t = tuning["gather"]
        self.t = t
        self.tick_hz = tuning["tick_hz"]
        self.rng = streams
        self.ids = ids
        p = scenario.get("player", {})
        self.pos = [float(c) for c in p.get("pos", t["start_pos"])]
        self.vel = [float(c) for c in p.get("vel", [0.0, 0.0])]
        self._tgt = None
        self._ramp_left = 0
        self.heading = float(p.get("heading_deg", t["start_heading_deg"]))
        self.oxygen_max = int(round(t["oxygen_max_s"] * TICK))
        self.oxygen_ticks = p.get("oxygen_ticks", self.oxygen_max)
        self.hp = p.get("hp", t["hp_max"])
        self.zero_oxy_ticks = p.get("zero_oxy_ticks", 0)
        self.invuln_ticks = p.get("invuln_ticks", 0)
        self.catch_cd_ticks = p.get("catch_cd_ticks", 0)
        self.hold = list(scenario.get("hold", []))  # thứ tự nhặt, cuối mảng là mới nhất
        self.time_left_ticks = scenario.get("time_left_ticks", int(round(t["duration_s"] * TICK)))
        # nút và đàn cá: scenario THAY THẾ danh sách mặc định; random_fish=false tắt cá mặc định
        src_nodes = scenario["nodes"] if "nodes" in scenario else t["nodes"]
        self.nodes = [{"id": n["id"], "kind": n["kind"], "pos": [float(c) for c in n["pos"]],
                       "regrow_ticks": n.get("regrow_ticks", 0)} for n in src_nodes]
        # v1.1: fish_initial là SỐ đàn đầu ca, sinh theo seed (TICKET-02 mục 1.1). Scenario `fish` thay thế.
        self._random_fish = bool(scenario.get("random_fish", True))
        self.phase_tick = 0
        src_fish = scenario["fish"] if "fish" in scenario else []
        self.fish = [{"id": f["id"], "kind": f["kind"], "pos": [float(c) for c in f["pos"]],
                      "heading_deg": f.get("heading_deg", 0), "age_ticks": f.get("age_ticks", 0)}
                     for f in src_fish]
        # Fixture thay toàn bộ spawn; gather độc lập mặc định ngày 1.
        src_monsters = scenario.get("monsters")
        if src_monsters is None:
            src_monsters = [m for m in t["monsters"]["spawns"] if m["from_day"] <= day]
        self.monsters = [{"id": m["id"], "kind": m["kind"],
                          "pos": [float(c) for c in m["pos"]],
                          "waypoints": [[float(c) for c in p] for p in m["waypoints"]],
                          "target_idx": m.get("target_idx", 1), "state": m.get("state", "patrol"),
                          "state_ticks_left": m.get("state_ticks_left", 0),
                          "recoil_dir": list(m["recoil_dir"]) if m.get("recoil_dir") is not None else None}
                         for m in src_monsters]
        for coll in (self.nodes, self.fish, self.monsters):
            for e in coll:
                ids.reserve(e["id"])
        if "fish" not in scenario and self._random_fish:
            for _ in range(int(t["fish_initial"])):
                school = self._spawn_school()
                if school is None:
                    break
                self.fish.append(school)
        self.money = 0
        self.earned = 0
        self.reputation = tuning["quan"]["reputation_initial"]
        self.done = False
        self.reason = None

    # --- giao diện cho runner -------------------------------------------------
    def inventory_items(self) -> dict:
        return hold_to_items(self.hold)

    def snapshot(self) -> dict:
        return {
            "player": {"pos": self.pos, "vel": self.vel, "heading_deg": self.heading,
                       "oxygen_ticks": self.oxygen_ticks, "oxygen_max_ticks": self.oxygen_max,
                       "hp": self.hp, "hp_max": self.t["hp_max"], "zero_oxy_ticks": self.zero_oxy_ticks,
                       "invuln_ticks": self.invuln_ticks, "catch_cd_ticks": self.catch_cd_ticks,
                       "at_surface": self._at_surface()},
            "hold": self.hold, "hold_count": len(self.hold),
            "hold_capacity": self.t["hold_capacity"],
            "nodes": [{"id": n["id"], "pos": n["pos"], "kind": n["kind"],
                       "ready": n["regrow_ticks"] == 0, "regrow_ticks": n["regrow_ticks"]}
                      for n in sort_by_id(self.nodes)],
            "fish": [{"id": f["id"], "pos": f["pos"], "kind": f["kind"], "heading_deg": f["heading_deg"],
                      "age_ticks": f["age_ticks"]}
                     for f in sort_by_id(self.fish)],
            "monsters": [{"id": m["id"], "kind": m["kind"], "pos": list(m["pos"]),
                          "waypoints": [list(p) for p in m["waypoints"]], "target_idx": m["target_idx"],
                          "state": m["state"], "state_ticks_left": m["state_ticks_left"],
                          "recoil_dir": m["recoil_dir"]} for m in sort_by_id(self.monsters)],
        }

    # --- một bước ---------------------------------------------------------------
    def step(self, inp):
        events = []
        # 1. đồng hồ và hàng có sẵn: giảm bộ đếm, nút mọc lại
        self.phase_tick += 1
        self.time_left_ticks = max(0, self.time_left_ticks - 1)
        self.invuln_ticks = max(0, self.invuln_ticks - 1)
        self.catch_cd_ticks = max(0, self.catch_cd_ticks - 1)
        for n in sort_by_id(self.nodes):
            if n["regrow_ticks"] > 0:
                n["regrow_ticks"] -= 1
                if n["regrow_ticks"] == 0:
                    events.append(("node_regrown", {"node_id": n["id"]}))
        # 2. bơi + chặn mép
        was_surface = self._at_surface()
        self._move(inp)
        at_surface = self._at_surface()
        if was_surface != at_surface:
            events.append(("surface" if at_surface else "dive", {"pos": list(self.pos)}))
        if at_surface:
            self.oxygen_ticks = min(self.oxygen_max, self.oxygen_ticks + self.t["oxygen_refill_per_tick"])
            self.zero_oxy_ticks = 0
        else:
            previous_oxygen = self.oxygen_ticks
            self.oxygen_ticks = max(0, self.oxygen_ticks - 1)
            if previous_oxygen > 0 and self.oxygen_ticks == 0:
                events.append(("oxygen_empty", {"oxygen_ticks": 0}))
            if self.oxygen_ticks == 0:
                self.zero_oxy_ticks += 1
                if self.zero_oxy_ticks >= self.t["choke_interval_ticks"]:
                    self.zero_oxy_ticks = 0
                    self.hp -= 1
                    events.append(("choke", {"hp": self.hp}))
                    if self.hp == 0:
                        lost = self._public_lost(reversed(self.hold))
                        self.hold.clear()
                        events.append(("faint", {"cause": "choke", "lost": lost, "hp": 0}))
                        self._finish("fainted", events)
                        return events
        eligible = self._move_monsters()
        self._monster_hit(eligible, events)
        if self.done:
            return events
        # 3. interact: bến trước, rồi hái
        if inp.pressed("interact"):
            if self._in_dock():
                self._finish("docked", events)
                return events
            # Lát 2 (AC-P1-20): ngoài bến, chỉ hái khi ở mặt nước.
            if self._at_surface():
                self._harvest(events)
        # 4. bắt cá (AC-P1-21): chỉ khi hết hồi chiêu và đang dưới nước
        if inp.pressed("catch") and self.catch_cd_ticks == 0 and not self._at_surface():
            self._catch(events)
        # 5. hết giờ; nếu còn giờ -> cá bơi và sinh theo lịch (TICKET-02 mục 4.5)
        if self.time_left_ticks <= 0:
            self._finish("time", events)
            return events
        if self._random_fish:
            self._swim_fish()
            self._maybe_spawn_fish(events)
        return events

    # --- tiện ích ---------------------------------------------------------------
    @staticmethod
    def _public_lost(items):
        items = list(items)
        return public_list(items) if items and isinstance(items[0], dict) else items

    def _move_monsters(self):
        """Cập nhật patrol/chase sau khi người chơi di chuyển, theo thứ tự id."""
        eligible = []
        for monster in sort_by_id(self.monsters):
            spec = self.t["monsters"]["species"][monster["kind"]]
            if monster["state"] == "stunned":
                monster["state_ticks_left"] -= 1
                if monster["state_ticks_left"] == 0:
                    monster["state"] = "patrol"
                continue
            if monster["state"] == "recoil":
                distance = spec["recoil_dist"] / spec["recoil_ticks"]
                for i in range(2):
                    monster["pos"][i] += monster["recoil_dir"][i] * distance
                self._clamp_monster(monster, spec)
                monster["state_ticks_left"] -= 1
                if monster["state_ticks_left"] == 0:
                    monster["state"] = "patrol"
                    monster["recoil_dir"] = None
                continue
            distance = math.dist(monster["pos"], self.pos)
            if monster["state"] == "chase":
                if self.pos[1] < spec["depths"][0] or distance > spec["exit_radius"]:
                    monster["state"] = "patrol"
            elif monster["state"] == "patrol":
                if self.pos[1] >= spec["depths"][0] and distance <= spec["detect_radius"]:
                    monster["state"] = "chase"
            else:
                continue
            target = self.pos if monster["state"] == "chase" else monster["waypoints"][monster["target_idx"]]
            dx, dd = (target[i] - monster["pos"][i] for i in range(2))
            length = math.hypot(dx, dd)
            speed = spec["chase_speed"] if monster["state"] == "chase" else spec["patrol_speed"]
            step = min(length, speed / self.tick_hz)
            if length:
                monster["pos"][0] += dx * step / length
                monster["pos"][1] += dd * step / length
            if monster["state"] == "patrol" and length <= speed / self.tick_hz:
                monster["target_idx"] = 1 - monster["target_idx"]
            self._clamp_monster(monster, spec)
            eligible.append(monster)
        return eligible

    def _clamp_monster(self, monster, spec):
        bounds = self.t["bounds"]
        for i, (lo, hi) in enumerate((bounds["x"], (max(bounds["d"][0], spec["depths"][0]),
                                                    min(bounds["d"][1], spec["depths"][1])))):
            monster["pos"][i] = max(lo, min(hi, monster["pos"][i]))

    def _monster_hit(self, eligible, events):
        if self.invuln_ticks:
            return
        candidates = [m for m in eligible
                      if self.pos[1] >= self.t["monsters"]["species"][m["kind"]]["depths"][0]
                      and math.dist(self.pos, m["pos"]) <= self.t["monsters"]["species"][m["kind"]]["hit_radius"]]
        if not candidates:
            return
        m = min(candidates, key=lambda x: (math.dist(self.pos, x["pos"]), id_key(x["id"])))
        spec = self.t["monsters"]["species"][m["kind"]]
        dx, dd = m["pos"][0] - self.pos[0], m["pos"][1] - self.pos[1]
        length = math.hypot(dx, dd)
        m["recoil_dir"] = [dx / length, dd / length] if length else [1.0, 0.0]
        m["state"] = "recoil"
        m["state_ticks_left"] = spec["recoil_ticks"]
        self.hp -= 1
        lost = self._public_lost(self.hold.pop() for _ in range(math.floor(len(self.hold) * self.t["monsters"]["loss_ratio"])))
        self.invuln_ticks = self.t["monsters"]["invuln_ticks"]
        events.append(("monster_hit", {"monster_id": m["id"], "hp": self.hp, "lost": lost, "pos": list(self.pos)}))
        if self.hp == 0:
            remaining = self._public_lost(reversed(self.hold))
            self.hold.clear()
            events.append(("faint", {"cause": "monster", "lost": remaining, "hp": 0}))
            self._finish("fainted", events)

    def _spawn_school(self):
        """Sinh MỘT đàn theo TICKET-02 mục 1.1 "Sinh cá"; trả dict hoặc None nếu hết điểm.

        Điểm hợp lệ: cặp (loài, x ∈ fish_spawn_x, d ∈ fish_spawn_depths[loài]) cách mọi đàn đang sống
        > fish_spawn_clearance. Chọn loài theo fish_weights, chuẩn hóa lại trên các loài còn điểm,
        rồi chọn đều một điểm của loài, hướng ban đầu đều trong [0, 360). Luồng RNG riêng "fish_spawn".
        Dùng chung cho 8 đàn đầu ca và lịch sinh mỗi fish_spawn_ticks (lát cá bơi/sinh gọi lại hàm này).
        """
        t = self.t
        clearance = t["fish_spawn_clearance"]
        valid = {}
        for kind in sorted(t["fish_weights"]):
            pts = [[float(x), float(d)] for x in t["fish_spawn_x"] for d in t["fish_spawn_depths"][kind]
                   if all(math.dist([x, d], f["pos"]) > clearance for f in self.fish)]
            if pts and t["fish_weights"][kind] > 0:
                valid[kind] = pts
        if not valid:
            return None
        rng = self.rng.get("fish_spawn")
        kinds = sorted(valid)
        total = sum(t["fish_weights"][k] for k in kinds)
        r, acc, kind = rng.random() * total, 0.0, kinds[-1]
        for k in kinds:
            acc += t["fish_weights"][k]
            if r < acc:
                kind = k
                break
        pos = valid[kind][rng.randrange(len(valid[kind]))]
        heading = rng.random() * 360.0
        return {"id": self.ids.new("F"), "kind": kind, "pos": pos, "heading_deg": heading, "age_ticks": 0}

    @staticmethod
    def _reflect_axis(val, comp, lo, hi):
        """Phản xạ 1 trục qua [lo, hi]; trả (vị_trí_mới, thành_phần_hướng_mới)."""
        while val < lo or val > hi:
            if val < lo:
                val = lo + (lo - val)
                comp = -comp
            elif val > hi:
                val = hi - (val - hi)
                comp = -comp
        if (val == lo and comp < 0) or (val == hi and comp > 0):
            comp = -comp
        return val, comp

    def _swim_fish(self):
        """Cá bơi 1.5 m/s, đổi hướng tại bước bơi 120, 240… (age_ticks), phản xạ mép."""
        t = self.t
        speed = t["fish_speed"] / self.tick_hz
        turn_ticks = t["fish_turn_ticks"]
        x_lo, x_hi = t["fish_x"]
        depths = t["fish_depths"]
        rng = self.rng.get("fish_move")
        for f in sort_by_id(self.fish):
            f["age_ticks"] += 1
            if f["age_ticks"] % turn_ticks == 0:
                f["heading_deg"] = rng.random() * 360.0
            rad = math.radians(f["heading_deg"])
            vx, vd = math.cos(rad), math.sin(rad)
            nx, vx = self._reflect_axis(f["pos"][0] + vx * speed, vx, x_lo, x_hi)
            d_lo, d_hi = depths[f["kind"]]
            nd, vd = self._reflect_axis(f["pos"][1] + vd * speed, vd, d_lo, d_hi)
            f["pos"] = [nx, nd]
            f["heading_deg"] = math.degrees(math.atan2(vd, vx)) % 360.0

    def _maybe_spawn_fish(self, events):
        """Tại phase_tick = 360·k (k ≥ 1), sinh tối đa 1 đàn nếu < fish_max; tham gia từ bước sau."""
        if self.phase_tick % self.t["fish_spawn_ticks"] != 0:
            return
        if len(self.fish) >= self.t["fish_max"]:
            return
        school = self._spawn_school()
        if school is not None:
            self.fish.append(school)
            events.append(("fish_spawned", {"id": school["id"], "kind": school["kind"], "pos": list(school["pos"])}))

    def _at_surface(self) -> bool:
        return self.pos[1] <= self.t["surface_depth"]

    def _in_dock(self) -> bool:
        return math.dist(self.pos, self.t["dock_pos"]) <= self.t["dock_radius"]

    def _nearest(self, items, radius):
        """Phần tử gần nhất trong bán kính (tính cả đúng mép), hòa theo id_key; không có -> None."""
        best, best_key = None, None
        for e in items:
            d = math.dist(self.pos, e["pos"])
            if d <= radius:
                key = (d, id_key(e["id"]))
                if best_key is None or key < best_key:
                    best, best_key = e, key
        return best

    def _free(self) -> int:
        return self.t["hold_capacity"] - len(self.hold)

    def _harvest(self, events):
        """Hái nút ready gần nhất trong interact_radius: gather hoặc hold_full."""
        ready = [n for n in self.nodes if n["regrow_ticks"] == 0]
        n = self._nearest(ready, self.t["interact_radius"])
        if n is None:
            return
        amount = self.t["node_yield"]
        free = self._free()
        if free < amount:
            events.append(("hold_full", {"action": "gather", "node_id": n["id"], "required": amount, "free": free}))
            return
        self.hold.extend([n["kind"]] * amount)
        n["regrow_ticks"] = int(round(self.t["regrow_s"] * TICK))
        events.append(("gather", {"node_id": n["id"], "kind": n["kind"], "amount": amount}))

    def _catch(self, events):
        """Bắt đúng một đàn gần nhất trong catch_radius: fish_caught hoặc hold_full (không thử đàn khác)."""
        f = self._nearest(self.fish, self.t["catch_radius"])
        if f is None:
            return  # không có đàn trong tầm: không event, không hồi chiêu
        amount = self.t["fish_yield"][f["kind"]]
        free = self._free()
        if free < amount:
            events.append(("hold_full", {"action": "catch", "fish_id": f["id"], "required": amount, "free": free}))
            return
        self.hold.extend([f["kind"]] * amount)
        self.fish = [x for x in self.fish if x["id"] != f["id"]]
        self.catch_cd_ticks = int(round(self.t["catch_cooldown_s"] * TICK))
        events.append(("fish_caught", {"fish_id": f["id"], "kind": f["kind"], "yield": amount}))

    def _finish(self, reason, events):
        self.done = True
        self.reason = reason
        events.append(("gather_end", {"reason": reason, "inventory": {"items": self.inventory_items()}}))

    def _move(self, inp):
        speed = self.t["swim_speed"]
        mx, md = inp.move
        self.vel = ramp_velocity(self, (mx * speed, md * speed), int(self.t["ramp_max_ticks"]))
        if (mx, md) != (0.0, 0.0):
            self.heading = math.degrees(math.atan2(md, mx)) % 360
        b = self.t["bounds"]
        for i, axis in enumerate(AXES):
            self.pos[i] += self.vel[i] / self.tick_hz
            lo, hi = b[axis]
            if self.pos[i] <= lo:
                self.pos[i] = lo
                self.vel[i] = max(0.0, self.vel[i])
            elif self.pos[i] >= hi:
                self.pos[i] = hi
                self.vel[i] = min(0.0, self.vel[i])
