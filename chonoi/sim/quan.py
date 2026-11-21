"""Buổi tối — Mở Quán. KHUNG: đi lại, chặn biên, đồng hồ, kho nạp từ file/scenario.

Nhóm viết tiếp (PRD-0 mục F, Quán):
  Lát 3 (minhtriet061203) — ĐÃ LÀM: khách đến theo lịch, chọn món nấu được, giữ chỗ nguyên liệu,
                     kiên nhẫn, bỏ đi (customer_left patience/closing), no_dish, khách dựng từ scenario.
  TODO(nhóm, lát 4): interact tại bếp/bàn (cook_started, dish_ready, dish_picked, served),
                     ăn xong trả tiền (paid finished_eating/closing), boa, uy tín.

Cấu trúc khách: PRD-0 mục D + docs/contracts/README.md mục 4 (order_id = id khách):
  {"id","table_id","dish_id","order_tick","state","patience_ticks_left","eat_ticks_left",
   "order_status","reserved","base_price","tip"}
  state: waiting -> eating; order_status: reserved (lát 3) -> assigned -> served (lát 4); unfulfillable (fixture).
Kho khả dụng = tồn (`stock`) − tổng `reserved` của mọi khách (xem `available()`).
Phase 3 (lát 3, v1.2 — bật khi tuning có `freshness`): stock là mảng cá thể {id, kind, fresh_units}, hao
  quan_per_tick mỗi bước kể cả hàng giữ, `spoiled` (location stock) theo id; customers[].reserved là mảng id
  (tươi nhất, hòa id); phần giữ vừa ươn -> nhả, giữ lại đúng một lần, thiếu -> unfulfillable.
Phase 2 (lát 3): `menu_filter` = id món trong day_plan[day].dishes (--mode day) — lọc kế hoạch TRƯỚC kho khả dụng;
  None = quán độc lập dùng cả menu. money/earned/reputation đầu ca do runner day truyền vào.
"""

import math

from ..ids import id_key, sort_by_id
from ..errors import BadInput
from ..items import (Freshness, ItemIds, decay, from_public, is_spoiled, is_v12, pick_freshest,
                     price_by_fresh, public, public_list)
from .ramp import ramp_velocity

TICK = 60.0
RNG_CUSTOMERS = "customers"  # luồng RNG riêng cho việc chọn món (clarify G1)
CUSTOMER_FIELDS = ("id", "table_id", "dish_id", "order_tick", "state", "patience_ticks_left", "eat_ticks_left",
                   "order_status", "reserved", "base_price", "tip")


