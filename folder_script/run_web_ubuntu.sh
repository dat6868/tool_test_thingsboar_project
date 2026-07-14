#!/bin/bash
# Script khởi chạy ngầm Device Simulator Web trên Ubuntu
cd ~/tool_test_thingsboar_project/device_simulator_web

# Tắt tiến trình cũ nếu đang chạy để tránh xung đột cổng
pkill -9 -f "uvicorn main:app --host 0.0.0.0 --port 6369"

# Khởi chạy ngầm uvicorn
nohup ../venv/bin/uvicorn main:app --host 0.0.0.0 --port 6369 --no-access-log > web_server.log 2>&1 &

echo "Device Simulator Web đã khởi chạy ngầm tại cổng 6369!"
echo "Bạn có thể truy cập tại: http://<IP_MÁY_ẢO>:6369"
