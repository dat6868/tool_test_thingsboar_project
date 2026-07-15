import json
import time
import csv
import os
import argparse
from datetime import datetime
from locust import User, task, between, events
import paho.mqtt.client as mqtt
import threading
import random

# =========================================================
# CẤU HÌNH THÔNG SỐ CHÍNH (TỰ ĐỘNG ĐỌC TỪ FILE CẤU HÌNH JSON NẾU CÓ)
# =========================================================
# Giá trị mặc định (Fallback)
BROKER_HOST = "36.50.232.86"
BROKER_PORT = 1883
NUM_DEV = 165                 # Số lượng thiết bị ảo muốn giả lập
START_INDEX = 0               # Chỉ số bắt đầu để sinh mã thiết bị
DEVICE_CODE_PREFIX = "b"      # Tiền tố mã thiết bị (VD: a00000001)
DEVICE_ID_PREFIX = "rd_"      # Tiền tố ID thiết bị dùng làm user/pass đăng nhập (VD: rd_a00000001)
TELEMETRY_INTERVAL = 50       # Chu kỳ gửi bản tin trạng thái Telemetry định kỳ (giây)
LOG_FILE_CSV = "logs/device_stats.csv" # File xuất thống kê dạng CSV
LOG_INTERVAL = 60                      # Chu kỳ in thống kê ra màn hình và file (giây)
TELEMETRY_TOPIC = "v1/devices/me/telemetry"
RPC_REQUEST_TOPIC = "v1/devices/me/rpc/request/{}"
TELEMETRY_DATA = {
    "mode": 1,
    "relay1": False,
    "relay2": False,
    "dim": 0,
    "vercode": "0.0.13"
}
RESPONSE_RPC = "true"  # Phản hồi các bản tin RPC hay không ("true", "false", "range")
RESPONSE_RPC_SKIP_START = 0
RESPONSE_RPC_SKIP_END = 0

# Đọc cấu hình từ file JSON
config_path = "device_config.json"
web_config_path = "../device_simulator_web/device_config.json"
if os.path.exists(web_config_path):
    config_path = web_config_path
elif os.path.exists(config_path):
    pass
else:
    config_path = None

if config_path:
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
# =========================================================

os.makedirs("logs", exist_ok=True)
client_lock = threading.Lock()
all_devices = []


# --- Locust Events ---
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print(f"🚀 Bắt đầu test MQTT Device ({NUM_DEV} thiết bị, chu kỳ Telemetry định kỳ: {TELEMETRY_INTERVAL}s)...")
    if not os.path.exists(LOG_FILE_CSV):
        with open(LOG_FILE_CSV, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "timestamp", "device_id", "sent_messages", "rpc_sent", "received_messages"
            ])


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    total_sent = sum(d.sent_messages for d in all_devices)
    total_recv = sum(d.received_messages for d in all_devices)
    total_rpc = sum(d.rpc_sent for d in all_devices)
    total_recv_rpc_resp = sum(d.msg_recv_rpc_resp for d in all_devices)
    total_recv_rpc_server = sum(d.msg_recv_rpc_server for d in all_devices)
    total_control = sum(d.control_messages for d in all_devices)
    
    success_rate = (total_recv / total_sent * 100) if total_sent else 0
    print("\n=== TEST SUMMARY ===")
    print(f"Broker: {BROKER_HOST}:{BROKER_PORT}")
    print(f"Devices: {len(all_devices)}")
    print(f"Sent: {total_sent}")
    print(f"Received: {total_recv}")
    print(f"RPC Sent: {total_rpc}")
    print(f"RPC Resp (reply): {total_recv_rpc_resp}")
    print(f"RPC ServerPush (server->client): {total_recv_rpc_server}")
    print(f"Control Messages: {total_control}")
    print(f"Success rate: {success_rate:.2f}%")


# --- DeviceClient ---
class DeviceClient:
    def __init__(self, index: int):
        self.index = index
        # Thông tin kết nối được sinh tự động theo biến đếm (index)
        # Độ dài phần số tự động phình ra theo giá trị lớn nhất (tối thiểu là 3 chữ số)
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

        # Giả lập Database local
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
        self.last_telemetry_time = time.time() - TELEMETRY_INTERVAL # Đảm bảo gửi luôn ngay khi khởi động

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
        payload = msg.payload.decode("utf-8", errors="ignore")
        # print(payload)

        # Đếm chính xác loại bản tin RPC
        if "rpc/response" in topic:
            self.msg_recv_rpc_resp += 1
        elif "rpc/request" in topic:
            self.msg_recv_rpc_server += 1
        try:
            payload = json.loads(msg.payload.decode())
            identify = topic.split("/")[-1]
            # print(f"[{self.device_id}] 📩 Nhận RPC: {payload}")
            if "method" in payload:
                # print(f"[{self.device_id}] 🔄 Xử lý method: {payload.get('method')}")
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
                # time.sleep(1) # Đã tạm ẩn đi theo yêu cầu test để không block luồng mạng
            if isinstance(payload, dict):
                req_method = payload.get("method")
                if req_method == "control":
                    params = payload.get("params", {})
                    if "dim" in params:
                        self.telemetry_db["dim"] = params.get("dim")
                    if "relay1" in params:
                        self.telemetry_db["relay1"] = params.get("relay1")
                    if "relay2" in params:
                        self.telemetry_db["relay2"] = params.get("relay2")
                    
                    # Trigger 1: Gửi telemetry ngay lập tức
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
        except Exception:
            pass

    def maybe_log_csv(self):
        now = time.time()
        if now - self.last_log_time >= LOG_INTERVAL:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOG_FILE_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    ts, self.device_id, self.sent_messages, self.rpc_sent, self.received_messages, self.control_messages, self.msg_recv_rpc_server, self.msg_recv_rpc_resp
                ])
            self.last_log_time = now

    def publish(self, topic, payload):
        self.client.publish(topic, payload)
        self.sent_messages += 1
        self.sent_last_minute += 1
        self.maybe_log_csv()

    # --------------------------
    # 🧩 Gửi bản tin
    # --------------------------
    def send_status_update(self):
        now = datetime.now()
        payload = self.telemetry_db.copy()
        
        # Thêm các trường động
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


