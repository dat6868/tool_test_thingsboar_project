# Hướng dẫn chạy Công cụ Thả Bom (Bomb Dropper Web)

Đây là công cụ Load Test API thông qua giao diện Web. Cần được cấu hình chạy liên tục trên Server.

## 1. Cài đặt thư viện
Chạy lệnh sau để cài đặt các thư viện lõi:
```bash
pip install -r requirements.txt --break-system-packages
```

## 2. Cách chạy bình thường (Có giao diện Log trên Terminal)
Chế độ này phù hợp khi bạn muốn xem log trực tiếp. Nếu bạn đóng Terminal (hoặc tắt SSH), tool sẽ bị tắt theo:
```bash
uvicorn main:app --host 0.0.0.0 --port 6368 --no-access-log
```

## 3. Cách chạy ngầm (Chạy nền trên Máy Ảo/Server)
Chế độ này giúp Tool sống vĩnh viễn trên Server, dù bạn có tắt máy tính cá nhân hay tắt kết nối SSH.
```bash
nohup uvicorn main:app --host 0.0.0.0 --port 6368 --no-access-log > server.log 2>&1 &
```
- Mọi log sẽ được đẩy vào file `server.log`. Bạn có thể xem trực tiếp bằng lệnh: `tail -f server.log`
- Để tắt tool khi đang chạy ngầm, tìm PID bằng lệnh `ps aux | grep uvicorn` và dùng lệnh `kill <PID>`.

---
Sau khi chạy, mở trình duyệt truy cập: `http://<IP_MÁY_ẢO>:6368`
