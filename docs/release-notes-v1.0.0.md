# Quán Ăn Chợ Nổi v1.0.0 — nhóm StoneAsterisk

Game 2D quản lý quán ăn miền Tây: sáng Út Sen lặn bắt cá, hái bông trên sông; tối nấu và phục vụ khách trên nhà bè; cuối ngày mua nâng cấp ở Shop. Bản phát hành cuối buổi lab Day 12 (AI SDLC), **Test Contract v1.3**.

## Cách chạy

Yêu cầu: Python 3 (chỉ thư viện chuẩn, không cài thêm), `git`, một trình duyệt.

```bash
git clone https://github.com/nglngnguyen-gh/K5-L3B-LAB-Day12-AI-SDLC-StoneAsterisk.git
cd K5-L3B-LAB-Day12-AI-SDLC-StoneAsterisk
python3 -m chonoi.live --mode gather      # mở http://127.0.0.1:8000/  (buổi tối: --mode quan)
```

Hoặc tải `quan-an-cho-noi-v1.0.0.zip` ở mục Assets, giải nén, rồi chạy lệnh thứ ba trong thư mục vừa giải nén.

Phím: **WASD / mũi tên** di chuyển · **E** cập bến / hái / nấu / bưng / phục vụ · **Space** bắt cá · **R** chơi lại · **H** tương phản cao.

Test và lệnh máy chấm:

```bash
PYTHONPATH=tests:. python3 -m unittest discover -s tests -v
python3 -m chonoi.headless --mode day --seed 1 --days 5 --ticks 120000 --out out.jsonl
python3 -m chonoi.bench --seed 42 --duration 30 --out bench.json
python3 -m chonoi.soak  --seed 7  --days 10    --out soak.json
```

## Điểm mới theo phase

- **Phase 1 (v1.0):** lõi buổi sáng (bơi, oxy, ngạt, Máu, ngất, giỏ LIFO, hái, bắt cá, cập bến) và buổi tối (khách theo lịch, giữ chỗ nguyên liệu, kiên nhẫn, bếp, bưng, phục vụ, boa, uy tín); file kho bàn giao giữa hai tiến trình headless; JSONL tất định.
- **Phase 2 (v1.1):** số chuẩn TICKET-02, 6 nguyên liệu / 6 món, cá bơi và sinh theo seed, Cá Sấu Năm Chèo (tuần tra, đuổi, chạm, lùi), 2 bếp / 4 bàn, `--mode day` (kế hoạch D1–D5, Shop nâng cấp oxy / Máu, pause).
- **Phase 3 (v1.2, breaking):** kho **cá thể** `{id, kind, fresh}` thay kho đếm; độ tươi hao trong giỏ và kho, hàng ươn (< 30) không dùng nấu, giữ chỗ theo id tươi nhất, giữ lại khi hàng vừa ươn, giá theo độ tươi; HUD hiện độ tươi. Cách sửa fixture: `CHANGELOG.md`.
- **Phase 4 (v1.3):** `bench_cmd`, `soak_cmd`; ba cảnh báo có chữ + biểu tượng (thủy quái gần, oxy sắp hết, khách sắp giận) và chế độ tương phản cao.
- **Mở rộng:** `burn` — món chín quá 20 s thì cháy, thử giữ lại nguyên liệu cho đơn.

## Kiểm chứng trên commit phát hành

Ma trận truy vết từng phase: `docs/verification/phase-1.md` … `phase-4.md`; bằng chứng chạy: `docs/proof/phase-4/final/` (unittest, smoke, tất định, soak 10 Ngày, bench).

## Giới hạn đã biết

- **Bench** đo vòng 60 Hz phía máy (bước mô phỏng + snapshot + JSON trạng thái mà trang web vẽ), **không đo phần vẽ canvas 1280×720 của trình duyệt**. 1% low dao động theo máy (Windows: 32.9–51.7).
- **Soak** dùng bot tất định đơn giản (cập bến ngay, không phục vụ) nên mọi Ngày cùng điểm 300: chứng minh 10 Ngày không lỗi và lặp lại được, không thử luật gameplay sâu.
- **Cửa sổ chơi** chưa có menu chính, DayIntro / EveningIntro / DayResult / Summary, giao diện Shop và menu pause (AC-P2-45): `--mode day` chạy đầy đủ ở headless, giao diện chơi từng buổi `gather` / `quan`.
- Chỉ thử clone sạch trên Windows (git bash + `python3`); nhóm không có máy macOS / Linux.
- Mở rộng `current` (dòng nước lũ), `reservations` (khách đặt trước), `leaderboard`, phụ đề SFX chưa làm; chưa có âm thanh.
- Một số giả định khi đề chưa rõ ghi ở `docs/clarify.md` (ví dụ #13: nút `attack` khi chưa bật mở rộng được bỏ qua).

## Nhóm

nglngnguyen-gh (PO, Integrator, QA lead) · LyLe10 · BLong1501 · minhtriet061203 · len2412 — vai và đóng góp: `TEAM.md`, `docs/members/`, ma trận từng phase.
