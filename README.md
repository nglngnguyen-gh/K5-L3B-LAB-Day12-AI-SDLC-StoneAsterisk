# Quán Ăn Chợ Nổi — nhóm StoneAsterisk

Game 2D quản lý quán ăn miền Tây (Day 12 · AI SDLC). Buổi sáng Út Sen lặn bắt cá, hái bông trên sông Chín Khúc; buổi tối nấu và phục vụ khách trên nhà bè của Má Tư. Thứ mang về từ buổi sáng quyết định quán bán được món nào.

Nhóm: xem [`TEAM.md`](TEAM.md) · Kế hoạch: [`docs/plan/`](docs/plan/) · Hợp đồng tích hợp: [`docs/contracts/`](docs/contracts/README.md) · Kiểm chứng: [`docs/verification/`](docs/verification/) · Thay đổi: [`CHANGELOG.md`](CHANGELOG.md) · Giấy phép: [`LICENSE`](LICENSE) · Nguồn tài sản: [`CREDITS.md`](CREDITS.md)

Phiên bản: **v1.0.0**, Test Contract **v1.3** (gameplay, tuning, kho và JSONL theo v1.2: nguyên liệu là cá thể có độ tươi).

## Yêu cầu môi trường

- **Python 3** (nhóm đã chạy với 3.12), **chỉ thư viện chuẩn**: không `pip install`, không bước build (`build_cmd` là `true`).
- `git` và một trình duyệt bất kỳ (giao diện là trang web do `chonoi.live` phục vụ tại `127.0.0.1`).
- macOS / Linux dùng `python3`. Trên Windows nếu không có lệnh `python3` thì thay bằng `python` (hoặc `py -3`) để chơi. Riêng bộ test hộp đen gọi đúng lệnh `python3` (`headless_cmd` trong manifest), nên cần có `python3` trên PATH (ví dụ một bản sao `python.exe` đặt tên `python3.exe`), và đổi `PYTHONPATH=tests:.` thành `PYTHONPATH=tests;.` (PowerShell: `$env:PYTHONPATH="tests;."`).

## Chạy từ clone sạch (3 lệnh)

```bash
git clone https://github.com/nglngnguyen-gh/K5-L3B-LAB-Day12-AI-SDLC-StoneAsterisk.git
cd K5-L3B-LAB-Day12-AI-SDLC-StoneAsterisk
python3 -m chonoi.live --mode gather      # mở địa chỉ in ra (mặc định http://127.0.0.1:8000/)
```

Chơi buổi tối: `python3 -m chonoi.live --mode quan`. Nối hai buổi qua file kho: thêm `--inventory-out kho.json` khi chơi `gather`, rồi `--inventory kho.json` khi chơi `quan`.

## Điều khiển

| Phím | Buổi sáng (`gather`) | Buổi tối (`quan`) |
|---|---|---|
| **WASD** / mũi tên | Bơi (S/↓ lặn sâu hơn) | Đi trong nhà bè |
| **E** (`interact`) | Cập bến (kết thúc buổi sáng) hoặc hái nút trên mặt nước | Nấu ở bếp, bưng món, phục vụ bàn |
| **Space** (`catch`) | Bắt đàn cá khi đang lặn | — |
| **R** | Chơi lại | Chơi lại |

Cảnh báo (thủy quái gần, oxy sắp hết, khách sắp giận) và chế độ tương phản cao: xem mục AC-P4-10/11 trong [`docs/verification/phase-4.md`](docs/verification/phase-4.md).

Buổi sáng: oxy giảm khi lặn và hồi khi nổi lên, hết oxy thì ngạt mất Máu (3 Máu), hết Máu thì ngất và mất cả giỏ. Giỏ chứa tối đa 12 nguyên liệu. Buổi tối: khách gọi món nấu được từ kho, bạn nấu → bưng → phục vụ trước khi khách hết kiên nhẫn.

## Cách tính điểm

```
điểm = earned + 100 × floor(uy tín)
```

- `earned`: tổng tiền thu cả lượt (nghìn đồng) = giá món + tiền boa.
- Boa = `floor(giá món × 0.2)` nếu lúc phục vụ khách còn ≥ 50% kiên nhẫn; boa dương cộng 0.2 uy tín.
- Khách bỏ đi vì hết kiên nhẫn: uy tín −0.5. Uy tín bắt đầu 3.0, kẹp trong [0, 5].
- Giá niêm yết (nghìn đồng): gỏi bông súng 40 · cá lóc nướng trui 60 · cá kèo nướng 70 · canh chua cá lóc 90 · lẩu cá linh bông điên điển 120 · lẩu mắm 200. Mỗi Ngày chỉ bán các món trong kế hoạch Ngày (`day_plan`).
- Độ tươi (v1.2): giá chốt lúc bắt đầu nấu = `floor(giá niêm yết × trung bình độ tươi / 100)`; nguyên liệu dưới 30 là ươn, không nấu được.

Mọi số liệu nằm ở [`game.contract.json`](game.contract.json) (Test Contract v1.3).

## Test và headless

```bash
PYTHONPATH=tests:. python3 -m unittest discover -s tests -v
```

Chạy headless (Test Contract v1.3, 60 tick/s, cùng seed → output giống từng byte; input sai → mã 2 trước khi ghi output):

```bash
python3 -m chonoi.headless --mode gather --seed 1 --ticks 600 --out out.jsonl [--inventory-out kho.json]
python3 -m chonoi.headless --mode quan   --seed 1 --ticks 600 --out out.jsonl [--inventory kho.json]
python3 -m chonoi.headless --mode day    --seed 1 --ticks 600 --out out.jsonl [--days 1..5]   # gather → quan → shop
```

