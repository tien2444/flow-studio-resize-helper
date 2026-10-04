# Tích hợp và phát hành

## 1. Web app

Đặt các file trong `web/` về đúng vị trí của ứng dụng Next.js. Host app cần:

- React và `lucide-react`;
- Dialog component tương thích;
- kiểu `Asset` gồm `id`, `name`, `mime`, `size`, `url`;
- route auth cho `/api/processor-targets`;
- phục vụ ZIP Helper tại các URL trong `helper-platform.ts`.

## 2. Catalog app

`processor-targets.json` là catalog đường dẫn. `processor-drive-targets.json` bổ sung folder ID. Chạy `scripts/resolve-drive-targets.py` trong môi trường có OAuth nội bộ để cập nhật catalog; không commit file OAuth.

## 3. macOS

Build `flow-local-processor` bằng PyInstaller, đặt binary trong `helper/macos/processor/`, đóng gói cùng `install.command` và `README.txt`.

Installer tạo LaunchAgent, cài vào `~/Library/Application Support/FlowStudioWebHelper/processor-v12` và chạy nền ở port 43127.

## 4. Windows

Workflow `build-helper-windows.yml` build binary x64, chạy smoke test rồi xuất artifact ZIP. Installer tạo shortcut Startup và lưu dữ liệu trong `%LOCALAPPDATA%\FlowStudioWebHelper`.

## 5. OAuth fallback

Google Drive Desktop là đường upload chính. API fallback chỉ bật khi máy có:

```text
oauth_client.json
drive_oauth_token.json
```

Hai file đặt trong Application Support của AutoResizeTool theo `platform_paths.application_data_dir()`. Không đưa chúng vào source, installer hoặc GitHub Actions.

## 6. Thứ tự chạy một pack

1. Web kiểm tra `/session` và cảnh báo nếu Helper cũ hơn phiên bản tối thiểu.
2. Web tải media vào `/inputs`; Helper lưu bản input local.
3. Web gửi catalog qua `/targets`, sau đó gọi `/refresh-targets` để lấy đường dẫn đúng của máy.
4. Người dùng chọn app đích, tỷ lệ, chế độ fit/crop/blur, chất lượng và quy tắc tên.
5. Web tạo `/jobs`; Helper đưa job vào hàng chờ và trả ID ngay.
6. Helper render từng output, ghi file local rồi mới upload tới từng app.
7. Web đọc `/jobs` định kỳ và cho phép mở lại pack sau khi đóng modal hoặc reload.
8. Nếu Drive lỗi, dùng `/jobs/:id/retry-drive`; output local được tái sử dụng và không bị resize lần nữa.

Khi chọn nhiều app, mỗi app nhận một bản video và thumbnail trong cùng cấu trúc ngày/theme. Bỏ chọn app trước khi tạo job sẽ loại app đó khỏi pack; danh sách app được đóng băng sau khi job đã tạo.
