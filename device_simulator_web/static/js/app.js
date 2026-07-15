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

    const btnStopAll = document.getElementById('btn-stop-all');
    const procBody = document.getElementById('processes-list-body');

    // 5. Polling Status
    async function pollStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            // Cập nhật trạng thái chạy
            isRunning = data.is_running;
            if (isRunning) {
                statusDot.className = 'dot running';
                statusText.textContent = `ĐANG GIẢ LẬP (${data.processes.length} dải)`;
                if (btnStopAll) btnStopAll.style.display = 'block';
            } else {
                statusDot.className = 'dot stopped';
                statusText.textContent = 'ĐANG DỪNG';
                if (btnStopAll) btnStopAll.style.display = 'none';
            }

            // Cập nhật Thống kê tổng
            statConnected.textContent = data.stats.connected || 0;
            statDisconnected.textContent = data.stats.disconnected || 0;
            statSent.textContent = data.stats.sent || 0;
            statReceived.textContent = data.stats.received || 0;
            statRpcSent.textContent = data.stats.rpc_sent || 0;
            statSuccessRate.textContent = (data.stats.success_rate || 0).toFixed(2) + '%';

            // Cập nhật log tĩnh
            terminalBody.innerHTML = '<div class="terminal-line" style="color: #fbbf24; font-weight: bold; text-align: center; margin-top: 1rem;">⚠️ Vì vấn đề hiệu năng, hãy xem log trực tiếp tại terminal!</div>';

            // Dựng bảng danh sách tiến trình đang chạy
            if (procBody) {
                if (data.processes && data.processes.length > 0) {
                    procBody.innerHTML = '';
                    data.processes.forEach(p => {
                        const maxVal = p.start_index + p.num_dev;
                        const paddingLen = Math.max(3, maxVal.toString().length);
                        
                        const firstNumStr = String(p.start_index + 1).padStart(paddingLen, '0');
                        const lastNumStr = String(p.start_index + p.num_dev).padStart(paddingLen, '0');
                        
                        const firstId = `${p.device_id_prefix}${p.device_code_prefix}${firstNumStr}`;
                        const lastId = `${p.device_id_prefix}${p.device_code_prefix}${lastNumStr}`;
                        
                        const tr = document.createElement('tr');
                        tr.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                        tr.innerHTML = `
                            <td style="padding: 0.4rem; color: #a5b4fc; font-family: monospace;">${p.pid}</td>
                            <td style="padding: 0.4rem; color: #e2e8f0;">
                                <span style="font-weight:600; color:#38bdf8;">${firstId}</span> &rarr; <span style="font-weight:600; color:#38bdf8;">${lastId}</span>
                                <br><span style="font-size:0.7rem; color:var(--text-muted);">(${p.num_dev} TB | Broker: ${p.broker_host})</span>
                            </td>
                            <td style="padding: 0.4rem; text-align: right;">
                                <button class="btn-stop-single" data-pid="${p.pid}" style="background: #ef4444; color:#fff; border:none; padding:0.2rem 0.4rem; border-radius:4px; font-size:0.75rem; cursor:pointer; font-weight:600; transition:all 0.2s; white-space:nowrap;">DỪNG 🛑</button>
                            </td>
                        `;
                        procBody.appendChild(tr);
                    });

                    // Gắn sự kiện dừng đơn lẻ
                    procBody.querySelectorAll('.btn-stop-single').forEach(btn => {
                        btn.addEventListener('click', async () => {
                            const pid = btn.getAttribute('data-pid');
                            try {
                                const res = await fetch('/api/stop', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ pid: parseInt(pid) })
                                });
                                const resData = await res.json();
                                if (resData.status === 'success') {
                                    showToast(`Đã dừng tiến trình PID ${pid} thành công!`);
                                    pollStatus();
                                } else {
                                    showToast(resData.message, 'error');
                                }
                            } catch (err) {
                                showToast('Lỗi mạng khi dừng tiến trình: ' + err.message, 'error');
                            }
                        });
                    });
                } else {
                    procBody.innerHTML = `
                        <tr>
                            <td colspan="3" style="padding: 0.5rem; text-align: center; color: var(--text-muted);">Không có dải giả lập nào đang chạy.</td>
                        </tr>
                    `;
                }
            }

        } catch (e) {
            console.error("Lỗi polling:", e);
        }
    }

    // 6. Start Button Listener (Khởi chạy dải thiết bị mới)
    btnToggle.addEventListener('click', async () => {
        try {
            showToast('Đang khởi chạy dải thiết bị mới...');
            const res = await fetch('/api/start', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                showToast('Khởi chạy dải giả lập mới thành công! (Mẹo: hãy bấm Lưu cấu hình trước khi chạy nếu có thay đổi)');
                pollStatus();
            } else {
                showToast(data.message, 'error');
            }
        } catch (err) {
            showToast('Lỗi mạng khi khởi chạy: ' + err.message, 'error');
        }
    });

    // 7. Stop All Button Listener
    if (btnStopAll) {
        btnStopAll.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast('Đã dừng toàn bộ tiến trình giả lập thành công!');
                    pollStatus();
                } else {
                    showToast(data.message, 'error');
                }
            } catch (err) {
                showToast('Lỗi mạng khi dừng toàn bộ: ' + err.message, 'error');
            }
        });
    }

    // Khởi chạy ban đầu
    loadConfig();
    pollStatus();
    setInterval(pollStatus, 5000); // Polling mỗi 5 giây để cập nhật nhanh danh sách dải và số liệu
});
