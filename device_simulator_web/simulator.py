import json
import time
import csv
import os
import sys
import io
from datetime import datetime
import paho.mqtt.client as mqtt
import threading

# Bắt buộc mã hóa UTF-8 cho dòng xuất chuẩn để tránh lỗi CP1252/charmap trên Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# === CONFIG_START ===
# Default parameters (Fallback)
BROKER_HOST = "36.50.232.86"
BROKER_PORT = 1883
NUM_DEV = 165
START_INDEX = 0
DEVICE_CODE_PREFIX = "b"
DEVICE_ID_PREFIX = "rd_"
TELEMETRY_INTERVAL = 50
LOG_FILE_CSV = "logs/device_stats.csv"
LOG_INTERVAL = 60
TELEMETRY_TOPIC = "v1/devices/me/telemetry"
RPC_REQUEST_TOPIC = "v1/devices/me/rpc/request/{}"
TELEMETRY_DATA = {
    "mode": 1,
    "relay1": False,
    "relay2": False,
    "dim": 0,
    "vercode": "0.0.13"
}
RESPONSE_RPC = "true"
RESPONSE_RPC_SKIP_START = 0
RESPONSE_RPC_SKIP_END = 0

# Load config from JSON
config_path = "device_config.json"
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            BROKER_HOST = cfg.get("BROKER_HOST", BROKER_HOST)
            BROKER_PORT = int(cfg.get("BROKER_PORT", BROKER_PORT))
            NUM_DEV = int(cfg.get("NUM_DEV", NUM_DEV))
            START_INDEX = int(cfg.get("START_INDEX", START_INDEX))
            DEVICE_CODE_PREFIX = cfg.get("DEVICE_CODE_PREFIX", DEVICE_CODE_PREFIX)
            DEVICE_ID_PREFIX = cfg.get("DEVICE_ID_PREFIX", DEVICE_ID_PREFIX)
            TELEMETRY_INTERVAL = int(cfg.get("TELEMETRY_INTERVAL", TELEMETRY_INTERVAL))
            LOG_FILE_CSV = cfg.get("LOG_FILE_CSV", LOG_FILE_CSV)
            LOG_INTERVAL = int(cfg.get("LOG_INTERVAL", LOG_INTERVAL))
            TELEMETRY_TOPIC = cfg.get("TELEMETRY_TOPIC", TELEMETRY_TOPIC)
            RPC_REQUEST_TOPIC = cfg.get("RPC_REQUEST_TOPIC", RPC_REQUEST_TOPIC)
            TELEMETRY_DATA = cfg.get("TELEMETRY_DATA", TELEMETRY_DATA)
            RESPONSE_RPC = str(cfg.get("RESPONSE_RPC", RESPONSE_RPC))
            RESPONSE_RPC_SKIP_START = int(cfg.get("RESPONSE_RPC_SKIP_START", RESPONSE_RPC_SKIP_START))
            RESPONSE_RPC_SKIP_END = int(cfg.get("RESPONSE_RPC_SKIP_END", RESPONSE_RPC_SKIP_END))
    except Exception as e:
        print(f"Lỗi khi đọc file cấu hình JSON: {e}. Sử dụng cấu hình mặc định.")
# === CONFIG_END ===

# Đảm bảo thư mục logs tồn tại
os.makedirs(os.path.dirname(LOG_FILE_CSV) or "logs", exist_ok=True)

client_lock = threading.Lock()
all_devices = []

