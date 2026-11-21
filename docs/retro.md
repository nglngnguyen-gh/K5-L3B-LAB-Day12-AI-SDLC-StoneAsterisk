# Retro nhóm

## Phase 2 (nhanh)
> Nháp do Integrator soạn từ lịch sử repo; cả nhóm bổ sung trong 5 phút retro.
- Điều tốt:
  - Chốt contract v1.1 + hợp đồng mục 5 trước khi các lát bắt đầu → 4 lát P2 làm song song, mỗi PR gộp riêng đều xanh.
  - Hai lát tự chuyển phần lọc vào sim của mình (`QuanSim(menu_filter)`, `GatherSim(day)`) thay vì sửa chồng trong `day.py`.
  - Skill `kiem-tat-dinh` / `smoke-hai-tien-trinh` chạy lại được ngay cho `day`; bằng chứng P2 sinh trong vài phút.
- Điều tệ:
  - Tag `phase-1` trễ hạn; lát 4 P1 (PR #2) phải sửa 2 vòng và có lúc sửa test của lát khác để test xanh khi luật sai.
  - 4 PR dồn vào cuối phase → xung đột `day.py`, `index.html`, `ai-usage-log.md`, `standup.md`.
  - Chưa ai làm UI vòng ngày (AC-P2-45) và chưa chơi thử HUD lưu ảnh; chưa có mục Mở rộng.
- 1 hành động cho Phase 3: mỗi lát mở PR nháp ngay khi có commit đầu và chạy toàn bộ test trước khi xin review; **không sửa test của lát khác** nếu không ghi lý do trong commit. Người nhận: nglngnguyen-gh (Integrator) nhắc ở standup phút 20.

## Phase 3 (nhanh — đổi kho đếm → kho cá thể)
> Nháp do Integrator soạn từ lịch sử repo; cả nhóm bổ sung.
- Điều tốt:
  - Ghi tác động + quyết định schema trước (`docs/plan/phase-3.md`), adapter `items.py` lên `main` khi manifest vẫn v1.1 → `main` luôn xanh trong lúc chuyển.
  - Biểu diễn độ tươi bằng số nguyên đơn vị (240/điểm) → không lệch ở ngưỡng 30 và phép floor giá.
  - Test v1.2 của `day` viết trước, tự bật khi manifest lên 1.2 → lúc bật đã có kiểm tích hợp.
- Điều tệ:
  - Bật v1.2 làm vỡ ~67 test P1–P2 vì fixture / kỳ vọng ghi cứng kho đếm; mất nhiều thời gian chuyển test (lý do ghi trong commit).
  - Lát gather v1.2 không có commit tới phút ~25 → Integrator làm thay; PR #11 làm trùng phần đã có trong PR #9.
  - Mở rộng (burn) vẫn chưa gộp.
- Rút ra từ lần đổi kho: test nên đọc dữ liệu qua helper (`hold_items`, `counts_of`) thay vì ghi cứng schema.
- 1 hành động cho Phase 4: phút 10 mỗi người báo commit đầu trong kênh; lát không có commit thì Integrator chia lại ngay. Người nhận: nglngnguyen-gh.

## Phase 4 (cuối)

### Rà hành động cải tiến Phase 2

| Hành động | Đánh giá | Bằng chứng và nguyên nhân / giới hạn |
|---|---|---|
| Mở PR nháp ngay sau commit đầu | Chưa đủ bằng chứng | Lịch sử có PR #9–#12; retro Phase 3 ghi PR #11 trùng phần PR #9. Git log không ghi thời điểm mở PR hay trạng thái nháp, nên chưa xác định được nguyên nhân và mức tuân thủ. |
| Chạy toàn bộ test trước khi xin review | Chưa đủ bằng chứng | `docs/proof/phase-3/unittest.txt` ghi 206 test, OK với 4 test bỏ qua; bằng chứng này không xác định thời điểm so với từng yêu cầu review. Chưa có bằng chứng tương ứng cho từng PR Phase 4. |
| Không sửa test lát khác nếu không ghi lý do trong commit | Thực hiện một phần | Retro Phase 3 ghi khoảng 67 test bị ảnh hưởng vì fixture / kỳ vọng gắn với kho đếm; commit `bf122e3` mô tả chuyển test khi bật v1.2. Chưa đủ bằng chứng để xác nhận mọi thay đổi test đều có lý do cụ thể. |

Hành động tiếp nối từ Phase 3 là báo commit đầu ở phút 10 và chia lại lát chậm. Chưa đủ bằng chứng xác nhận thực hiện trong Phase 4: `docs/standup.md` không có dòng Phase 4 và không có bản ghi kênh trao đổi trong tài liệu đã rà.

### Điều tốt và cần cải thiện

- **Tốt:** Kế hoạch Phase 3 ghi quyết định schema và phân tích tác động trước khi chuyển kho (`docs/plan/phase-3.md`). Bằng chứng lưu tại `docs/proof/phase-3/smoke.txt` ghi 12/12 mục đạt và `tat-dinh.txt` ghi 15/15 cặp giống từng byte; `unittest.txt` ghi 206 test, OK với 4 test bỏ qua. Đây là các kết quả đã lưu của Phase 3.
- **Cần cải thiện:** Retro Phase 3 ghi lát gather không có commit đến khoảng phút 25, Integrator làm thay và PR #11 trùng PR #9. Fixture phụ thuộc schema kho đếm khiến khoảng 67 test cần chuyển khi bật v1.2; nên kiểm tác động sớm và dùng helper fixture chung.
- **Phase 4:** `docs/proof/phase-4/bench.json` có kết quả đo benchmark, nhưng artifact không xác định commit được đo; riêng kết quả này không đủ xác nhận trạng thái phát hành.

### Số commit và review chéo

Đếm commit không phải merge có thể truy tới `origin/main` tại `75695b6`, từ commit gốc, theo author (`git log 75695b6 --no-merges`). Đây là ảnh chụp ref cục bộ, không khẳng định trạng thái máy chủ hiện tại.

| Thành viên | Commit không merge |
|---|---:|
| nglngnguyen-gh (author `Nguyen`) | 18 |
| LyLe10 | 4 |
| BLong1501 | 6 |
| minhtriet061203 | 10 |
| len2412 | 5 |

Ngoài nhóm có 9 commit starter của author `Hai Duong`: tổng 52 commit không merge. Có thêm 25 merge commit bị loại khỏi số chính; author `Nguyen` và `nglngnguyen-gh` dùng cùng email trong lịch sử. Thống kê không đo khối lượng, chất lượng, đóng góp cùng làm hay review; commit ngoài phạm vi ref không được tính.

`TEAM.md` quy định review chéo lát 1 ↔ 2, lát 3 ↔ 4 và Integrator đọc trước khi gộp. `docs/standup.md` ghi dự định review / pair; `docs/ai-usage-log.md` ghi Integrator review PR #8 và #11. Chưa có đủ link và kết quả review để xác nhận từng cặp đã hoàn tất.

### AI: lỗi và chi phí

Nhật ký Integrator trong `docs/ai-usage-log.md` ghi regex chuyển fixture v1.2 tạo ID trùng với `hold_items("x") * n`; test báo mã 2, sau đó sửa thành `hold_items(*[...] * n)` để tạo các cá thể riêng. Nhật ký ghi cách phát hiện và sửa, chưa định danh riêng lần chạy xác minh sau sửa.

| Người | Token / chi phí AI |
|---|---|
| nglngnguyen-gh | Không đo được trong các dòng đã ghi; chưa có dòng Phase 4. |
| LyLe10 | Không đo được theo nhật ký Phase 1–4. |
| BLong1501 | Không đo được trong các dòng đã ghi; chưa có dòng Phase 4. |
| minhtriet061203 | Không đo được trong các dòng đã ghi; chưa có dòng Phase 4. |
| len2412 | Không đo được trong dòng đã ghi; chưa có dòng Phase 4. |

### Hành động tiếp theo — đề xuất, chờ nhóm xác nhận người nhận và thời hạn

| Việc | Người nhận đề xuất | Thời hạn đề xuất |
|---|---|---|
| Ghi nhận commit đầu và vướng mắc, chia lại lát chậm | nglngnguyen-gh | Mốc phút 10 của phase tiếp theo; chờ xác nhận |
| Lưu link PR, review và kết quả toàn bộ test trước khi xin review; ghi lý do khi sửa test lát khác | Mỗi người; nglngnguyen-gh theo dõi | Trước khi xin review từng PR; chờ xác nhận |
| Rà fixture phụ thuộc schema, dùng helper chung khi phù hợp | minhtriet061203 và LyLe10 | Trước lần đổi schema tiếp theo; chờ xác nhận |
| Bổ sung link review chéo và số token / chi phí nếu có, hoặc ghi không đo được | Mỗi thành viên | Trước khi chốt retro; chờ xác nhận |
