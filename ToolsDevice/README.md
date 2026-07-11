# Hướng dẫn chạy Công cụ Giả lập Thiết bị (Device Simulator)

Đây là công cụ chạy giả lập mô phỏng hàng loạt thiết bị MQTT bắn thông điệp Telemetry định kỳ lên Server. Công cụ này sử dụng nền tảng `locust` và `paho-mqtt`.

## 1. Cài đặt thư viện
Chạy lệnh sau để cài đặt các thư viện lõi:
```bash
pip install -r requirements.txt --break-system-packages
```

## 2. Cách chạy bình thường (Có giao diện Log trên Terminal)
Chế độ này phù hợp khi bạn muốn giám sát quá trình gửi MQTT trực tiếp trên màn hình đen. Tuy nhiên, nếu bạn đóng Terminal (hoặc tắt phần mềm SSH), tool sẽ bị tắt ngay lập tức:
```bash
locust -f Device1.py --headless
```

## 3. Cách chạy ngầm (Chạy nền trên Máy Ảo/Server)
Khi chạy thực tế trên máy ảo để test dài ngày, bạn bắt buộc phải dùng lệnh `nohup` (No Hang Up) để công cụ tiếp tục sống ngay cả khi bạn tắt máy tính cá nhân.
```bash
nohup locust -f Device1.py --headless > device_sim.log 2>&1 &
```
- **Lưu ý:** Lệnh trên có chữ `--headless` nghĩa là **chạy không giao diện Web**, chỉ ghi log ra file.
- Nếu bạn muốn **mở Giao diện Web của Locust** (để xem biểu đồ và chỉnh thông số trên web), hãy BỎ chữ `--headless` đi và thêm tham số cổng `--web-port 6366`:
```bash
nohup locust -f Device1.py --web-port 6366 > device_sim.log 2>&1 &
```
Lúc này bạn có thể truy cập `http://<IP_MÁY_ẢO>:6366` để xem web của tool Device.

- Mọi thông báo lỗi hoặc tiến trình bắn API sẽ được ghi vào file `device_sim.log`.
- Thống kê tin nhắn MQTT (số lượng success, fail) sẽ được tự động ghi vào thư mục `logs/device_stats.csv`.
- Xem log chạy ngầm theo thời gian thực bằng lệnh: `tail -f device_sim.log`
- Tắt tool chạy ngầm: `ps aux | grep locust` -> `kill <PID>`
