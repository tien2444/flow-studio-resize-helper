# Flow Studio Resize & Drive Helper

Repository độc lập cho toàn bộ luồng **chọn media → chọn app đích → đặt tên → resize → lưu local → upload Google Drive** của Studio Web.

Repo này chứa:

- `helper/`: local processor chạy trên macOS và Windows, FFmpeg resize, hàng chờ bền vững, retry và Google Drive fallback.
- `web/`: giao diện React/Next.js, API catalog app đích và client kết nối Helper tại `127.0.0.1:43127`.
- `scripts/`: công cụ tạo catalog Drive từ cấu trúc Shared Drive.
- `tests/`: kiểm tra catalog, nền tảng, lỗi Drive và quy tắc đặt tên.

## Luồng vận hành

```mermaid
flowchart LR
  A[Chọn ảnh/video] --> B[Đẩy file vào Helper]
  B --> C[Chọn 1 hoặc nhiều app đích]
  C --> D[Chọn tỷ lệ và cách fit/crop/blur]
  D --> E[Chọn quy tắc tên]
  E --> F[FFmpeg render trên máy]
  F --> G[Lưu output local]
  G --> H[Copy qua Google Drive Desktop]
  H -->|File Provider lỗi| I[Google Drive API fallback]
  H --> J[Video + thumbnail theo từng app]
  I --> J
```

Helper luôn lưu output local trước. Lỗi Drive không làm mất file resize. Nút retry chỉ upload lại item lỗi, không render lại và không nhân bản file đã có cùng kích thước.

## Chạy source Helper

Yêu cầu Python 3.12 và FFmpeg được cung cấp bởi `imageio-ffmpeg`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r helper/src/requirements.txt
python helper/src/server.py --port 43127 --data-dir ./data
```

Kiểm tra session:

```bash
curl -H 'Origin: https://flow-studio-web-one.vercel.app' \
  http://127.0.0.1:43127/session
```

## Tích hợp web

Sao chép cấu trúc trong `web/` vào ứng dụng Next.js tương ứng. `ResizeWorkspace.tsx` cần các component Dialog của host app và kiểu `Asset`. Các đường dẫn alias `@/` giữ nguyên như Studio Web.

API `/api/processor-targets` trả catalog canonical. Khi mở workspace, web gửi catalog này xuống Helper rồi gọi `/refresh-targets` để dịch đường dẫn sang Drive mount thực tế của macOS/Windows.

Xem thêm:

- [Kiến trúc](docs/ARCHITECTURE.md)
- [Quy tắc đặt tên](docs/NAMING-RULES.md)
- [Tích hợp và phát hành](docs/INTEGRATION.md)

## QA

```bash
python -m unittest discover -s helper -p 'test_*.py'
node --experimental-transform-types --test tests/*.test.ts
```

## Bảo mật

Repository không chứa OAuth client, refresh token, access token, media người dùng hoặc dữ liệu job local. Đặt `oauth_client.json` và `drive_oauth_token.json` trong thư mục Application Support của từng máy; các file này đã được chặn bởi `.gitignore`.

Repository dành cho nội bộ iKame và nên được giữ ở chế độ private.