# --- Locust User ---
class MqttDeviceUser(User):
    wait_time = lambda self: 0  # task không chờ
    abstract = False

    def on_start(self):
        with client_lock:
            self.index = START_INDEX + len(all_devices) + 1
            device = DeviceClient(self.index)
            all_devices.append(device)
            self.client = device

        self.last_time_sync = time.time()
        self.last_scene_update = time.time()

    @task
    def send_device_messages(self):
        if not self.client.connected:
            return
        try:
            current_time = time.time()
            now = datetime.now()
            
            # Trigger 2: Định kỳ mỗi chu kỳ TELEMETRY_INTERVAL (mặc định 50 giây)
            if current_time - self.client.last_telemetry_time >= TELEMETRY_INTERVAL:
                self.client.send_status_update()
                self.client.last_telemetry_time = current_time

            # Trigger 3: Kiểm tra Kịch bản (Scene) chạy tự động
            current_day_str = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.weekday()] # VD: "Mon", "Tue"
            current_time_str = f"{now.hour}:{now.minute:02d}" # VD: "3:20"
            
            for scene_id, scene_info in self.client.scene_db.items():
                cond = scene_info.get("condition", {})
                target_time = cond.get("time")
                repeat_days = cond.get("repeat", [])
                
                # Chuẩn hóa format giờ (đề phòng server gửi "03:20" hay "3:20")
                if target_time:
                    try:
                        h, m = target_time.split(":")
                        target_time_norm = f"{int(h)}:{int(m):02d}"
                    except:
                        target_time_norm = target_time
                else:
                    target_time_norm = None

                if current_time_str == target_time_norm and current_day_str in repeat_days:
                    # Tránh chạy lặp lại trong cùng 1 phút
                    if scene_info["last_run_day"] != now.day or scene_info["last_run_minute"] != now.minute:
                        scene_info["last_run_day"] = now.day
                        scene_info["last_run_minute"] = now.minute
                        
                        execute = scene_info.get("execute", {})
                        if "relay1" in execute:
                            self.client.telemetry_db["relay1"] = execute["relay1"]
                        if "relay2" in execute:
                            self.client.telemetry_db["relay2"] = execute["relay2"]
                        if "dim" in execute:
                            self.client.telemetry_db["dim"] = execute["dim"]
                            
                        self.client.telemetry_db["scene_now"] = scene_id
                        
                        # Trigger gửi telemetry
                        self.client.send_status_update()
                        
                        # Trigger gửi báo cáo runScene
                        self.client.send_run_scene(scene_id)

            # Mỗi 30 phút: đồng bộ thời gian
            if time.time() - self.last_time_sync > 1800:
                self.client.send_time_sync()
                self.last_time_sync = time.time()
        except Exception:
            pass


# --- 🕒 Log tổng hợp định kỳ (như Gateway) ---
def periodic_log():
    while True:
        time.sleep(LOG_INTERVAL)
        with client_lock:
            connected_clients = sum(1 for d in all_devices if d.connected)
            disconnected_clients = len(all_devices) - connected_clients
            total_sent = sum(d.sent_messages for d in all_devices)
            total_recv = sum(d.received_messages for d in all_devices)
            total_rpc = sum(d.rpc_sent for d in all_devices)
            total_recv_rpc_resp = sum(d.msg_recv_rpc_resp for d in all_devices)
            total_recv_rpc_server = sum(d.msg_recv_rpc_server for d in all_devices)
            total_control = sum(d.control_messages for d in all_devices)
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
            f"Success Rate: {success_rate:.2f}%"
        )

        print(log_line.strip())

        # Lưu file log theo ngày
        log_filename = f"logs/device_{datetime.now().strftime('%Y-%m-%d')}.txt"
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(log_line)


# Khởi chạy thread log nền
log_thread = threading.Thread(target=periodic_log, daemon=True)
log_thread.start()