class DeviceClient:
    def __init__(self, index: int):
        self.index = index
        max_val = START_INDEX + NUM_DEV
        padding_len = max(3, len(str(max_val)))
        self.device_code = f"{DEVICE_CODE_PREFIX}{index:0{padding_len}d}"
        self.device_id = f"{DEVICE_ID_PREFIX}{self.device_code}"
        self.mac_address = self.device_code
        self.msg_id = 1
        self.connected = False
        self.sent_messages = 0
        self.received_messages = 0
        self.msg_recv_rpc_resp = 0
        self.control_messages = 0
        self.msg_recv_rpc_server = 0
        self.rpc_sent = 0
        self.last_log_time = time.time()

        self.telemetry_db = {
            "number_scene": 0,
            "scene_now": 0,
            "mac": self.mac_address
        }
        if isinstance(TELEMETRY_DATA, dict):
            for k, v in TELEMETRY_DATA.items():
                self.telemetry_db[k] = v
        else:
            self.telemetry_db["mode"] = 1
            self.telemetry_db["relay1"] = False
            self.telemetry_db["relay2"] = False
            self.telemetry_db["dim"] = 0
            self.telemetry_db["vercode"] = "0.0.13"
        self.scene_db = {}
        # Đặt thời điểm telemetry cũ để kích hoạt gửi ngay sau khi kết nối thành công
        self.last_telemetry_time = time.time() - TELEMETRY_INTERVAL
        self.last_time_sync = time.time()

        self.client = mqtt.Client(client_id=self.device_id)
        self.client.username_pw_set(self.device_id, self.device_id)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.sent_last_minute = 0

        self._connect()

    def _connect(self):
        try:
            self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"[{self.device_id}] ❌ Lỗi kết nối MQTT: {e}")
            self.connected = False

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print(f"[{self.device_id}] ✅ MQTT connected.")
            self.client.subscribe("v1/devices/me/rpc/request/+")
            self.client.subscribe("v1/devices/me/rpc/response/+")
        else:
            print(f"[{self.device_id}] ⚠️ Kết nối lỗi (code={rc})")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"[{self.device_id}] ⚠️ Mất kết nối, thử reconnect...")
        while not self.connected:
            try:
                time.sleep(3)
                self._connect()
            except Exception:
                pass

    def on_message(self, client, userdata, msg):
        self.received_messages += 1
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
            identify = topic.split("/")[-1]
            
            if "rpc/response" in topic:
                self.msg_recv_rpc_resp += 1
            elif "rpc/request" in topic:
                self.msg_recv_rpc_server += 1

            if isinstance(payload, dict) and "method" in payload:
                method = payload.get("method")
                payload_response = {
                    "method": method + "Rsp",
                    "params": {
                        "code": 0
                    }
                }
                should_respond = True
                if RESPONSE_RPC == "false":
                    should_respond = False
                elif RESPONSE_RPC == "range":
                    if RESPONSE_RPC_SKIP_START <= self.index <= RESPONSE_RPC_SKIP_END:
                        should_respond = False

                if should_respond:
                    self.publish("v1/devices/me/rpc/response/{}".format(identify), json.dumps(payload_response))
                    print(f"Gửi phản hồi RPC đến topic v1/devices/me/rpc/response/{identify}: {payload_response}")
                else:
                    print(f"Nhận được RPC '{method}' trên {self.device_id} nhưng KHÔNG gửi phản hồi (RESPONSE_RPC = {RESPONSE_RPC})")
                
                req_method = payload.get("method")
                if req_method == "control":
                    params = payload.get("params", {})
                    if "dim" in params:
                        self.telemetry_db["dim"] = params.get("dim")
                    if "relay1" in params:
                        self.telemetry_db["relay1"] = params.get("relay1")
                    if "relay2" in params:
                        self.telemetry_db["relay2"] = params.get("relay2")
                    
                    self.send_status_update()
                    self.control_messages += 1
                
                elif req_method == "setScene":
                    params = payload.get("params", {})
                    scene_id = params.get("id")
                    if scene_id is not None:
                        self.scene_db[scene_id] = {
                            "condition": params.get("condition", {}),
                            "execute": params.get("execute", {}),
                            "last_run_day": None,
                            "last_run_minute": None
                        }
                        self.telemetry_db["number_scene"] = len(self.scene_db)
        except Exception as e:
            print(f"Lỗi xử lý on_message trên {self.device_id}: {e}")

    def maybe_log_csv(self):
        now = time.time()
        if now - self.last_log_time >= LOG_INTERVAL:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(LOG_FILE_CSV, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([
                        ts, self.device_id, self.sent_messages, self.rpc_sent, self.received_messages, self.control_messages, self.msg_recv_rpc_server, self.msg_recv_rpc_resp
                    ])
                self.last_log_time = now
            except Exception as e:
                print(f"Lỗi ghi log CSV: {e}")

    def publish(self, topic, payload):
        self.client.publish(topic, payload)
        self.sent_messages += 1
        self.sent_last_minute += 1
        self.maybe_log_csv()

    def send_status_update(self):
        now = datetime.now()
        payload = self.telemetry_db.copy()
        payload["time_rtc"] = [{
            "hour": now.hour, "minute": now.minute, "second": now.second,
            "day": now.day, "month": now.month, "year": now.year % 100
        }]
        self.publish(TELEMETRY_TOPIC, json.dumps(payload))

    def send_time_sync(self):
        payload = json.dumps({"method": "getTimeCloud", "params": {}})
        self.publish(RPC_REQUEST_TOPIC.format(self.msg_id), payload)
        self.msg_id += 1
        self.rpc_sent += 1

    def send_run_scene(self, scene_id):
        payload = json.dumps({"method": "runScene", "params": {"mac": self.mac_address, "ruleId": scene_id}})
        self.publish(RPC_REQUEST_TOPIC.format(self.msg_id), payload)
        self.msg_id += 1
        self.rpc_sent += 1


# --- Vòng lặp thiết bị toàn cục để định kỳ gửi telemetry & kiểm tra scene ---
def global_device_loop():
    while True:
        try:
            current_time = time.time()
            now = datetime.now()
            
            with client_lock:
                devices_to_process = list(all_devices)

            for device in devices_to_process:
                if not device.connected:
                    continue
                
                # 1. Gửi telemetry định kỳ
                if current_time - device.last_telemetry_time >= TELEMETRY_INTERVAL:
                    try:
                        device.send_status_update()
                        device.last_telemetry_time = current_time
                    except Exception as e:
                        print(f"Lỗi gửi telemetry trên {device.device_id}: {e}")

                # 2. Xử lý Scene tự động
                current_day_str = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.weekday()]
                current_time_str = f"{now.hour}:{now.minute:02d}"
                
                for scene_id, scene_info in list(device.scene_db.items()):
                    cond = scene_info.get("condition", {})
                    target_time = cond.get("time")
                    repeat_days = cond.get("repeat", [])
                    
                    if target_time:
                        try:
                            h, m = target_time.split(":")
                            target_time_norm = f"{int(h)}:{int(m):02d}"
                        except:
                            target_time_norm = target_time
                    else:
                        target_time_norm = None

                    if current_time_str == target_time_norm and current_day_str in repeat_days:
                        if scene_info["last_run_day"] != now.day or scene_info["last_run_minute"] != now.minute:
                            scene_info["last_run_day"] = now.day
                            scene_info["last_run_minute"] = now.minute
                            
                            execute = scene_info.get("execute", {})
                            if "relay1" in execute:
                                device.telemetry_db["relay1"] = execute["relay1"]
                            if "relay2" in execute:
                                device.telemetry_db["relay2"] = execute["relay2"]
                            if "dim" in execute:
                                device.telemetry_db["dim"] = execute["dim"]
                                
                            device.telemetry_db["scene_now"] = scene_id
                            try:
                                device.send_status_update()
                                device.send_run_scene(scene_id)
                            except Exception as e:
                                print(f"Lỗi chạy Scene {scene_id} trên {device.device_id}: {e}")

                # 3. Đồng bộ thời gian mỗi 30 phút
                if current_time - device.last_time_sync > 1800:
                    try:
                        device.send_time_sync()
                        device.last_time_sync = current_time
                    except Exception as e:
                        print(f"Lỗi đồng bộ thời gian trên {device.device_id}: {e}")

        except Exception as e:
            print(f"Lỗi trong vòng lặp thiết bị toàn cục: {e}")
        time.sleep(0.5)


