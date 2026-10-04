# Kiến trúc

## Web

`ResizeWorkspace.tsx` quản lý ba bước:

1. Chọn nhiều ảnh/video và tải chúng vào Helper.
2. Đồng bộ catalog, tìm kiếm và chọn một hoặc nhiều app đích.
3. Chọn tỷ lệ, chế độ resize, chất lượng, quy tắc tên và chạy pack.

Web không xử lý media trực tiếp. Mọi file lớn chỉ đi từ trình duyệt tới loopback `127.0.0.1:43127`, tránh giới hạn request của Vercel.

## Local Helper

`server.py` chỉ bind loopback, kiểm tra `Host`, `Origin` và token session. `engine.py` lưu input, job, tiến độ và output bằng JSON atomic để mở lại web vẫn tiếp tục xem được.

`engine.py` thực hiện:

- tạo thumbnail và các tỷ lệ 9:16, 1:1, 16:9, 4:5;
- fit, crop, nền blur hoặc màu;
- giới hạn số worker để không làm nghẽn máy;
- lưu output trước khi upload;
- copy video và thumbnail tới từng app theo thứ tự;
- retry riêng phần Drive lỗi.

## Local API

Helper mở API tại `http://127.0.0.1:43127` và chỉ nhận request hợp lệ từ web Studio. Sau khi gọi `GET /session`, client dùng token session cho các request còn lại.

| Endpoint | Chức năng |
| --- | --- |
| `GET /session` | Kiểm tra phiên bản, nền tảng và lấy session token |
| `POST /inputs` | Đưa một ảnh/video vào kho input local |
| `GET /targets` | Đọc app catalog hiện tại của máy |
| `POST /targets` | Đồng bộ catalog canonical từ Studio Web xuống Helper |
| `POST /refresh-targets` | Ánh xạ catalog sang Drive mount hiện tại của macOS/Windows |
| `POST /jobs` | Tạo pack resize và upload |
| `GET /jobs` | Đọc danh sách pack cùng tiến độ để tiếp tục sau khi mở lại web |
| `GET /jobs/:id` | Đọc chi tiết một pack |
| `POST /jobs/:id/retry-drive` | Chỉ upload lại output lỗi, không render lại |
| `POST /jobs/:id/cancel` | Dừng pack đang chạy |
| `POST /jobs/:id/delete` | Xóa job và output local của pack |
| `GET /files/:job/:item/:kind` | Mở hoặc tải output/thumbnail local |

Mỗi job ghi trạng thái xuống đĩa theo kiểu atomic. Vì vậy đóng tab, reload web hoặc tạo pack mới không làm mất hàng chờ đang chạy.

## Đồng bộ app

Catalog gồm hai lớp:

- `processor-targets.json`: đường dẫn chuẩn trên Windows.
- `processor-drive-targets.json`: Drive ID và folder ID dùng cho API fallback.

`platform_paths.py` dịch đường dẫn chuẩn sang Google Drive mount của tài khoản hiện tại trên macOS hoặc Windows. `targets.py` đóng băng danh sách app đã chọn cho từng job để thay đổi catalog sau đó không làm lệch pack đang chạy.

## Upload Drive

Helper ưu tiên Google Drive for Desktop. Nếu File Provider lỗi, `google_drive.py` dùng resumable upload qua Drive API. Rate limit 403/429 và lỗi 5xx được backoff; lỗi quyền dừng ngay và giữ file local.

Mỗi item chỉ được đánh dấu `copied` sau khi tất cả app đích đã nhận đủ video và thumbnail.
