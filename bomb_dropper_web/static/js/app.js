document.addEventListener('DOMContentLoaded', () => {
    // Menu Switching
    const menuBtns = document.querySelectorAll('.menu-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    menuBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            menuBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const targetId = btn.getAttribute('data-target');
            tabContents.forEach(tab => {
                if (tab.id === targetId) {
                    tab.classList.remove('hidden');
                    tab.classList.add('active');
                } else {
                    tab.classList.remove('active');
                    tab.classList.add('hidden');
                }
            });
        });
    });

    // Toast Notification
    function showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.style.background = type === 'success' ? 'rgba(16, 185, 129, 0.9)' : 'rgba(239, 68, 68, 0.9)';
        toast.classList.remove('hidden');
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            setTimeout(() => toast.classList.add('hidden'), 300);
        }, 3000);
    }

    // Login Logic
    let jwtToken = null;
    document.getElementById('btn-login').addEventListener('click', async () => {
        const url = document.getElementById('server-url').value;
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, username, password })
            });
            const data = await res.json();
            
            if (data.status === 'success') {
                jwtToken = data.token;
                showToast('Lấy JWT Token thành công!');
            } else {
                showToast(data.message, 'error');
            }
        } catch (e) {
            showToast('Lỗi mạng: ' + e.message, 'error');
        }
    });

    // Dynamic API Panels
    const apiList = document.getElementById('api-list');
    let apiCount = 0;

    document.getElementById('btn-add-api').addEventListener('click', () => {
        let apiName = prompt("Nhập tên gợi nhớ cho API này:", `API Hiệu năng ${apiCount + 1}`);
        if (!apiName) apiName = "Lệnh cURL";

        apiCount++;
        const id = `api-${apiCount}`;
        const html = `
            <div class="api-item" id="${id}">
                <label class="api-title" title="Nhấp đúp để đổi tên" style="cursor: pointer; font-weight: bold; color: var(--primary);">${apiName}:</label>
                <textarea placeholder="Dán lệnh cURL vào đây..."></textarea>
                <div class="api-config-row">
                    <div class="api-rates">
                        <label>Start (req/s):</label>
                        <input type="number" class="api-rate" value="10">
                        <label>Step/5s:</label>
                        <input type="number" class="api-step" value="5">
                    </div>
                    <button class="btn btn-secondary btn-remove" data-target="${id}">Xóa</button>
                </div>
            </div>
        `;
        apiList.insertAdjacentHTML('beforeend', html);
    });

    apiList.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-remove')) {
            const targetId = e.target.getAttribute('data-target');
            document.getElementById(targetId).remove();
        }
    });

    apiList.addEventListener('dblclick', (e) => {
        if (e.target.classList.contains('api-title')) {
            let currentName = e.target.textContent.replace(':', '');
            let newName = prompt("Đổi tên API:", currentName);
            if (newName && newName.trim() !== "") {
                e.target.textContent = newName.trim() + ':';
            }
        }
    });

    // Engine Control & Status Polling
    let isRunning = false;
    let pollInterval = null;
    const btnToggle = document.getElementById('btn-toggle');
    const logOutput = document.getElementById('log-output');
    const thresholdContainer = document.getElementById('threshold-container');

    function addLog(msg) {
        const isError = msg.includes('LỖI') || msg.includes('MẠCH BẢO VỆ');
        const isWarning = msg.includes('TĂNG TỐC');
        const div = document.createElement('div');
        div.className = 'terminal-line';
        if (isError) div.classList.add('error');
        if (isWarning) div.classList.add('warning');
        div.textContent = msg;
        logOutput.appendChild(div);
        logOutput.scrollTop = logOutput.scrollHeight;
    }

    // Export Logic
    document.getElementById('btn-export').addEventListener('click', () => {
        const apiItems = document.querySelectorAll('.api-item');
        if (apiItems.length === 0) {
            showToast('Không có dữ liệu API nào để xuất!', 'error');
            return;
        }

        let report = `BÁO CÁO KẾT QUẢ LOAD TEST API - ${new Date().toLocaleString()}\n`;
        report += "=".repeat(60) + "\n\n";

        let idx = 1;
        apiItems.forEach(item => {
            const curl = item.querySelector('textarea').value.trim();
            if (!curl) return;

            const urlMatch = curl.match(/https?:\/\/[^\s'"]+/);
            const url = urlMatch ? urlMatch[0] : 'N/A';
            const methodMatch = curl.match(/-X\s+([A-Z]+)/);
            const method = methodMatch ? methodMatch[1] : 'GET';

            const rate = parseInt(item.querySelector('.api-rate').value);
            const step = parseInt(item.querySelector('.api-step').value);
            const apiName = item.querySelector('.api-title').textContent.replace(':', '');

            report += `--- ${apiName} ---\n`;
            report += `URL: ${url}\n`;
            report += `Method: ${method}\n`;
            report += `Cấu hình Test: Bắt đầu ${rate} req/s | Tăng ${step} req/s mỗi 5s\n`;
            
            const thresholds = Array.from(thresholdContainer.children).map(s => s.textContent);
            if (thresholds.length > 0) {
                report += `KẾT QUẢ: ${thresholds.join(' | ')}\n`;
            } else {
                report += `KẾT QUẢ: Chưa có (Hoặc Test chưa chạm ngưỡng chết)\n`;
            }
            report += "-".repeat(40) + "\n\n";
            idx++;
        });

        const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `load_test_report_${new Date().getTime()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        showToast('Đã tải báo cáo xuống thành công!');
    });

    async function toggleEngine() {
        if (isRunning) {
            // Stop
            await fetch('/api/stop', { method: 'POST' });
        } else {
            // Start
            const apiItems = document.querySelectorAll('.api-item');
            if (apiItems.length === 0) {
                showToast('Vui lòng thêm ít nhất 1 API', 'error');
                return;
            }

            const apis = [];
            apiItems.forEach(item => {
                const curl = item.querySelector('textarea').value.trim();
                const rate = parseInt(item.querySelector('.api-rate').value);
                const step = parseInt(item.querySelector('.api-step').value);
                if (curl) {
                    apis.push({ curl, rate, step });
                }
            });

            if (apis.length === 0) {
                showToast('Vui lòng nhập nội dung cURL', 'error');
                return;
            }

            logOutput.innerHTML = '';
            thresholdContainer.innerHTML = '';

            const loginUrl = document.getElementById('server-url').value;
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            const res = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: jwtToken, login_url: loginUrl, username: username, password: password, apis: apis })
            });
            const data = await res.json();
            if (data.status === 'error') {
                showToast(data.message, 'error');
                return;
            }
        }
        
        // Trạng thái sẽ được hàm pollStatus tự động cập nhật
    }

    btnToggle.addEventListener('click', toggleEngine);

    // Status Polling
    async function pollStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            updateLockUI(data.is_locked);

            // Update running state & Button
            if (data.is_running !== isRunning) {
                isRunning = data.is_running;
                if (isRunning) {
                    btnToggle.textContent = 'DỪNG LẠI 🛑';
                    btnToggle.style.background = '#f59e0b'; // orange/yellow
                } else {
                    btnToggle.textContent = 'BẮT ĐẦU';
                    btnToggle.style.background = '#ef4444'; // red
                }
            }

            // Update Stats
            document.getElementById('stat-success').textContent = data.stats.success;
            document.getElementById('stat-fail').textContent = data.stats.fail;

            // Add logs
            if (data.logs && data.logs.length > 0) {
                data.logs.forEach(log => addLog(log));
            }

            // Update Thresholds
            if (data.thresholds && data.thresholds.length > 0) {
                thresholdContainer.innerHTML = '';
                data.thresholds.forEach(t => {
                    const span = document.createElement('span');
                    span.style.color = '#ef4444';
                    span.style.fontWeight = 'bold';
                    span.style.display = 'block';
                    span.textContent = t;
                    thresholdContainer.appendChild(span);
                });
            }

        } catch (e) {
            console.error('Polling error', e);
        }
    }

    // Start polling loop
    pollInterval = setInterval(pollStatus, 500);

    // ==========================================
    // LOCK LOGIC
    // ==========================================
    const btnLock = document.getElementById('btn-lock');
    const btnUnlock = document.getElementById('btn-unlock');

    btnLock.addEventListener('click', async () => {
        const pwd = prompt("Nhập mã PIN để khóa Tool (Ví dụ: 1234):");
        if (!pwd) return;

        const res = await fetch('/api/lock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Đã khóa Tool thành công!');
        } else {
            showToast(data.message, 'error');
        }
    });

    btnUnlock.addEventListener('click', async () => {
        const pwd = prompt("Nhập mã PIN để MỞ KHÓA:");
        if (!pwd) return;

        const res = await fetch('/api/unlock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Đã mở khóa thành công!');
        } else {
            showToast(data.message, 'error');
        }
    });

    function updateLockUI(isLocked) {
        if (isLocked) {
            document.body.classList.add('locked-mode');
            btnLock.classList.add('hidden');
            btnUnlock.classList.remove('hidden');
        } else {
            document.body.classList.remove('locked-mode');
            btnLock.classList.remove('hidden');
            btnUnlock.classList.add('hidden');
        }
    }

    // ==========================================
    // BASIC TEST LOGIC
    // ==========================================
    const apiListBasic = document.getElementById('api-list-basic');
    let apiCountBasic = 0;

    document.getElementById('btn-add-api-basic').addEventListener('click', () => {
        let apiName = prompt("Nhập tên gợi nhớ cho API này:", `API Cơ bản ${apiCountBasic + 1}`);
        if (!apiName) apiName = "Lệnh cURL";

        apiCountBasic++;
        const id = `api-basic-${apiCountBasic}`;
        const html = `
            <div class="api-item basic-api-item" id="${id}">
                <label class="api-title" title="Nhấp đúp để đổi tên" style="cursor: pointer; font-weight: bold; color: var(--primary);">${apiName}:</label>
                <textarea placeholder="Dán lệnh cURL vào đây..."></textarea>
                <div class="api-config-row">
                    <div class="api-rates">
                        <label>Chu kỳ (giây):</label>
                        <input type="number" class="api-interval" value="5">
                    </div>
                    <button class="btn btn-secondary btn-remove-basic" data-target="${id}">Xóa</button>
                </div>
            </div>
        `;
        apiListBasic.insertAdjacentHTML('beforeend', html);
    });

    apiListBasic.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-remove-basic')) {
            const targetId = e.target.getAttribute('data-target');
            document.getElementById(targetId).remove();
        }
    });

    apiListBasic.addEventListener('dblclick', (e) => {
        if (e.target.classList.contains('api-title')) {
            let currentName = e.target.textContent.replace(':', '');
            let newName = prompt("Đổi tên API:", currentName);
            if (newName && newName.trim() !== "") {
                e.target.textContent = newName.trim() + ':';
            }
        }
    });

    let isBasicRunning = false;
    const btnToggleBasic = document.getElementById('btn-toggle-basic');
    const logOutputBasic = document.getElementById('log-output-basic');

    function addLogBasic(msg) {
        const isError = msg.includes('❌');
        const div = document.createElement('div');
        div.className = 'terminal-line';
        if (isError) div.classList.add('error');
        div.textContent = msg;
        logOutputBasic.appendChild(div);
        logOutputBasic.scrollTop = logOutputBasic.scrollHeight;
    }

    document.getElementById('btn-export-basic').addEventListener('click', () => {
        const apiItems = document.querySelectorAll('.basic-api-item');
        if (apiItems.length === 0) {
            showToast('Không có dữ liệu API nào để xuất!', 'error');
            return;
        }

        let report = `BÁO CÁO KẾT QUẢ KIỂM TRA CƠ BẢN - ${new Date().toLocaleString()}\n`;
        report += "=".repeat(60) + "\n\n";

        let idx = 1;
        apiItems.forEach(item => {
            const curl = item.querySelector('textarea').value.trim();
            if (!curl) return;

            const urlMatch = curl.match(/https?:\/\/[^\s'"]+/);
            const url = urlMatch ? urlMatch[0] : 'N/A';
            const methodMatch = curl.match(/-X\s+([A-Z]+)/);
            const method = methodMatch ? methodMatch[1] : 'GET';
            const interval = parseInt(item.querySelector('.api-interval').value);
            const apiName = item.querySelector('.api-title').textContent.replace(':', '');

            report += `--- ${apiName} ---\n`;
            report += `URL: ${url}\n`;
            report += `Method: ${method}\n`;
            report += `Chu kỳ: ${interval} giây / 1 request\n`;
            report += "-".repeat(40) + "\n\n";
            idx++;
        });

        const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `basic_test_report_${new Date().getTime()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        showToast('Đã tải báo cáo xuống thành công!');
    });

    btnToggleBasic.addEventListener('click', async () => {
        if (isBasicRunning) {
            await fetch('/api/stop_basic', { method: 'POST' });
        } else {
            const apiItems = document.querySelectorAll('.basic-api-item');
            if (apiItems.length === 0) {
                showToast('Vui lòng thêm ít nhất 1 API', 'error');
                return;
            }

            const apis = [];
            apiItems.forEach(item => {
                const curl = item.querySelector('textarea').value.trim();
                const interval = parseInt(item.querySelector('.api-interval').value);
                if (curl) {
                    apis.push({ curl, interval });
                }
            });

            if (apis.length === 0) {
                showToast('Vui lòng nhập nội dung cURL', 'error');
                return;
            }

            logOutputBasic.innerHTML = '';

            const loginUrl = document.getElementById('server-url').value;
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            const res = await fetch('/api/start_basic', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: jwtToken, login_url: loginUrl, username: username, password: password, apis: apis })
            });
            const data = await res.json();
            if (data.status === 'error') {
                showToast(data.message, 'error');
                return;
            }
        }
    });

    async function pollBasicStatus() {
        try {
            const res = await fetch('/api/status_basic');
            const data = await res.json();

            updateLockUI(data.is_locked);

            if (data.is_running !== isBasicRunning) {
                isBasicRunning = data.is_running;
                if (isBasicRunning) {
                    btnToggleBasic.textContent = 'DỪNG LẠI 🛑';
                    btnToggleBasic.style.background = '#f59e0b';
                } else {
                    btnToggleBasic.textContent = 'BẮT ĐẦU';
                    btnToggleBasic.style.background = '#10b981'; // green
                }
            }

            document.getElementById('stat-success-basic').textContent = data.stats.success;
            document.getElementById('stat-fail-basic').textContent = data.stats.fail;

            if (data.logs && data.logs.length > 0) {
                data.logs.forEach(log => addLogBasic(log));
            }

        } catch (e) {
            console.error('Basic Polling error', e);
        }
    }

    setInterval(pollBasicStatus, 500);

    // ==========================================
    // DATABASE SAVE/LOAD LOGIC
    // ==========================================
    function saveStateToLocal() {
        const state = {
            url: document.getElementById('server-url').value,
            username: document.getElementById('username').value,
            jwtToken: jwtToken,
            apis: [],
            basicApis: []
        };
        
        document.querySelectorAll('.api-item:not(.basic-api-item)').forEach(item => {
            state.apis.push({
                name: item.querySelector('.api-title').textContent.replace(':', ''),
                curl: item.querySelector('textarea').value,
                rate: item.querySelector('.api-rate').value,
                step: item.querySelector('.api-step').value
            });
        });

        document.querySelectorAll('.basic-api-item').forEach(item => {
            state.basicApis.push({
                name: item.querySelector('.api-title').textContent.replace(':', ''),
                curl: item.querySelector('textarea').value,
                interval: item.querySelector('.api-interval').value
            });
        });

        fetch('/api/database', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state)
        }).catch(e => console.error("Lỗi lưu DB", e));
    }

    async function loadStateFromLocal() {
        try {
            const res = await fetch('/api/database');
            const state = await res.json();
            
            if (Object.keys(state).length === 0) return;
            
            if (state.url) document.getElementById('server-url').value = state.url;
            if (state.username) document.getElementById('username').value = state.username;
            if (state.jwtToken) jwtToken = state.jwtToken;
            
            if (state.apis && state.apis.length > 0) {
                state.apis.forEach(api => {
                    apiCount++;
                    const id = `api-${apiCount}`;
                    const html = `
                        <div class="api-item" id="${id}">
                            <label class="api-title" title="Nhấp đúp để đổi tên" style="cursor: pointer; font-weight: bold; color: var(--primary);">${api.name}:</label>
                            <textarea placeholder="Dán lệnh cURL vào đây...">${api.curl}</textarea>
                            <div class="api-config-row">
                                <div class="api-rates">
                                    <label>Start (req/s):</label>
                                    <input type="number" class="api-rate" value="${api.rate}">
                                    <label>Step/5s:</label>
                                    <input type="number" class="api-step" value="${api.step}">
                                </div>
                                <button class="btn btn-secondary btn-remove" data-target="${id}">Xóa</button>
                            </div>
                        </div>
                    `;
                    apiList.insertAdjacentHTML('beforeend', html);
                });
            }

            if (state.basicApis && state.basicApis.length > 0) {
                state.basicApis.forEach(api => {
                    apiCountBasic++;
                    const id = `api-basic-${apiCountBasic}`;
                    const html = `
                        <div class="api-item basic-api-item" id="${id}">
                            <label class="api-title" title="Nhấp đúp để đổi tên" style="cursor: pointer; font-weight: bold; color: var(--primary);">${api.name}:</label>
                            <textarea placeholder="Dán lệnh cURL vào đây...">${api.curl}</textarea>
                            <div class="api-config-row">
                                <div class="api-rates">
                                    <label>Chu kỳ (giây):</label>
                                    <input type="number" class="api-interval" value="${api.interval}">
                                </div>
                                <button class="btn btn-secondary btn-remove-basic" data-target="${id}">Xóa</button>
                            </div>
                        </div>
                    `;
                    apiListBasic.insertAdjacentHTML('beforeend', html);
                });
            }
        } catch (e) {
            console.error("Lỗi tải DB", e);
        }
    }

    loadStateFromLocal();
    setInterval(saveStateToLocal, 2000);

});