class QuanSim:
    mode = "quan"
    phase = "quan"

    def __init__(self, tuning, scenario, streams, ids, inventory=None, menu_filter=None,
                 money=0, earned=0, reputation=None, item_ids=None):
        # v1.2: bộ cấp id cá thể dùng chung cả lượt (`day` truyền vào; chạy riêng thì tự tạo)
        self.item_ids = item_ids if item_ids is not None else ItemIds()
        """menu_filter: id món trong day_plan[day].dishes (chỉ dùng ở --mode day; None = quán độc lập, đủ menu).
        money/earned/reputation: trạng thái xuyên Ngày do runner day truyền vào (hợp đồng mục 5.3)."""
        t = tuning["quan"]
        self.t = t
        self.menu = tuning["menu"]
        self.plan_dishes = None if menu_filter is None else sorted(set(menu_filter))
        if self.plan_dishes is not None:
            from ..errors import BadInput
            unknown = [d for d in self.plan_dishes if d not in self.menu]
            if unknown:
                raise BadInput(f"day_plan có món ngoài menu: {unknown}")
        self.rng = streams
        self.ids = ids
        p = scenario.get("player", {})
        self.pos = list(p.get("pos", t["start_pos"]))
        self.vel = [float(c) for c in p.get("vel", [0.0, 0.0])]
        self._tgt = None
        self._ramp_left = 0
        # kho: --inventory HOẶC scenario.stock (cả hai -> cli đã báo mã 2)
        self.v12 = is_v12(tuning)
        self.fr = Freshness(tuning) if self.v12 else None
        if self.v12:  # mảng cá thể nội bộ; scenario.stock là dạng công khai {id, kind, fresh}
            src = inventory if inventory is not None else scenario.get("stock", [])
            if src == {}:  # gather bàn giao kho rỗng dạng đếm (vd. ngất) -> không có cá thể nào
                src = []
            if not isinstance(src, list):
                raise BadInput("contract v1.2: kho quán phải là mảng cá thể")
            self.stock = [dict(it) if "fresh_units" in it else from_public(it) for it in src]
            for it in self.stock:
                self.item_ids.reserve(it["id"])
        else:
            self.stock = dict(inventory if inventory is not None else scenario.get("stock", {}))
        self.hand = scenario.get("hand")
        self.time_left_ticks = scenario.get("time_left_ticks", int(round(t["duration_s"] * 60)))
        if reputation is None:
            reputation = scenario.get("reputation", t["reputation_initial"])
        self.reputation = reputation
        self.stoves = [dict(s, state=s.get("state", "idle"), dish=s.get("dish"),
                            cook_ticks_left=s.get("cook_ticks_left", 0), ready_ticks=s.get("ready_ticks", 0))
                       for s in self._merge(t["stoves"], scenario.get("stoves", []))]
        self.tables = self._merge(t["tables"], scenario.get("tables", []))
        # lịch khách (theo phase_tick, đếm từ 0 ở đầu ca)
        self.phase_tick = 0
        self.first_customer_tick = int(t["first_customer_tick"])
        self.customer_interval_ticks = max(1, int(round(t["customer_interval_s"] * 60)))
        self.patience_ticks = int(round(t["patience_s"] * 60))
        self.random_customers = scenario.get("random_customers", True)
        # khách dựng sẵn từ scenario: giữ id, suy ra giữ chỗ
        fixture = scenario.get("customers", [])
        for c in fixture:
            ids.reserve(c["id"])
        self.customers = [self._customer_from_fixture(c) for c in sort_by_id(fixture)]
        if self.v12:
            self._fixture_reservations_v12({c["id"]: c for c in fixture})
        else:
            self._check_reserved_fits_stock()
        self._check_plan_fixture()
        self.money = money
        self.earned = earned
        self.shift_earned = 0
        self.done = False
        self.reason = None

    @staticmethod
    def _merge(defaults, updates):
        by_id = {d["id"]: dict(d) for d in defaults}
        for u in updates:
            if u["id"] not in by_id:
                from ..errors import BadInput
                raise BadInput(f"id bếp/bàn không tồn tại: {u['id']}")
            by_id[u["id"]].update(u)
        return sort_by_id(list(by_id.values()))

    # ---------- khách: dựng từ scenario ----------

    def _new_customer(self, cid, table_id, dish_id, order_tick, reserved=None):
        if reserved is None:
            reserved = [] if self.v12 else dict(self.menu[dish_id]["recipe"])
        return {"id": cid, "table_id": table_id, "dish_id": dish_id, "order_tick": order_tick,
                "state": "waiting", "patience_ticks_left": self.patience_ticks, "eat_ticks_left": 0,
                "order_status": "reserved", "reserved": reserved,
                "base_price": 0, "tip": 0}

    def _customer_from_fixture(self, c):
        cust = self._new_customer(c["id"], c["table_id"], c["dish_id"], c.get("order_tick", 0))
        if c.get("state", "waiting") == "eating":
            cust.update(state="eating", order_status="served")
        for k in ("patience_ticks_left", "eat_ticks_left", "order_status", "base_price", "tip"):
            if k in c:
                cust[k] = c[k]
        if cust["order_status"] != "reserved":
            cust["reserved"] = [] if self.v12 else {}
        return cust

    def _fixture_reservations_v12(self, raw_by_id):
        """TICKET-03 (Scenario): reserved là mảng id trỏ tới cá thể chưa ươn trong kho, đủ đúng công thức,
        không dùng chung giữa các đơn. Đơn reserved bỏ trống reserved -> cấp theo (order_tick, id bàn),
        tươi nhất rồi id nhỏ, sau khi đã đặt các phần giữ tường minh. Sai/thiếu -> BadInput (mã 2)."""
        by_id = {it["id"]: it for it in self.stock}
        taken, pending = set(), []
        for c in self.customers:
            raw = raw_by_id[c["id"]].get("reserved")
            if c["order_status"] != "reserved":
                if raw:
                    raise BadInput(f"customers.{c['id']}: đơn {c['order_status']} không giữ chỗ nguyên liệu")
                continue
            if raw is None:
                pending.append(c)
                continue
            counts = {}
            for iid in raw:
                it = by_id.get(iid)
                if it is None:
                    raise BadInput(f"customers.{c['id']}.reserved: {iid!r} không có trong kho quán")
                if iid in taken:
                    raise BadInput(f"customers.{c['id']}.reserved: {iid} đã được đơn khác giữ")
                if is_spoiled(it, self.fr):
                    raise BadInput(f"customers.{c['id']}.reserved: {iid} đã ươn")
                taken.add(iid)
                counts[it["kind"]] = counts.get(it["kind"], 0) + 1
            if counts != dict(self.menu[c["dish_id"]]["recipe"]):
                raise BadInput(f"customers.{c['id']}.reserved: giữ khác công thức {self.menu[c['dish_id']]['recipe']}")
            c["reserved"] = sorted(raw, key=id_key)
        for c in sorted(pending, key=lambda c: (c["order_tick"], id_key(c["table_id"]))):
            ids = self._pick_recipe(c["dish_id"], taken)
            if ids is None:
                raise BadInput(f"customers.{c['id']}: kho không đủ cá thể chưa ươn để giữ {c['dish_id']}")
            c["reserved"] = ids
            taken.update(ids)

    def _check_reserved_fits_stock(self):
        """Mâu thuẫn: khách giữ chỗ nhiều hơn tồn kho (kho có thể đến từ --inventory) -> mã 2."""
        from ..errors import BadInput
        need = self._reserved_total()
        for k in sorted(need):
            if need[k] > self.stock.get(k, 0):
                raise BadInput(f"khách giữ chỗ {need[k]} {k} nhưng kho chỉ có {self.stock.get(k, 0)}")

    def _check_plan_fixture(self):
        """TICKET-02 mục 4.3: trong day, khách/bếp/tay dựng sẵn phải thuộc món trong kế hoạch -> sai thì mã 2."""
        if self.plan_dishes is None:
            return
        from ..errors import BadInput
        dishes = [("customers." + c["id"], c["dish_id"]) for c in self.customers]
        dishes += [("stoves." + s["id"], s["dish"].get("dish_id")) for s in self.stoves if isinstance(s.get("dish"), dict)]
        if isinstance(self.hand, dict):
            dishes.append(("hand", self.hand.get("dish_id")))
        for name, dish_id in dishes:
            if dish_id not in self.plan_dishes:
                raise BadInput(f"{name}: món {dish_id!r} không thuộc kế hoạch Ngày {self.plan_dishes}")

    # ---------- kho khả dụng / giữ chỗ ----------

    def _reserved_total(self) -> dict:
        tot = {}
        for c in self.customers:
            for k, n in c["reserved"].items():
                tot[k] = tot.get(k, 0) + n
        return tot

    def _reserved_ids(self) -> set:
        return {iid for c in self.customers for iid in c["reserved"]} if self.v12 else set()

    def available(self) -> dict:
        """Kho khả dụng theo loại. v1.1: tồn − đang giữ. v1.2: số cá thể chưa ươn và chưa bị đơn nào giữ."""
        if self.v12:
            taken, counts = self._reserved_ids(), {}
            for it in self.stock:
                if it["id"] not in taken and not is_spoiled(it, self.fr):
                    counts[it["kind"]] = counts.get(it["kind"], 0) + 1
            return counts
        res = self._reserved_total()
        return {k: max(0, self.stock.get(k, 0) - res.get(k, 0)) for k in set(self.stock) | set(res)}

    def _pick_recipe(self, dish_id, exclude):
        """v1.2: mỗi loại trong công thức lấy cá thể khả dụng tươi nhất, hòa theo id. Thiếu -> None."""
        ids = []
        for kind, n in sorted(self.menu[dish_id]["recipe"].items()):
            got = pick_freshest(self.stock, kind, n, self.fr, exclude=exclude)
            if not got:
                return None
            ids += [it["id"] for it in got]
        return sorted(ids, key=id_key)

    def _decay_stock(self, events):
        """v1.2 (quán): hao tươi kho thô (kể cả hàng giữ), phát HẾT spoiled theo id, RỒI xử lý từng đơn có phần
        giữ vừa ươn theo (order_tick, id bàn): nhả toàn bộ, giữ lại đúng một lần; thiếu -> unfulfillable."""
        if not self.v12:
            return
        newly = decay(self.stock, self.fr.quan_per_tick, self.fr)
        for it in newly:
            events.append(("spoiled", {"item_id": it["id"], "kind": it["kind"], "location": "stock"}))
        bad = {it["id"] for it in newly}
        hit = [c for c in self.customers if c["order_status"] == "reserved" and bad.intersection(c["reserved"])]
        for c in sorted(hit, key=lambda c: (c["order_tick"], id_key(c["table_id"]))):
            c["reserved"] = []
            ids = self._pick_recipe(c["dish_id"], self._reserved_ids())
            if ids is None:
                c["order_status"] = "unfulfillable"
            else:
                c["reserved"] = ids

    def _cookable_dishes(self) -> list:
        """Ứng viên chọn món, theo id món (mã Unicode). Trong day: lọc theo kế hoạch TRƯỚC, rồi mới lọc
        theo kho khả dụng (TICKET-02 mục 4.5). Không giới hạn số suất: đủ nguyên liệu là gọi tiếp được."""
        candidates = sorted(self.menu) if self.plan_dishes is None else self.plan_dishes
        avail = self.available()
        return [d for d in candidates
                if all(avail.get(k, 0) >= n for k, n in self.menu[d]["recipe"].items())]

    # ---------- uy tín / rời quán (dùng chung với lát 4) ----------

    def _add_reputation(self, delta):
        lo, hi = self.t["reputation_min"], self.t["reputation_max"]
        self.reputation = round(min(hi, max(lo, self.reputation + delta)), 6)

    def _release(self, c):
        """Hợp đồng mục 4: khách rời -> nhả phần giữ, bỏ món của đơn ở bếp (về idle) hoặc trên tay."""
        c["reserved"] = [] if self.v12 else {}
        for s in self.stoves:
            if isinstance(s.get("dish"), dict) and s["dish"].get("order_id") == c["id"]:
                s.update(state="idle", dish=None, cook_ticks_left=0, ready_ticks=0)
        if isinstance(self.hand, dict) and self.hand.get("order_id") == c["id"]:
            self.hand = None
        self.customers = [x for x in self.customers if x["id"] != c["id"]]

    def _customer_left(self, c, reason, events, rep_delta=0.0):
        """Khách rời: _release, đổi uy tín (kẹp), customer_left mang uy tín SAU khi đổi (clarify #3)."""
        self._release(c)
        if rep_delta:
            self._add_reputation(rep_delta)
        events.append(("customer_left", {"order_id": c["id"], "table_id": c["table_id"], "reason": reason,
                                         "reputation": self.reputation}))

    # ---------- bước ----------

    def snapshot(self) -> dict:
        occupied = {c["table_id"]: c["id"] for c in self.customers}
        return {
            "player": {"pos": self.pos},
            "stock": (public_list(self.stock, by_id=True) if self.v12
                      else {k: self.stock[k] for k in sorted(self.stock) if self.stock[k] > 0}),
            "hand": self.hand,
            "stoves": [{k: s.get(k) for k in ("id", "pos", "state", "dish", "cook_ticks_left", "ready_ticks")}
                       for s in self.stoves],
            "tables": [{"id": tb["id"], "pos": tb["pos"], "customer_id": occupied.get(tb["id"])} for tb in self.tables],
            "customers": [{k: (self._public_reserved(c[k]) if k == "reserved" else c[k])
                           for k in CUSTOMER_FIELDS} for c in sort_by_id(self.customers)],
        }

    @staticmethod
    def _public_reserved(r):
        return sorted(r, key=id_key) if isinstance(r, list) else {i: r[i] for i in sorted(r)}

    def step(self, inp):
        """Thứ tự theo PRD-0 mục F (Quán), đánh số 1–5 như PRD."""
        events = []
        # 1. đồng hồ, timer ca, nấu, ăn, kiên nhẫn
        self.phase_tick += 1
        self.time_left_ticks = max(0, self.time_left_ticks - 1)
        self._tick_patience()
        self._tick_eating()
        # 1b. v1.2: hao tươi kho thô, spoiled theo id, rồi giữ lại cho đơn có hàng vừa ươn
        self._decay_stock(events)
        # 2. xét bếp theo id: món nấu xong -> ready (ready_ticks = 0)
        self._tick_cooking(events)
        # 3. di chuyển rồi tối đa MỘT interact (phục vụ ở bước cuối ca vẫn hợp lệ)
        self._move(inp)
        self._interact(inp, events)
        # 4. theo id bàn: ăn xong trả tiền / hết kiên nhẫn / hết ca (closing); dọn xong -> quan_end
        self._settle_tables(events)
        if self.time_left_ticks <= 0:
            self.done = True
            self.reason = "time"
            events.append(("quan_end", {"reason": "time", "money": self.money, "earned": self.earned,
                                        "shift_earned": self.shift_earned, "reputation": self.reputation}))
            return events
        # 5. còn giờ: lượt khách mới
        self._spawn_customer(events)
        return events

    def _distance(self, pos):
        return math.hypot(self.pos[0] - pos[0], self.pos[1] - pos[1])

    def _tick_cooking(self, events):
        for stove in self.stoves:
            if stove["state"] == "ready":
                stove["ready_ticks"] += 1
            elif stove["state"] != "cooking":
                continue
            else:
                stove["cook_ticks_left"] = max(0, stove["cook_ticks_left"] - 1)
                if stove["cook_ticks_left"] == 0:
                    stove["state"] = "ready"
                    stove["ready_ticks"] = 0
                    dish = stove["dish"]
                    events.append(("dish_ready", {"stove_id": stove["id"], "order_id": dish["order_id"],
                                                   "dish_id": dish["dish_id"]}))

    def _cook_at(self, stove, events) -> bool:
        """Bếp idle được interact: lấy đơn reserved cũ nhất (order_tick, id bàn), tiêu nguyên liệu giữ, chốt giá."""
        orders = [c for c in self.customers if c["state"] == "waiting" and c["order_status"] == "reserved"]
        if not orders:
            return False
        customer = min(orders, key=lambda c: (c["order_tick"], id_key(c["table_id"])))
        dish_id = customer["dish_id"]
        recipe = self.menu[dish_id]["recipe"]
        if self.v12:  # tiêu đúng các id đang giữ; giá chốt theo trung bình fresh (TICKET-03)
            held = set(customer["reserved"])
            used = [it for it in self.stock if it["id"] in held]
            self.stock = [it for it in self.stock if it["id"] not in held]
            items = [public(it) for it in sorted(used, key=lambda it: (it["kind"], id_key(it["id"])))]
            base_price = price_by_fresh(self.menu[dish_id]["price"], used)
            customer["reserved"] = []
            customer["order_status"] = "assigned"
        else:
            items = {kind: customer["reserved"].get(kind, 0) for kind in sorted(recipe)}
            for kind, count in items.items():
                self.stock[kind] = max(0, self.stock.get(kind, 0) - count)
            customer["reserved"] = {}
            customer["order_status"] = "assigned"
            base_price = self.menu[dish_id]["price"]
        customer["base_price"] = base_price
        dish = {"order_id": customer["id"], "dish_id": dish_id, "base_price": base_price}
        stove.update(state="cooking", dish=dish,
                     cook_ticks_left=int(round(self.menu[dish_id]["cook_s"] * TICK)), ready_ticks=0)
        events.append(("cook_started", {"stove_id": stove["id"], "order_id": customer["id"],
                       "dish_id": dish_id, "items": items, "base_price": base_price}))
        return True

    def _interact(self, inp, events):
        """PRD-0 mục F: tối đa MỘT interact, chọn đối tượng gần nhất theo (khoảng cách, bếp trước bàn, id).
        Đối tượng được chọn không tương tác được thì bỏ lượt (không thử đối tượng khác)."""
        if not inp.pressed("interact"):
            return
        radius = self.t["interact_radius"]
        candidates = [(self._distance(st["pos"]), 0, id_key(st["id"]), "stove", st) for st in self.stoves]
        candidates += [(self._distance(tb["pos"]), 1, id_key(tb["id"]), "table", tb) for tb in self.tables]
        candidates = [c for c in candidates if c[0] <= radius]
        if not candidates:
            return
        _, _, _, target_type, obj = min(candidates, key=lambda c: c[:3])
        if target_type == "stove":
            stove = obj
            if stove["state"] == "idle":
                self._cook_at(stove, events)
            elif stove["state"] == "ready" and self.hand is None:
                dish = dict(stove["dish"])
                self.hand = dish
                stove.update(state="idle", dish=None, cook_ticks_left=0, ready_ticks=0)
                events.append(("dish_picked", {"stove_id": stove["id"], "order_id": dish["order_id"],
                                               "dish_id": dish["dish_id"]}))
            return
        table = obj
        customer = next((c for c in self.customers if c["table_id"] == table["id"]), None)
        if (customer is None or customer["state"] != "waiting" or customer["order_status"] != "assigned"
                or not isinstance(self.hand, dict) or self.hand.get("order_id") != customer["id"]):
            return
        target = (table, customer)
        table, customer = target
        dish = self.hand
        base_price = dish["base_price"]
        patience_left = customer["patience_ticks_left"]
        tip_threshold = self.patience_ticks * self.t["tip_min_patience_ratio"]
        tip = math.floor(base_price * self.t["tip_rate"]) if patience_left >= tip_threshold else 0
        customer.update(state="eating", order_status="served", base_price=base_price, tip=tip,
                        eat_ticks_left=int(round(self.t["eat_s"] * TICK)))
        self.hand = None
        events.append(("served", {"order_id": customer["id"], "table_id": table["id"], "dish_id": dish["dish_id"],
                                   "patience_ticks_left": patience_left, "base_price": base_price, "tip": tip}))

    def _tick_eating(self):
        for customer in sort_by_id(self.customers):
            if customer["state"] != "eating":
                continue
            customer["eat_ticks_left"] = max(0, customer["eat_ticks_left"] - 1)

    def _pay(self, customer, events, reason):
        base_price = customer["base_price"]
        tip = customer["tip"]
        amount = base_price + tip
        self.money += amount
        self.earned += amount
        self.shift_earned += amount
        if tip > 0:
            self._add_reputation(self.t["tip_reputation"])
        events.append(("paid", {"order_id": customer["id"], "table_id": customer["table_id"],
                                 "base_price": base_price, "tip": tip, "amount": amount, "reason": reason}))
        self.customers = [c for c in self.customers if c["id"] != customer["id"]]

    def _tick_patience(self):
        """Step 1: giảm kiên nhẫn; việc rời bàn được xử lý sau tương tác."""
        for customer in sort_by_id(self.customers):
            if customer["state"] == "waiting":
                customer["patience_ticks_left"] = max(0, customer["patience_ticks_left"] - 1)

    def _settle_tables(self, events):
        """Step 4: settle theo id bàn sau khi người chơi có thể phục vụ trong tick này."""
        closing = self.time_left_ticks <= 0
        for customer in sorted(self.customers, key=lambda c: id_key(c["table_id"])):
            if customer["state"] == "eating":
                if closing:
                    self._pay(customer, events, "closing")
                elif customer["eat_ticks_left"] == 0:
                    self._pay(customer, events, "finished_eating")
            elif closing:
                self._customer_left(customer, "closing", events)
            elif customer["patience_ticks_left"] == 0:
                self._customer_left(customer, "patience", events, rep_delta=self.t["left_reputation_delta"])

    def _is_arrival_tick(self) -> bool:
        k = self.phase_tick - self.first_customer_tick
        return k >= 0 and k % self.customer_interval_ticks == 0

    def _spawn_customer(self, events):
        """Đúng lịch: bàn trống id nhỏ nhất; không bàn -> bỏ lượt; không món nấu được -> no_dish."""
        if not self.random_customers or not self._is_arrival_tick():
            return
        occupied = {c["table_id"] for c in self.customers}
        free = [tb for tb in self.tables if tb["id"] not in occupied]  # self.tables đã sort_by_id
        if not free:
            return
        table = free[0]
        options = self._cookable_dishes()
        if not options:
            events.append(("no_dish", {}))
            return
        dish_id = options[self.rng.get(RNG_CUSTOMERS).randrange(len(options))]
        reserved = self._pick_recipe(dish_id, self._reserved_ids()) if self.v12 else None
        c = self._new_customer(self.ids.new("C"), table["id"], dish_id, self.phase_tick, reserved)
        self.customers.append(c)
        events.append(("customer_arrived", {"order_id": c["id"], "table_id": c["table_id"], "dish_id": dish_id}))

    def _move(self, inp):
        speed = self.t["walk_speed"]
        mx, mz = inp.move
        self.vel = ramp_velocity(self, (mx * speed, mz * speed), int(self.t.get("ramp_max_ticks", 6)))
        b = self.t["bounds"]
        for i, axis in enumerate(("x", "z")):
            self.pos[i] += self.vel[i] / TICK
            lo, hi = b[axis]
            if self.pos[i] <= lo:
                self.pos[i], self.vel[i] = lo, max(0.0, self.vel[i])
            elif self.pos[i] >= hi:
                self.pos[i], self.vel[i] = hi, min(0.0, self.vel[i])
