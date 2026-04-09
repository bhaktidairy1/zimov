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
    
    // Components
    const radarList = document.getElementById("radar-list");
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
});
