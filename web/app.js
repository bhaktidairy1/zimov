document.addEventListener("DOMContentLoaded", () => {
    // UI Elements
    const loginScreen = document.getElementById("login-screen");
    const dashScreen = document.getElementById("dashboard-screen");
    const connectBtn = document.getElementById("connect-btn");
    const urlInput = document.getElementById("mageurl-input");
    const statusMsg = document.getElementById("login-status");

    // Controls
    const modeBtns = document.querySelectorAll(".mode-btn");
    const pauseBtn = document.getElementById("pause-btn");
    const hexInput = document.getElementById("hex-input");
    const injectBtn = document.getElementById("inject-btn");
    const mapNameSpan = document.getElementById("map-name");
    
    // Components
    const radarList = document.getElementById("radar-list");
    const inventoryList = document.getElementById("inventory-list");
    const terminal = document.getElementById("terminal");

    let isConnected = false;
    let pollInterval = null;

    // --- Login ---
    connectBtn.addEventListener("click", () => {
        const url = urlInput.value.trim();
        if(!url) return;
        
        connectBtn.disabled = true;
        statusMsg.textContent = "Negotiating Neural Link...";

        fetch("/api/connect", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({url})
        })
        .then(res => res.json())
        .then(data => {
            // fast-polling state
            pollInterval = setInterval(fetchState, 500); 
            setInterval(fetchLogs, 500);
        })
        .catch(err => {
            statusMsg.textContent = "Fatal: Server unverified.";
            connectBtn.disabled = false;
        });
    });

    function transitionToDashboard() {
        if(isConnected) return;
        isConnected = true;
        loginScreen.classList.remove("active");
        loginScreen.classList.add("hidden");
        
        // Wait for class transitions
        setTimeout(() => {
            dashScreen.classList.remove("hidden");
            dashScreen.classList.add("active");
        }, 100);
    }

    // --- Polling Logic ---
    function fetchState() {
        fetch("/api/state")
        .then(r => r.json())
        .then(data => {
            if(data.connected && !isConnected) {
                transitionToDashboard();
            }

            if(isConnected) {
                updateControls(data);
                updateRadar(data);
                updateInventory(data);
                if (data.map_name) {
                    mapNameSpan.textContent = data.map_name;
                }
            }
        });
    }

    function fetchLogs() {
        fetch("/api/logs")
        .then(r => r.json())
        .then(data => {
            if(data.logs && data.logs.length > 0) {
                let isScrolledToBottom = terminal.scrollHeight - terminal.clientHeight <= terminal.scrollTop + 1;
                
                data.logs.forEach(log => {
                    let span = document.createElement("span");
                    span.textContent = log;
                    if(log.includes("←")) span.className = "log-recv";
                    else if (log.includes("→")) span.className = "log-send";
                    else if (log.includes("[!]")) span.className = "log-warn";
                    
                    terminal.appendChild(span);
                });

                if(isScrolledToBottom) {
                    terminal.scrollTop = terminal.scrollHeight;
                }
            }
        });
    }

    // --- API Writers ---
    function sendAction(payload) {
        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });
    }

    // --- Interaction Binding ---
    modeBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            const mode = e.target.dataset.mode;
            sendAction({type: "set_mode", mode: mode});
        });
    });

    pauseBtn.addEventListener("click", () => {
        sendAction({type: "toggle_pause"});
    });

    injectBtn.addEventListener("click", () => {
        const hex = hexInput.value;
        if(hex) {
            sendAction({type: "inject_hex", hex: hex});
            hexInput.value = "";
        }
    });

    // Teleport
    const tpMapId = document.getElementById("tp-mapid");
    const tpX = document.getElementById("tp-x");
    const tpY = document.getElementById("tp-y");
    const tpBtn = document.getElementById("tp-btn");
    const tpStatus = document.getElementById("tp-status");

    tpBtn.addEventListener("click", () => {
        const mapId = tpMapId.value.trim();
        if(!mapId) {
            tpStatus.textContent = "Enter a map ID";
            tpStatus.className = "tp-status-msg tp-error";
            return;
        }

        const payload = {type: "teleport", map_id: parseInt(mapId)};
        const xVal = tpX.value.trim();
        const yVal = tpY.value.trim();
        if(xVal) payload.x = parseInt(xVal);
        if(yVal) payload.y = parseInt(yVal);

        sendAction(payload);
        tpStatus.textContent = "Warping to " + mapId + "...";
        tpStatus.className = "tp-status-msg tp-ok";
        setTimeout(() => { tpStatus.textContent = ""; }, 3000);
    });

    // Zimov Button
    const zimovBtn = document.getElementById("zimov-btn");
    const zimovStatus = document.getElementById("zimov-status");

    zimovBtn.addEventListener("click", () => {
        zimovBtn.disabled = true;
        zimovStatus.textContent = "Initiating Zimov Sequence...";
        zimovStatus.className = "tp-status-msg tp-ok";

        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type: "zimov_boss"})
        }).then(r => r.json()).then(data => {
            if (data.status === "error") {
                zimovStatus.textContent = data.message;
                zimovStatus.className = "tp-status-msg tp-error";
                zimovBtn.disabled = false;
            } else {
                zimovStatus.textContent = "Sequence Running...";
                setTimeout(() => { zimovStatus.textContent = ""; }, 5000);
            }
        });
    });

    // Heal Button
    const healBtn = document.getElementById("heal-btn");
    
    healBtn.addEventListener("click", () => {
        healBtn.disabled = true;
        zimovStatus.textContent = "Initiating Heal Sequence...";
        zimovStatus.className = "tp-status-msg tp-ok";

        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type: "kakeula_heal"})
        }).then(r => r.json()).then(data => {
            if (data.status === "error") {
                zimovStatus.textContent = data.message;
                zimovStatus.className = "tp-status-msg tp-error";
                healBtn.disabled = false;
            } else {
                zimovStatus.textContent = "Sequence Running...";
                setTimeout(() => { 
                    zimovStatus.textContent = ""; 
                    healBtn.disabled = false;
                }, 5000);
            }
        });
    });

    // Sell Button
    const sellBtn = document.getElementById("sell-btn");
    
    sellBtn.addEventListener("click", () => {
        sellBtn.disabled = true;
        zimovStatus.textContent = "Initiating Sell Sequence...";
        zimovStatus.className = "tp-status-msg tp-ok";

        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type: "kakeula_sell"})
        }).then(r => r.json()).then(data => {
            if (data.status === "error") {
                zimovStatus.textContent = data.message;
                zimovStatus.className = "tp-status-msg tp-error";
                sellBtn.disabled = false;
            } else {
                zimovStatus.textContent = "Sequence Running...";
                setTimeout(() => { 
                    zimovStatus.textContent = ""; 
                    sellBtn.disabled = false;
                }, 5000);
            }
        });
    });

    // Auto Zimov Button
    const autoZimovBtn = document.getElementById("auto-zimov-btn");

    autoZimovBtn.addEventListener("click", () => {
        if (autoZimovBtn.classList.contains("stop")) {
            sendAction({type: "stop_auto_zimov"});
        } else {
            sendAction({type: "start_auto_zimov"});
        }
    });

    // --- Renderers ---
    function updateControls(state) {
        modeBtns.forEach(btn => {
            if(btn.dataset.mode === state.mode) btn.classList.add("active");
            else btn.classList.remove("active");
        });

        if(state.paused) {
            pauseBtn.classList.add("active-pause");
            pauseBtn.textContent = "RESUME NAV";
        } else {
            pauseBtn.classList.remove("active-pause");
            pauseBtn.textContent = "PAUSE NAV";
        }

        // Only enable Zimov button if map is 3e1c (Dierolt)
        if (state.current_map_hex === "3e1c") {
            zimovBtn.disabled = false;
            if (!state.auto_zimov_running) autoZimovBtn.disabled = false;
        } else {
            zimovBtn.disabled = true;
            if (!state.auto_zimov_running) autoZimovBtn.disabled = true;
        }

        // Handle auto zimov loop state
        if (state.auto_zimov_running) {
            autoZimovBtn.classList.add("stop");
            autoZimovBtn.classList.add("warn");
            autoZimovBtn.textContent = "STOP AUTO ZIMOV";
            
            zimovBtn.disabled = true;
            healBtn.disabled = true;
            sellBtn.disabled = true;
        } else {
            autoZimovBtn.classList.remove("stop");
            autoZimovBtn.classList.remove("warn");
            autoZimovBtn.textContent = "AUTO ZIMOV LOOP";
            
            healBtn.disabled = false;
            sellBtn.disabled = false;
        }
    }

    function updateRadar(state) {
        const entries = Object.entries(state.monsters);
        if(entries.length === 0) {
            radarList.innerHTML = `<div class="radar-empty">Awaiting targets...</div>`;
            return;
        }

        // We re-render manually for MVP
        radarList.innerHTML = "";
        entries.forEach(([uid, m]) => {
            const name = (m.id <= 2) ? "Colon" : `Entity Model(${m.id})`;
            const row = document.createElement("div");
            row.className = "monster-row";
            if(uid === state.targetUid) row.classList.add("selected");
            
            row.innerHTML = `
                <div class="m-name">${name}</div>
                <div class="m-uid">${uid}</div>
            `;
            
            row.addEventListener("click", () => {
                sendAction({type: "set_target", uid: uid});
            });

            radarList.appendChild(row);
        });
    }

    function updateInventory(state) {
        const spinaEl = document.getElementById("spina-earned");
        if(spinaEl) spinaEl.textContent = state.spina_earned ? state.spina_earned.toLocaleString() : "0";

        const items = state.inventory;
        if(!items || Object.keys(items).length === 0) {
            inventoryList.innerHTML = `<div class="inv-empty">No items loaded...</div>`;
            return;
        }

        // Sort by count descending
        const sorted = Object.entries(items).sort((a, b) => b[1].count - a[1].count);

        inventoryList.innerHTML = "";
        sorted.forEach(([hex, item]) => {
            const row = document.createElement("div");
            row.className = "inv-row";
            row.innerHTML = `
                <div class="inv-info">
                    <span class="inv-name">${item.name}</span>
                    <span class="inv-id">${hex}</span>
                </div>
                <span class="inv-count">x${item.count}</span>
            `;
            inventoryList.appendChild(row);
        });
    }
});
