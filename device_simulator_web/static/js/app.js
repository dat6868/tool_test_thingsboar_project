document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const configForm = document.getElementById('config-form');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const btnToggle = document.getElementById('btn-toggle');
    const btnLockConfig = document.getElementById('btn-lock-config');

    const toastContainer = document.getElementById('toast-container');
    const currentTimeEl = document.getElementById('current-time');

    let isRunning = false;
    let pollInterval = null;
    let renderedLogLinesCount = 0;
    let isConfigLocked = false;

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
    async function saveConfig() {
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
                data[input.id] = input.type === 'number' ? parseInt(val) : val;
            }
        });

        if (hasError) return false;

        // Validation cho dải chỉ số RPC không phản hồi
        if (rpcSelect && rpcSelect.value === 'range') {
            const startIndex = parseInt(document.getElementById('START_INDEX').value) || 0;
            const endIndex = parseInt(document.getElementById('END_INDEX').value) || 0;
            const skipStart = parseInt(document.getElementById('RESPONSE_RPC_SKIP_START').value) || 0;
            const skipEnd = parseInt(document.getElementById('RESPONSE_RPC_SKIP_END').value) || 0;
            
            const minAllowed = startIndex + 1;
            const maxAllowed = endIndex;

            if (skipStart < minAllowed || skipStart > maxAllowed) {
                showToast(`Chỉ số bắt đầu bỏ qua (${skipStart}) phải nằm trong khoảng từ ${minAllowed} đến ${maxAllowed}!`, 'error');
                return false;
            }
            if (skipEnd < skipStart || skipEnd > maxAllowed) {
                showToast(`Chỉ số kết thúc bỏ qua (${skipEnd}) phải từ ${skipStart} đến ${maxAllowed}!`, 'error');
                return false;
            }
        }

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const resData = await res.json();
            if (resData.status === 'success') {
                return true;
            } else {
                showToast(resData.message, 'error');
                return false;
            }
        } catch (err) {
            showToast('Lỗi mạng khi lưu cấu hình: ' + err.message, 'error');
            return false;
        }
    }

    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const success = await saveConfig();
        if (success) {
            showToast('Đã lưu cấu hình giả lập thành công!');
        }
    });

    // 4.1 Khóa/Mở khóa chỉnh sửa Cấu hình (Có mật khẩu bảo vệ)
    if (btnLockConfig) {
        btnLockConfig.addEventListener('click', () => {
            const inputs = configForm.querySelectorAll('input, textarea, select, #btn-save-config');
            if (!isConfigLocked) {
                // Đang mở -> Tiến hành khóa (Không cần mật khẩu)
                isConfigLocked = true;
                inputs.forEach(el => el.disabled = true);
                btnLockConfig.textContent = '🔒 ĐÃ KHÓA';
                btnLockConfig.style.backgroundColor = '#ef4444';
                showToast('Đã khóa chỉnh sửa cấu hình!');
            } else {
                // Đang khóa -> Tiến hành mở khóa (Yêu cầu mật khẩu)
                const password = prompt('Nhập mật khẩu để mở khóa chỉnh sửa cấu hình:');
                if (password === 'admin' || password === 'rangdong') {
                    isConfigLocked = false;
                    inputs.forEach(el => el.disabled = false);
                    btnLockConfig.textContent = '🔓 MỞ KHÓA';
                    btnLockConfig.style.backgroundColor = '#4b5563';
                    showToast('Đã mở khóa cấu hình thành công!');
                    if (window.rpcSelect) {
                        const rpcRangeRow = document.getElementById('rpc-range-row');
                        if (rpcRangeRow) {
                            rpcRangeRow.style.display = window.rpcSelect.value === 'range' ? 'grid' : 'none';
                        }
                    }
                } else {
                    if (password !== null) {
                        showToast('Mật khẩu không chính xác!', 'error');
                    }
                }
            }
        });
    }

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
                statusText.textContent = `RUNNING (${data.processes.length} dải)`;
                if (btnStopAll) btnStopAll.style.display = 'block';
            } else {
                statusDot.className = 'dot stopped';
                statusText.textContent = 'ĐANG DỪNG';
                if (btnStopAll) btnStopAll.style.display = 'none';
            }





            // Dựng bảng danh sách tiến trình đang chạy
            if (procBody) {
                if (data.processes && data.processes.length > 0) {
                    procBody.innerHTML = '';
                    data.processes.forEach(p => {
                        const paddingLen = p.end_index.toString().length;
                        
                        const firstNumStr = String(p.start_index + 1).padStart(paddingLen, '0');
                        const lastNumStr = String(p.end_index).padStart(paddingLen, '0');
                        
                        const firstId = `${p.device_id_prefix}${p.device_code_prefix}${firstNumStr}`;
                        const lastId = `${p.device_id_prefix}${p.device_code_prefix}${lastNumStr}`;
                        
                        const num_dev = p.end_index - p.start_index;
                        
                        const tr = document.createElement('tr');
                        tr.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                        tr.innerHTML = `
                            <td style="padding: 0.4rem; color: #a5b4fc; font-family: monospace;">${p.pid}</td>
                            <td style="padding: 0.4rem; color: #e2e8f0;">
                                <span style="font-weight:600; color:#38bdf8;">${firstId}</span> &rarr; <span style="font-weight:600; color:#38bdf8;">${lastId}</span>
                                <br><span style="font-size:0.7rem; color:var(--text-muted);">(${num_dev} TB | Broker: ${p.broker_host})</span>
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
            showToast('Đang lưu cấu hình...');
            const saveSuccess = await saveConfig();
            if (!saveSuccess) {
                return; // Có lỗi validation hoặc mạng khi lưu cấu hình
            }

            showToast('Đang khởi chạy dải thiết bị mới...');
            const res = await fetch('/api/start', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                showToast('Khởi chạy dải giả lập mới thành công!');
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

    // 8. Poll and Render Scenes
    const scenesListContainer = document.getElementById('scenes-list-container');
    const btnRefreshScenes = document.getElementById('btn-refresh-scenes');

    async function loadScenes() {
        if (!scenesListContainer) return;
        try {
            const res = await fetch('/api/scenes');
            const data = await res.json();
            
            if (Object.keys(data).length === 0) {
                scenesListContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 0.5rem;">Không có kịch bản nào được thiết lập.</div>';
                return;
            }

            // Gom nhóm kịch bản theo Scene ID
            const groupedScenes = {};
            for (const [devId, scenes] of Object.entries(data)) {
                for (const [sceneId, info] of Object.entries(scenes)) {
                    if (!groupedScenes[sceneId]) {
                        groupedScenes[sceneId] = {
                            condition: info.condition,
                            execute: info.execute,
                            devices: []
                        };
                    }
                    groupedScenes[sceneId].devices.push(devId);
                }
            }

            let html = '';
            for (const [sceneId, info] of Object.entries(groupedScenes)) {
                info.devices.sort();
                html += `
                <div style="border: 1px solid rgba(255,255,255,0.05); padding: 0.6rem; border-radius: 6px; background: rgba(255,255,255,0.02); margin-bottom: 0.6rem;">
                    <div style="font-weight: bold; color: #f59e0b; display: flex; justify-content: space-between; align-items: center;">
                        <span>🎬 Kịch bản ID: ${sceneId}</span>
                        <span style="font-size: 0.75rem; background: rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 10px; color: #34d399;">${info.devices.length} thiết bị</span>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.5rem; padding-left: 0.5rem; border-left: 2px solid var(--border-color);">
                        <div style="font-size: 0.75rem;"><span style="color: var(--text-muted); font-weight: 600;">Điều kiện:</span> <code style="color: #a7f3d0;">${JSON.stringify(info.condition)}</code></div>
                        <div style="font-size: 0.75rem;"><span style="color: var(--text-muted); font-weight: 600;">Hành động:</span> <code style="color: #93c5fd;">${JSON.stringify(info.execute)}</code></div>
                        <div style="font-size: 0.75rem; margin-top: 0.2rem;">
                            <span style="color: var(--text-muted); font-weight: 600; display: block; margin-bottom: 0.15rem;">Danh sách thiết bị nhận:</span>
                            <div style="max-height: 85px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 0.3rem 0.5rem; border-radius: 4px; color: #e2e8f0; font-family: monospace; line-height: 1.3; word-break: break-all;">
                                ${info.devices.join(', ')}
                            </div>
                        </div>
                    </div>
                </div>
                `;
            }
            scenesListContainer.innerHTML = html;
        } catch (err) {
            console.error("Lỗi khi tải danh sách kịch bản:", err);
        }
    }

    if (btnRefreshScenes) {
        btnRefreshScenes.addEventListener('click', loadScenes);
    }

    // Khởi chạy ban đầu
    loadConfig();
    pollStatus();
    loadScenes();
    setInterval(pollStatus, 5000); // Polling mỗi 5 giây để cập nhật nhanh danh sách dải và số liệu
});
