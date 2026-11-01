# FOOTBALL MANAGER — Web Edition

Bản cập nhật giao diện và logic quản lý đội bóng.

## Các thay đổi
- Hiển thị ngân sách và giá cầu thủ theo số euro đầy đủ, ví dụ `300.000.000 €`.
- Cầu thủ mua trên TTCN và cầu thủ nhận từ gói được đưa thẳng vào danh sách dự bị.
- Chuẩn hoá dữ liệu dự bị cũ, chuyển tên cầu thủ dạng chuỗi thành hồ sơ cầu thủ và loại bỏ mục dự bị trùng tên.
- Thêm hộp thoại xác nhận theo phong cách game trước khi mua cầu thủ, mở gói và ép thẻ.
- Kết quả ép thẻ hiển thị rõ thành công/thất bại, cấp thẻ sau cùng, chi phí và ngân sách còn lại.
- Giữ nguyên dữ liệu lưu của người chơi; không kèm database trong gói cập nhật.

## Cập nhật dự án hiện tại
Sao lưu dự án của bạn trước khi thay file. Giải nén gói này và chép đè các file cùng tên trong repository. **Không xoá, thay thế hoặc tạo lại database PostgreSQL/SQLite đang dùng**, không chạy lệnh reset dữ liệu. Các file `models.py`, `requirements.txt`, `Procfile` và các trang đăng nhập/chọn CLB được giữ nguyên từ bản dự án hiện tại.

## Chạy local
```bash
pip install -r requirements.txt
python app.py
```

Khi deploy, giữ nguyên `DATABASE_URL` và `SECRET_KEY` hiện tại.