Benchmark và soak (Test Contract v1.3, khai ở gốc `game.contract.json` là `bench_cmd` / `soak_cmd`):

```bash
python3 -m chonoi.bench --seed 42 --duration 30 --out bench.json   # cảnh lặn chuẩn, làm nóng 3 s rồi đo 30 s
python3 -m chonoi.soak  --seed 7  --days 10    --out soak.json    # 10 Ngày trong một tiến trình, bot tất định
```

`bench.json` = `{avg_fps, p1_low_fps, frames, measured_s, load_ms}`; bench đo vòng mô phỏng 60 Hz + dựng trạng thái khung hình mà trình duyệt vẽ, **không đo phần vẽ canvas của trình duyệt**. `soak.json` = `{days, days_completed, crashes, results[], duration_s}`. Kết quả trên commit bàn giao: [`docs/proof/phase-4/`](docs/proof/phase-4/).

Kiểm tích hợp và tất định (skill của nhóm, xem [`.agents/skills/`](.agents/skills/)):

```bash
python3 .agents/skills/smoke-hai-tien-trinh/smoke.py     # gather → file kho → quan
python3 .agents/skills/kiem-tat-dinh/kiem_tat_dinh.py    # chạy 2 lần, so từng byte
```

## Sáng tạo của nhóm

### Cháy món quá hạn (`burn`)

- Ý tưởng: món chín để quá 20 giây sẽ cháy, bếp được dọn, nguyên liệu cũ mất; thử giữ lại công thức từ kho. Đủ nguyên liệu thì đơn `reserved`, thiếu thì `unfulfillable` và khách tiếp tục chờ.
- Bật/tắt ở chơi live: trong `game.contract.json`, bật bằng `"extensions": ["burn"]` cùng `"burn_s": 20`; tắt bằng `"extensions": []` cùng `"burn_s": null`. Headless luôn tắt phần sáng tạo để giữ nguyên luật lõi.
- Bằng chứng: `python -m unittest discover -s tests -p "test_quan_service.py" -v` (12 test), `python -m unittest discover -s tests -p "test_python_starter_units.py" -v` (9 test), và `python .agents/skills/kiem-tat-dinh/kiem_tat_dinh.py` (15/15 cặp giống từng byte).

Khi thêm sáng tạo, mỗi mục ghi: ý tưởng · cách bật/tắt · bằng chứng lõi vẫn đúng (test + `kiem_tat_dinh.py` xanh, headless không đổi).

---

# Về lab Day 12

> Đề từng phase mở theo mốc giờ tại lab board **[Chợ Nổi Lab](https://claude.ai/artifact/E35v787wSx2wDgPTNhMVDg)**. Chi tiết khung starter: [`docs/STARTER.md`](docs/STARTER.md).

## Bắt buộc

1. **Một repo chung:** fork tên `K5-L3B-LAB-Day12-AI-SDLC-<ten-nhom>`, mọi thành viên là collaborator (quyền Write), repo **public**.
2. **Cả nhóm cùng commit** bằng tài khoản GitHub của mình, mỗi người **≥ 3 commit có nội dung** (làm cặp thì ghi `Co-authored-by:`).
3. **[`TEAM.md`](TEAM.md):** danh sách thành viên + thỏa thuận nhóm; `team_size` trong [`game.contract.json`](game.contract.json) khớp.
4. **Gắn tag** `phase-1` … `phase-4` đúng hạn; chạy được tại từng tag.
5. **Ghi chép tối thiểu:** `docs/verification/phase-n.md`, `docs/clarify.md`, `docs/ai-usage-log.md`, `docs/retro.md`, `docs/members/<handle>.md`.

## Tự do sáng tạo

Được **thêm** nhân vật, loài cá/cây, sinh vật, món, bản đồ, cơ chế, câu chuyện, đồ họa, âm nhạc… với ba điều kiện: **không phá phần cố định** (tắt ở headless), ghi mục **"Sáng tạo của nhóm"** ở trên, và **làm lõi đúng trước**.

## Lịch 3 giờ

| Mốc | Phase | Hạn tag |
|---|---|---|
| 0:00 | Phase 1 (PRD-0) | `phase-1` trước 1:00 |
| 1:00 | Phase 2 | `phase-2` trước 1:55 |
| 1:55 | Phase 3 | `phase-3` trước 2:30 |
| 2:30 | Phase 4 | `phase-4` + Release `v1.0.0` trước 3:00 |

Hết giờ mỗi phase thì gắn tag rồi đi tiếp; chỗ chưa xong ghi trung thực trong bằng chứng.

## Đánh giá (100 điểm)

| Hạng mục | Điểm |
|---|---|
| Test tự động ẩn (headless, gồm kiểm tra lại phase trước) | 25 |
| Làm việc nhóm (một repo chung, chia việc, tích hợp, đổi yêu cầu) | 25 |
| Kiểm chứng & bằng chứng | 15 |
| Harness AI (AGENTS.md, skill, nhật ký dùng AI) | 10 |
| Đánh giá & retro | 10 |
| Chất lượng sản phẩm (đúng yêu cầu, mở rộng/sáng tạo) | 10 |
| Demo | 5 |

## Quy định

- Dùng AI thoải mái; **không sao chép repo của nhóm khác**; bằng chứng phải thật.
- Nhân vật, bối cảnh là bản gốc của lab; asset ngoài chỉ dùng CC0/CC-BY/MIT hoặc tự tạo, ghi nguồn trong `CREDITS.md`. Không commit API key, token, `.env`.
