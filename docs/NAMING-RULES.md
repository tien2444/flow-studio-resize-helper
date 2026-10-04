# Quy tắc đặt tên

Tên chuẩn được tạo tại `helper/src/autoresize_tool/naming.py`.

## OS

```text
{Theme}_{AppCode}_{AssetLabel}_{Language}_OS_{Ratio}_{Duration}_{YYMMDD}.mp4
```

Ví dụ:

```text
BScanhsatCar_AABP_A11B84C40D44E14F29G92_EN_OS_916_30s_261004.mp4
```

## AUTO

Giống OS nhưng marker là `AT`:

```text
{Theme}_{AppCode}_{AssetLabel}_{Language}_AT_{Ratio}_{Duration}_{YYMMDD}.mp4
```

## W2W

```text
{Theme}_{AppCode}_{AssetLabel}_{Language}_{W2WFlow}_{Ratio}_{Duration}_{YYMMDD}.mp4
```

Nếu flow token chưa bắt đầu bằng `W2W`, Helper tự thêm prefix.

## W2WOS

```text
{Theme}_{AppCode}_{AssetLabel}_{Language}_{W2WFlow}_OS_{Ratio}_{Duration}_{YYMMDD}.mp4
```

## Source

Giữ nguyên tên file output local. Khi upload nhiều app, chế độ có cấu trúc được khuyến nghị để mỗi app nhận đúng `AppCode`.

## Thư mục

```text
{YYMM}/{YYMMDD}/{Theme}/
```

Asset label có dạng `A…B…C…D…E…F…G…` và được cấp ngẫu nhiên, không trùng trong kho local.
