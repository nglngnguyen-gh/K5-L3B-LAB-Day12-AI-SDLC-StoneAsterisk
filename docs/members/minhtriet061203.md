# minhtriet061203 — phản tư cá nhân (≤ 200 từ)

- **Đã làm:** Lát 3 quán: khách theo lịch, chọn món theo seed, giữ chỗ, kiên nhẫn, fixture mã 2 (`550c398`, `e16e752`). P2: 4 bàn, 6 món, `menu_filter` theo `day_plan` (`4c20e28`). P3: kho cá thể v1.2, hao tươi, `spoiled`, giữ lại khi ươn (`9572fbe`). P4 (Đóng gói, Bench/QA): clone sạch, regression, bench, soak, README, CREDITS, LICENSE, [phase-4.md](../verification/phase-4.md).
- **Đã giúp:** chạy `--mode day` thật, phát hiện `day.py` cắt menu làm crash (mã 1) và sửa (`d353848`). Báo Integrator lỗi gather v1.2 không bàn giao được giỏ có hàng. Báo soak bot không thử kho và khách.
- **AI sai:** viết lát 3 trước khi đọc hợp đồng nên đặt sai tên trường, phải sửa theo hợp đồng (`ef1c6bb`). Đoán sai thứ tự bước PRD-0; thêm test `StepOrder` để bắt. Ở P4, AI đọc nhầm file kho cũ nên suýt báo lỗi gather sai; chạy lại có cập bến thật mới thấy đúng.
- **Bài học:** đọc hợp đồng trước khi để AI viết code. Một kết luận chỉ đáng tin khi có lệnh chạy thật trên commit cụ thể. Test sim riêng lẻ không thay được chạy tích hợp end-to-end.