# --- 🕒 Log tổng hợp định kỳ ---
def periodic_log():
    while True:
        time.sleep(LOG_INTERVAL)
        try:
            with client_lock:
                devices_to_process = list(all_devices)
            
            connected_clients = sum(1 for d in devices_to_process if d.connected)
            disconnected_clients = len(devices_to_process) - connected_clients
            total_sent = sum(d.sent_messages for d in devices_to_process)
            total_recv = sum(d.received_messages for d in devices_to_process)
            total_rpc = sum(d.rpc_sent for d in devices_to_process)
            total_recv_rpc_resp = sum(d.msg_recv_rpc_resp for d in devices_to_process)
            total_recv_rpc_server = sum(d.msg_recv_rpc_server for d in devices_to_process)
            total_control = sum(d.control_messages for d in devices_to_process)
            success_rate = (total_recv / total_sent * 100) if total_sent else 0

            log_line = (
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Connected: {connected_clients}, "
                f"Disconnected: {disconnected_clients}, "
                f"Sent: {total_sent}, "
                f"Received: {total_recv}, "
                f"RPC Sent: {total_rpc}\n"
                f"RPC Resp (server->client reply): {total_recv_rpc_resp}, "
                f"RPC ServerPush (server->client request): {total_recv_rpc_server}, "
                f"Control Messages: {total_control}, "
                f"Success Rate: {success_rate:.2f}%\n"
            )

            print(log_line.strip())

            # Lưu log ngày vào thư mục logs
            log_filename = f"logs/device_{datetime.now().strftime('%Y-%m-%d')}.txt"
            with open(log_filename, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            print(f"Lỗi ghi log tổng hợp: {e}")


if __name__ == "__main__":
    print(f"🚀 Bắt đầu giả lập MQTT Device (Không sử dụng Locust) - {NUM_DEV} thiết bị...")
    print(f"Broker: {BROKER_HOST}:{BROKER_PORT}")
    
    # Khởi tạo file log CSV
    if not os.path.exists(LOG_FILE_CSV):
        os.makedirs(os.path.dirname(LOG_FILE_CSV) or "logs", exist_ok=True)
        with open(LOG_FILE_CSV, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "timestamp", "device_id", "sent_messages", "rpc_sent", "received_messages", "control_messages", "rpc_server_recv", "rpc_resp_recv"
            ])
            
    # Chạy thread log tổng hợp định kỳ
    log_thread = threading.Thread(target=periodic_log, daemon=True)
    log_thread.start()
    
    # Chạy thread vòng lặp thiết bị toàn cục
    device_thread = threading.Thread(target=global_device_loop, daemon=True)
    device_thread.start()

    # Kết nối các thiết bị ảo
    for i in range(START_INDEX + 1, START_INDEX + NUM_DEV + 1):
        device = DeviceClient(i)
        with client_lock:
            all_devices.append(device)
        # Giãn cách kết nối 50ms tránh nghẽn luồng
        time.sleep(0.05)

    print(f"✅ Đã kết nối xong tất cả {NUM_DEV} thiết bị. Tiến trình đang hoạt động...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("👋 Đang dừng giả lập...")
