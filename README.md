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


## Admin account (private)

The game has no public Admin registration or first-claim setup page. Provision the single Admin account through private environment variables in the hosting dashboard:

- `ADMIN_USERNAME`: the Admin login name you choose.
- `ADMIN_PASSWORD`: a strong password you choose and keep private.
- `SECRET_KEY`: a separate long random secret used to protect sessions.

Set these variables in the hosting provider's Environment/Variables settings before starting the app. On startup, the configured username is created/promoted as the only Admin and its password is synchronized from `ADMIN_PASSWORD`; all other accounts are forced to regular-player status. Never paste these secrets into chat, source code, or a public GitHub repository.

After logging in with the Admin account, open **Admin** in the top navigation. Admin can view account names and creation dates, gift players (including custom OVR/card level) directly into a recipient's player collection, and grant in-game budget. Passwords are stored as secure hashes and are never displayed.

## Hệ thống bạn bè
- Thanh điều hướng người chơi: **Tổng quan → Bạn bè → Hòm thư**.
- Tìm kiếm tài khoản, gửi/nhận lời mời kết bạn và chấp nhận/từ chối.
- Hồ sơ bạn bè hiển thị CLB, OVR đội hình chính, đội hình/cầu thủ và 5 trận gần nhất.
- Trạng thái online dựa trên lần hoạt động gần nhất (90 giây); trang Bạn bè tự cập nhật trạng thái định kỳ.
- Gửi lời mời giao hữu cho bạn bè. Khi người nhận chấp nhận, trận đấu được mô phỏng và kết quả lưu vào lịch sử của cả hai đội; giao hữu không cộng ngân sách.
- Các bảng FriendRequest, Friendship, FriendlyChallenge và cột User.last_seen_at được tạo/migrate tự động khi ứng dụng khởi động. Không cần xoá database hiện tại.

## Đồng bộ dữ liệu cầu thủ và khung thẻ

- Khung thẻ hiện tại được thiết kế theo cảm hứng FC Online: Thường, Bạc, Vàng, Cao cấp và ICON. Khung sự kiện chưa được triển khai.
- Không sử dụng API bóng đá bên ngoài. Dữ liệu metadata cầu thủ chỉ lấy từ thông tin Admin xác minh hoặc dữ liệu đã lưu trong game. Thị trường chuyển nhượng sử dụng dữ liệu nội bộ của game.
- ICON/HEROES không được suy đoán từ API. Với cầu thủ còn thi đấu, Admin có thể cấu hình `SPECIAL_PLAYER_TYPES` dạng JSON, ví dụ: `{"Player Name":"ICON","Another Player":"HEROES"}`. Với cầu thủ đã giải nghệ, dùng `SPECIAL_PLAYER_METADATA` dạng JSON gồm đủ `nationality`, `club` (CLB cuối cùng), `league` (giải đấu cuối cùng), `type` (`ICON` hoặc `HEROES`) và `source` (nguồn xác minh). Chỉ khai báo sau khi kiểm chứng. ICON dùng khung ICON; HEROES có huy hiệu HEROES riêng.
- Khi API không trả đủ dữ liệu hoặc key chưa được cấu hình, cầu thủ đó bị ẩn khỏi thẻ/market thay vì hiển thị thông tin chưa xác minh. Dữ liệu đội hình đã lưu trong database không bị xóa hay ghi đè bởi tác vụ đồng bộ.
