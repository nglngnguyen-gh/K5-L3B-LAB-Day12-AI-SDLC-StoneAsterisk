# BLong1501 (Trần Bảo Long · 2A202604012) — phản tư cá nhân (≤ 200 từ)

- **Tôi đã làm:**
  - **P1:** Lát 2 `chonoi/sim/gather.py` (`20cc53d`), 16 test `tests/test_gather_slice2.py`, HUD (`7993154`).
  - **P2:** Lát 1 cá bơi/phản xạ/sinh cá `360·k`, 7 test `tests/test_gather_p2_fish.py`, nâng cấp HUD sáng v1.1 (`≥ 18px`, cảnh báo, cần lấy).
  - **P4:** 3 cảnh báo chữ + biểu tượng (`🐊 ⚠ THỦY QUÁI GẦN!`, `🫧 ⚠ OXY SẮP HẾT!`, `😡 ⚠ Sắp giận!`) và phím `H` bật chế độ tương phản cao trong `chonoi/web/index.html`; lưu ảnh bằng chứng `docs/proof/phase-4/`.
- **Tôi đã review:** Tham gia kiểm thử tích hợp và chạy thử giao diện qua `chonoi.live`.
- **AI sai ở đâu và tôi phát hiện thế nào:** AI gợi ý lệnh Bash trên Windows PowerShell (`PYTHONPATH=tests:.`) và không thấy Python trong sandbox; khi chuyển sang v1.1 có 2 test hồi chiêu P1 fail do cá tự bơi vượt dải độ sâu. Tôi tự chạy lại trên PowerShell (`unittest`, `kiem_tat_dinh`, `smoke`) và kiểm tra trực tiếp trên trình duyệt.
- **Điều tôi học được:** Luôn kéo `main` sạch trước khi tách nhánh mới và đọc kỹ hợp đồng (`docs/contracts/README.md`) để ghép code nhiều người ít xung đột nhất.
