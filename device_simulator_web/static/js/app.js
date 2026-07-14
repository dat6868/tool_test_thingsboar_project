document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const configForm = document.getElementById('config-form');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const btnToggle = document.getElementById('btn-toggle');
    const terminalBody = document.getElementById('terminal-body');
    const toastContainer = document.getElementById('toast-container');
    const currentTimeEl = document.getElementById('current-time');

    // Stat Elements
    const statConnected = document.getElementById('stat-connected');
    const statDisconnected = document.getElementById('stat-disconnected');
    const statSent = document.getElementById('stat-sent');
    const statReceived = document.getElementById('stat-received');
    const statRpcSent = document.getElementById('stat-rpc-sent');
    const statSuccessRate = document.getElementById('stat-success-rate');

    let isRunning = false;
    let pollInterval = null;
    let renderedLogLinesCount = 0;

    // 1. Clock in Header
    function updateClock() {
        const now = new Date();
        currentTimeEl.textContent = now.toLocaleTimeString('vi-VN') + ' - ' + now.toLocaleDateString('vi-VN');
    }
    setInterval(updateClock, 1000);
    updateClock();

    // 2. Toast Notification Helper
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon = '🔔';
        if (type === 'success') icon = '✅';
        if (type === 'error') icon = '❌';
        
        toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            toast.style.transition = 'all 0.5s ease';
            setTimeout(() => toast.remove(), 500);
        }, 3000);
    }

    // Bind RESPONSE_RPC change event to show/hide range row
    const rpcSelect = document.getElementById('RESPONSE_RPC');
    const rpcRangeRow = document.getElementById('rpc-skip-range-row');
    if (rpcSelect && rpcRangeRow) {
        rpcSelect.addEventListener('change', () => {
            rpcRangeRow.style.display = rpcSelect.value === 'range' ? 'grid' : 'none';
        });
    }

    // 3. Load Config from Backend
    async function loadConfig() {
        try {
            const res = await fetch('/api/config');
            const cfg = await res.json();
            
            // Map JSON keys directly to input IDs
            for (const key in cfg) {
                const el = document.getElementById(key);
                if (el) {
                    if (key === 'TELEMETRY_DATA') {
                        el.value = JSON.stringify(cfg[key], null, 4);
                    } else {
                        el.value = cfg[key].toString();
                    }
                }
            }

            // Sync range row visibility
            if (rpcSelect && rpcRangeRow) {
                rpcRangeRow.style.display = rpcSelect.value === 'range' ? 'grid' : 'none';
            }
        } catch (e) {
            showToast('Lỗi khi tải cấu hình: ' + e.message, 'error');
        }
    }

    // 4. Save Config to Backend
    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const inputs = configForm.querySelectorAll('input, textarea, select');
        const data = {};
        let hasError = false;
        
        inputs.forEach(input => {
            if (hasError) return;
            const val = input.value;
            if (input.id === 'TELEMETRY_DATA') {
                try {
                    data[input.id] = JSON.parse(val);
                } catch (err) {
                    showToast('Dữ liệu Telemetry không đúng định dạng JSON hợp lệ!', 'error');
                    hasError = true;
                }
            } else {
                // Ép kiểu số nếu input có kiểu number
                data[input.id] = input.type === 'number' ? parseInt(val) : val;
            }
        });

        // Validation cho dải chỉ số RPC không phản hồi
        if (!hasError && rpcSelect && rpcSelect.value === 'range') {
            const startIndex = parseInt(document.getElementById('START_INDEX').value) || 0;
            const numDev = parseInt(document.getElementById('NUM_DEV').value) || 0;
            const skipStart = parseInt(document.getElementById('RESPONSE_RPC_SKIP_START').value) || 0;
            const skipEnd = parseInt(document.getElementById('RESPONSE_RPC_SKIP_END').value) || 0;
            
            const minAllowed = startIndex + 1;
            const maxAllowed = startIndex + numDev;

            if (skipStart < minAllowed || skipStart > maxAllowed) {
                showToast(`Chỉ số bắt đầu bỏ qua (${skipStart}) phải nằm trong khoảng từ ${minAllowed} đến ${maxAllowed}!`, 'error');
                hasError = true;
            }
            if (!hasError && (skipEnd < skipStart || skipEnd > maxAllowed)) {
                showToast(`Chỉ số kết thúc bỏ qua (${skipEnd}) phải từ ${skipStart} đến ${maxAllowed}!`, 'error');
                hasError = true;
            }
        }

        if (hasError) return;

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const resData = await res.json();
            if (resData.status === 'success') {
                showToast('Đã lưu cấu hình giả lập thành công!');
            } else {
                showToast(resData.message, 'error');
            }
        } catch (err) {
            showToast('Lỗi mạng khi lưu cấu hình: ' + err.message, 'error');
        }
    });

    // 5. Polling Status
    async function pollStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            // Cập nhật trạng thái chạy
            isRunning = data.is_running;
            if (isRunning) {
                statusDot.className = 'dot running';
                statusText.textContent = 'ĐANG GIẢ LẬP';
                btnToggle.textContent = 'DỪNG LẠI 🛑';
                btnToggle.className = 'btn btn-danger';
                configForm.querySelectorAll('input, textarea, select, button[type="submit"]').forEach(el => el.disabled = true);
            } else {
                statusDot.className = 'dot stopped';
                statusText.textContent = 'ĐANG DỪNG';
                btnToggle.textContent = 'BẮT ĐẦU 🚀';
                btnToggle.className = 'btn btn-success';
                configForm.querySelectorAll('input, textarea, select, button[type="submit"]').forEach(el => el.disabled = false);
            }

            // Cập nhật Thống kê
            statConnected.textContent = data.stats.connected || 0;
            statDisconnected.textContent = data.stats.disconnected || 0;
            statSent.textContent = data.stats.sent || 0;
            statReceived.textContent = data.stats.received || 0;
            statRpcSent.textContent = data.stats.rpc_sent || 0;
            statSuccessRate.textContent = (data.stats.success_rate || 0).toFixed(2) + '%';

            // Cập nhật log lên Terminal
            if (data.logs && data.logs.length > 0) {
                // Nếu số dòng log nhận được nhiều hơn số dòng hiện tại
                if (data.logs.length > renderedLogLinesCount) {
                    // Xóa dòng chờ nếu có
                    if (renderedLogLinesCount === 0) {
                        terminalBody.innerHTML = '';
                    }

                    const newLines = data.logs.slice(renderedLogLinesCount);
                    newLines.forEach(line => {
                        const div = document.createElement('div');
                        div.className = 'terminal-line';
                        
                        // Thêm màu đỏ cho dòng báo lỗi nếu có
                        if (line.includes('Disconnected:') && !line.includes('Disconnected: 0,')) {
                            div.style.color = '#ef4444';
                        }
                        
                        div.textContent = line;
                        terminalBody.appendChild(div);
                    });

                    renderedLogLinesCount = data.logs.length;
                    // Tự động cuộn xuống cuối
                    terminalBody.scrollTop = terminalBody.scrollHeight;
                }
            } else if (!isRunning) {
                renderedLogLinesCount = 0;
                terminalBody.innerHTML = '<div class="terminal-line">Đang đợi khởi động giả lập...</div>';
            }

        } catch (e) {
            console.error("Lỗi polling:", e);
        }
    }

    // 6. Start/Stop Button Click Listener
    btnToggle.addEventListener('click', async () => {
        const url = isRunning ? '/api/stop' : '/api/start';
        const actionText = isRunning ? 'Dừng' : 'Bắt đầu';

        try {
            const res = await fetch(url, { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                showToast(`Đã gửi lệnh ${actionText} thành công!`);
                pollStatus(); // Cập nhật trạng thái tức thì
            } else {
                showToast(data.message, 'error');
            }
        } catch (err) {
            showToast(`Lỗi khi gửi lệnh ${actionText}: ` + err.message, 'error');
        }
    });

    // Khởi chạy ban đầu
    loadConfig();
    pollStatus();
    setInterval(pollStatus, 1000); // Polling mỗi giây
});
