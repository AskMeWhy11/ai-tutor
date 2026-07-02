"use strict";

const STORAGE_KEY = "ai_tutor_session_id";

const DIALOG_STATES = new Set([
    "TRAINING",
    "TRAINING_QUIZ",
    "EXAMPLE",
    "PRACTICE",
    "KNOWLEDGE",
]);

const state = {
    sessionId: window.INITIAL_SESSION_ID || null,
    currentState: null,
    availableCommands: [],
    knowledgeUnlocked: false,
    debug: false,
    recording: false,
};

const els = {
    chatLog: document.getElementById("chat-log"),
    sessState: document.getElementById("sess-state"),
    sessId: document.getElementById("sess-id"),
    avatarStatus: document.getElementById("avatar-status"),
    avatar: document.getElementById("avatar"),
    avatarAudio: document.getElementById("avatar-audio"),
    composer: document.getElementById("command-form"),
    composerInput: document.getElementById("composer-input"),
    btnMic: document.getElementById("btn-mic"),
    btnNew: document.getElementById("btn-new"),
    btnDebug: document.getElementById("btn-debug"),
    btnHome: document.getElementById("btn-home"),
    quick: document.getElementById("quick-actions"),
    debug: document.getElementById("debug"),
    debugEffects: document.getElementById("debug-effects"),
    chatDock: document.getElementById("chat-dock"),
    chatDockDrag: document.getElementById("chat-dock-drag"),
    chatDockResize: document.getElementById("chat-dock-resize"),
    chatDockReset: document.getElementById("chat-dock-reset"),
};

// ---------- API ----------

async function apiGetSession(id) {
    const res = await fetch(`/api/sessions/${id}`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`GET /sessions/${id}: ${res.status}`);
    return res.json();
}

async function apiSendCommand(id, command) {
    const res = await fetch(`/api/sessions/${id}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`POST command: ${res.status} ${body}`);
    }
    return res.json();
}

// ---------- TTS controls ----------

// Привязка к конкретному пузырю: в момент play мы знаем, какой bubble «активен».
const ttsState = {
    activeBubble: null, // элемент .chat-msg--bot, чьё аудио сейчас играет/на паузе
    currentUrl: null,
};

function makeIconBtn(svgInner, opts = {}) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tts-btn";
    if (opts.title) btn.title = opts.title;
    if (opts.ariaLabel) btn.setAttribute("aria-label", opts.ariaLabel);
    btn.innerHTML = svgInner;
    return btn;
}

const ICON_PAUSE = `
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <rect x="6" y="5" width="4" height="14" rx="1"/>
  <rect x="14" y="5" width="4" height="14" rx="1"/>
</svg>`;

const ICON_PLAY = `
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <polygon points="6 4 20 12 6 20 6 4"/>
</svg>`;

const ICON_RESTART = `
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <polyline points="1 4 1 10 7 10"/>
  <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
</svg>`;

function setBubblePlayState(bubble, playing) {
    if (!bubble) return;
    const pauseBtn = bubble.querySelector(".tts-btn--pause");
    if (!pauseBtn) return;
    if (playing) {
        pauseBtn.innerHTML = ICON_PAUSE;
        pauseBtn.title = "Пауза";
        pauseBtn.setAttribute("aria-label", "Пауза");
        pauseBtn.setAttribute("aria-pressed", "false");
    } else {
        pauseBtn.innerHTML = ICON_PLAY;
        pauseBtn.title = "Продолжить";
        pauseBtn.setAttribute("aria-label", "Продолжить");
        pauseBtn.setAttribute("aria-pressed", "true");
    }
}

function attachTtsControlsToBubble(bubble, audioUrl) {
    if (!bubble || !audioUrl) return;
    const controls = document.createElement("div");
    controls.className = "tts-controls";

    const pauseBtn = makeIconBtn(ICON_PAUSE, {
        title: "Пауза",
        ariaLabel: "Пауза озвучки",
    });
    pauseBtn.classList.add("tts-btn--pause");

    const restartBtn = makeIconBtn(ICON_RESTART, {
        title: "Перезапустить озвучку",
        ariaLabel: "Перезапустить озвучку",
    });
    restartBtn.classList.add("tts-btn--restart");

    pauseBtn.addEventListener("click", () => {
        const audio = els.avatarAudio;
        const isActive = ttsState.activeBubble === bubble && audio.src && audio.src.endsWith(audioUrl);
        if (!isActive) {
            // не наш — стартуем заново на этом пузыре
            playAudioOnBubble(bubble, audioUrl);
            return;
        }
        if (audio.paused) {
            audio.play().catch((err) => console.warn("audio resume failed:", err));
        } else {
            audio.pause();
        }
    });

    restartBtn.addEventListener("click", () => {
        playAudioOnBubble(bubble, audioUrl, /*forceRestart=*/true);
    });

    controls.appendChild(pauseBtn);
    controls.appendChild(restartBtn);
    bubble.appendChild(controls);
    bubble.dataset.ttsUrl = audioUrl;
}

function playAudioOnBubble(bubble, url, forceRestart = false) {
    const audio = els.avatarAudio;
    // снимаем индикатор со старого пузыря
    if (ttsState.activeBubble && ttsState.activeBubble !== bubble) {
        ttsState.activeBubble.classList.remove("is-playing", "is-paused");
        setBubblePlayState(ttsState.activeBubble, true);
    }
    ttsState.activeBubble = bubble;
    ttsState.currentUrl = url;

    if (forceRestart || !audio.src || !audio.src.endsWith(url)) {
        audio.src = url;
    } else {
        audio.currentTime = 0;
    }
    setAvatarSpeaking(true);
    bubble.classList.add("is-playing");
    bubble.classList.remove("is-paused");
    setBubblePlayState(bubble, true);
    audio.play().catch((err) => {
        console.warn("audio play failed:", err);
        setAvatarSpeaking(false);
        bubble.classList.remove("is-playing", "is-paused");
    });
}

function bindAudioEvents() {
    const audio = els.avatarAudio;
    audio.addEventListener("play", () => {
        if (!ttsState.activeBubble) return;
        ttsState.activeBubble.classList.add("is-playing");
        ttsState.activeBubble.classList.remove("is-paused");
        setBubblePlayState(ttsState.activeBubble, true);
        setAvatarSpeaking(true);
    });
    audio.addEventListener("pause", () => {
        if (!ttsState.activeBubble) return;
        if (audio.ended) return;
        ttsState.activeBubble.classList.add("is-paused");
        ttsState.activeBubble.classList.remove("is-playing");
        setBubblePlayState(ttsState.activeBubble, false);
        setAvatarSpeaking(false);
    });
    audio.addEventListener("ended", () => {
        if (ttsState.activeBubble) {
            ttsState.activeBubble.classList.remove("is-playing", "is-paused");
            setBubblePlayState(ttsState.activeBubble, true);
        }
        setAvatarSpeaking(false);
    });
}

// ---------- UI helpers ----------

function appendBubble(role, text) {
    const li = document.createElement("li");
    const map = { ai: "bot", user: "user", hint: "system" };
    const kind = map[role] || "system";
    li.className = `chat-msg chat-msg--${kind}`;
    const body = document.createElement("div");
    body.className = "chat-msg__text";
    body.textContent = text;
    li.appendChild(body);
    els.chatLog.appendChild(li);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
    return li;
}

function renderHistory(history) {
    if (!Array.isArray(history) || history.length === 0) return;
    for (const msg of history) {
        if (!msg || !msg.text) continue;
        if (msg.role === "user") {
            appendBubble("user", msg.text);
        } else if (msg.role === "assistant") {
            appendBubble("ai", msg.text);
        }
    }
}

function setAvatarSpeaking(flag) {
    els.avatar.dataset.speaking = flag ? "true" : "false";
    if (els.avatarStatus) {
        els.avatarStatus.textContent = flag ? "говорит" : "ожидает";
    }
}

function findLastAiBubble() {
    const items = els.chatLog.querySelectorAll(".chat-msg--bot");
    return items.length ? items[items.length - 1] : null;
}

function playAudioIfAny(effects) {
    const audio = effects.find((e) => e.type === "play_audio" && e.url);
    if (!audio) return;
    const bubble = findLastAiBubble();
    if (!bubble) return;
    attachTtsControlsToBubble(bubble, audio.url);
    playAudioOnBubble(bubble, audio.url);
}

function renderEffectsToChat(effects) {
    for (const eff of effects) {
        if (eff.type === "emit_text" && eff.text) {
            appendBubble("ai", eff.text);
        } else if (eff.type === "emit_hint" && eff.text) {
            appendBubble("hint", `📌 ${eff.text}`);
        } else if (eff.type === "emit_message" && eff.key) {
            appendBubble("ai", `[${eff.key}]`);
        }
    }
}

function isDialogState() {
    return DIALOG_STATES.has(state.currentState);
}

// ---------- Команда «по умолчанию» (для не-диалоговых состояний) ----------

function buildSuccessPayload(availableCmd) {
    const payload = { type: availableCmd.type };
    const hint = availableCmd.schema_hint || {};

    for (const [field] of Object.entries(hint)) {
        switch (field) {
            case "correct":
            case "accept":
            case "resume":
                payload[field] = true;
                break;
            case "weak_zones":
                payload[field] = [];
                break;
            case "mode":
                payload[field] = "training";
                break;
            case "employee_name":
            case "product_id":
                break;
            default:
                break;
        }
    }
    return payload;
}

function pickPrimaryCommand() {
    const nonDialog = state.availableCommands.filter((c) => c.type !== "user_message");
    if (nonDialog.length === 0) return null;
    const priority = [
        "continue",
        "theory_done",
        "scenario_done",
        "dialog_done",
        "zones_done",
        "repeat_cycle",
        "explanation_done",
        "weak_zones_sent",
        "start_training",
    ];
    for (const t of priority) {
        const found = nonDialog.find((c) => c.type === t);
        if (found) return found;
    }
    return nonDialog[0];
}

// ---------- Ввод сотрудника ----------

async function sendUserMessage(text) {
    const trimmed = (text || "").trim();
    if (!trimmed) return;

    if (isDialogState()) {
        appendBubble("user", trimmed);
        await sendCommand({ type: "user_message", text: trimmed });
        return;
    }

    appendBubble("user", trimmed);
    const primary = pickPrimaryCommand();
    if (!primary) return;
    const payload = buildSuccessPayload(primary);
    await sendCommand(payload);
}

async function sendCommand(payload) {
    if (!state.sessionId) return;
    try {
        const data = await apiSendCommand(state.sessionId, payload);
        applyServerState(data);
    } catch (err) {
        console.error(err);
        appendBubble("hint", `⚠️ Ошибка: ${err.message}`);
    }
}

// ---------- Применение state с сервера ----------

function applyServerState(data) {
    state.currentState = data.state;
    state.availableCommands = data.available_commands || [];
    state.knowledgeUnlocked = !!(data.ctx && data.ctx.knowledge_unlocked);

    els.sessState.textContent = data.state;
    els.sessId.textContent = state.sessionId || "—";

    renderEffectsToChat(data.effects || []);
    playAudioIfAny(data.effects || []);
    renderQuickActions();
    updateComposerPlaceholder();

    if (state.debug) {
        els.debugEffects.textContent = JSON.stringify(data.effects, null, 2);
    }
}

function updateComposerPlaceholder() {
    if (state.currentState === "TRAINING_QUIZ") {
        els.composerInput.placeholder = "Введи ответ на вопрос…";
        return;
    }
    if (isDialogState()) {
        els.composerInput.placeholder = "Напиши реплику или нажми микрофон…";
        return;
    }
    const primary = pickPrimaryCommand();
    els.composerInput.placeholder = primary
        ? `Enter — «${primary.label}»`
        : "Нет доступных команд";
}

function renderQuickActions() {
    els.quick.innerHTML = "";
    const cmds = state.availableCommands.filter((c) => c.type !== "user_message");
    for (const cmd of cmds) {
        if (cmd.type === "submit_quiz_answer") {
            if (!state.debug) continue;
            els.quick.appendChild(makeBtn("[debug] Ответил верно", () =>
                sendCommand({ type: "submit_quiz_answer", correct: true }),
            ));
            els.quick.appendChild(makeBtn("[debug] Ошибся", () =>
                sendCommand({ type: "submit_quiz_answer", correct: false }),
            ));
            continue;
        }
        if (cmd.type === "practice_evaluated") {
            if (!state.debug) continue;
            els.quick.appendChild(makeBtn("[debug] Зоны: все ок", () =>
                sendCommand({ type: "practice_evaluated", weak_zones: [] }),
            ));
            els.quick.appendChild(makeBtn("[debug] Зоны: needs+pitch", () =>
                sendCommand({
                    type: "practice_evaluated",
                    weak_zones: ["needs", "pitch"],
                }),
            ));
            continue;
        }
        if (cmd.type === "confirm_skip_warning") {
            els.quick.appendChild(makeBtn("Да, пропустить", () =>
                sendCommand({ type: "confirm_skip_warning", accept: true }),
            ));
            els.quick.appendChild(makeBtn("Нет, вернуться", () =>
                sendCommand({ type: "confirm_skip_warning", accept: false }),
            ));
            continue;
        }
        if (cmd.type === "resume_choice") {
            els.quick.appendChild(makeBtn("Продолжить", () =>
                sendCommand({ type: "resume_choice", resume: true }),
            ));
            els.quick.appendChild(makeBtn("Начать заново", () =>
                sendCommand({ type: "resume_choice", resume: false }),
            ));
            continue;
        }
        if (cmd.type === "select_mode") {
            els.quick.appendChild(makeBtn("Обучение", () =>
                sendCommand({ type: "select_mode", mode: "training" }),
                        ));
            els.quick.appendChild(makeBtn("Пример", () =>
                sendCommand({ type: "select_mode", mode: "example" }),
            ));
            els.quick.appendChild(makeBtn("Практика", () =>
                sendCommand({ type: "select_mode", mode: "practice" }),
            ));
            const knowBtn = makeBtn("Знания", () =>
                sendCommand({ type: "select_mode", mode: "knowledge" }),
            );
            if (!state.knowledgeUnlocked) {
                knowBtn.disabled = true;
                knowBtn.classList.add("btn--locked");
                knowBtn.title = "Открывается после неуспешной практики";
            }
            els.quick.appendChild(knowBtn);
            continue;
        }
        els.quick.appendChild(makeBtn(cmd.label, () => {
            const payload = buildSuccessPayload(cmd);
            sendCommand(payload);
        }));
    }
}

function makeBtn(label, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn btn-sm";
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
}

// ---------- Микрофон (запись PCM 16k → /api/stt) ----------

const sttRec = {
    stream: null,
    audioCtx: null,
    source: null,
    processor: null,
    chunks: [],       // Float32Array блоки
    sampleRate: 16000,
    busy: false,
};

function floatTo16BitPCM(input) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
}

function encodeWav(samples, sampleRate) {
    const pcm = floatTo16BitPCM(samples);
    const buffer = new ArrayBuffer(44 + pcm.length * 2);
    const view = new DataView(buffer);
    const writeStr = (off, str) => {
        for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i));
    };
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + pcm.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);       // PCM
    view.setUint16(22, 1, true);       // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);       // block align
    view.setUint16(34, 16, true);      // bits
    writeStr(36, "data");
    view.setUint32(40, pcm.length * 2, true);
    let off = 44;
    for (let i = 0; i < pcm.length; i++, off += 2) view.setInt16(off, pcm[i], true);
    return new Blob([view], { type: "audio/wav" });
}

// Down-mix + resample к 16k (линейная интерполяция).
function resampleTo16k(float32, fromRate) {
    const target = 16000;
    if (fromRate === target) return float32;
    const ratio = fromRate / target;
    const newLen = Math.round(float32.length / ratio);
    const out = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
        const pos = i * ratio;
        const idx = Math.floor(pos);
        const frac = pos - idx;
        const a = float32[idx] || 0;
        const b = float32[idx + 1] || a;
        out[i] = a + (b - a) * frac;
    }
    return out;
}

function concatFloat32(chunks) {
    let len = 0;
    for (const c of chunks) len += c.length;
    const out = new Float32Array(len);
    let off = 0;
    for (const c of chunks) { out.set(c, off); off += c.length; }
    return out;
}

async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const audioCtx = new AudioCtx();
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    sttRec.stream = stream;
    sttRec.audioCtx = audioCtx;
    sttRec.source = source;
    sttRec.processor = processor;
    sttRec.chunks = [];
    sttRec.sampleRate = audioCtx.sampleRate;

    processor.onaudioprocess = (e) => {
        const ch = e.inputBuffer.getChannelData(0);
        sttRec.chunks.push(new Float32Array(ch));
    };
    source.connect(processor);
    processor.connect(audioCtx.destination);
}

async function stopRecordingAndSend() {
    const { processor, source, audioCtx, stream, chunks, sampleRate } = sttRec;
    try {
        processor && processor.disconnect();
        source && source.disconnect();
    } catch (_) { /* ignore */ }
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (audioCtx && audioCtx.state !== "closed") { try { await audioCtx.close(); } catch (_) {} }

    sttRec.processor = sttRec.source = sttRec.audioCtx = sttRec.stream = null;

    const merged = concatFloat32(chunks);
    sttRec.chunks = [];
    if (!merged.length) return;

    const pcm16k = resampleTo16k(merged, sampleRate);
    const wav = encodeWav(pcm16k, 16000);

    const fd = new FormData();
    fd.append("audio", wav, "speech.wav");

    els.btnMic.classList.add("is-busy");
    try {
        const res = await fetch("/api/stt", { method: "POST", body: fd });
        if (!res.ok) {
            const body = await res.text();
            throw new Error(`STT ${res.status}: ${body}`);
        }
        const data = await res.json();
        const text = (data.text || "").trim();
        if (text) {
            els.composerInput.value = text;
            sendUserMessage(text);
            els.composerInput.value = "";
        } else {
            appendBubble("hint", "🎤 Речь не распознана, попробуйте ещё раз.");
        }
    } catch (err) {
        console.error(err);
        appendBubble("hint", `⚠️ Ошибка распознавания: ${err.message}`);
    } finally {
        els.btnMic.classList.remove("is-busy");
    }
}

function setupSpeechRecognition() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        els.btnMic.disabled = true;
        els.btnMic.title = "Микрофон не поддерживается этим браузером";
        return;
    }

    els.btnMic.addEventListener("click", async () => {
        if (sttRec.busy) return;

        if (state.recording) {
            // остановка
            state.recording = false;
            els.btnMic.setAttribute("aria-pressed", "false");
            els.btnMic.classList.remove("is-recording");
            sttRec.busy = true;
            try {
                await stopRecordingAndSend();
            } finally {
                sttRec.busy = false;
            }
            return;
        }

        // старт
        try {
            await startRecording();
            state.recording = true;
            els.btnMic.setAttribute("aria-pressed", "true");
            els.btnMic.classList.add("is-recording");
        } catch (err) {
            console.warn("mic start failed:", err);
            appendBubble("hint", "⚠️ Не удалось получить доступ к микрофону.");
        }
    });
}
// ---------- Chat dock: drag + resize + persist ----------

const DOCK_STORAGE_KEY = "ai_tutor_chat_dock_rect";
const SIDEBAR_W = 64;

function clampRect(rect) {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const minW = 320;
    const minH = 320;
    const margin = 8;

    const maxW = Math.max(minW, vw - SIDEBAR_W - margin * 2);
    const maxH = Math.max(minH, vh - margin * 2);

    let { left, top, width, height } = rect;
    width = Math.min(Math.max(width, minW), maxW);
    height = Math.min(Math.max(height, minH), maxH);

    const minLeft = SIDEBAR_W + margin;
    const maxLeft = vw - width - margin;
    const minTop = margin;
    const maxTop = vh - height - margin;

    left = Math.min(Math.max(left, minLeft), Math.max(minLeft, maxLeft));
    top  = Math.min(Math.max(top,  minTop),  Math.max(minTop,  maxTop));

    return { left, top, width, height };
}

function applyDockRect(rect) {
    const r = clampRect(rect);
    const el = els.chatDock;
    el.style.left = r.left + "px";
    el.style.top = r.top + "px";
    el.style.right = "auto";
    el.style.bottom = "auto";
    el.style.width = r.width + "px";
    el.style.height = r.height + "px";
    return r;
}

function saveDockRect(rect) {
    try {
        localStorage.setItem(DOCK_STORAGE_KEY, JSON.stringify(rect));
    } catch (_) { /* ignore */ }
}

function loadDockRect() {
    try {
        const raw = localStorage.getItem(DOCK_STORAGE_KEY);
        if (!raw) return null;
        const obj = JSON.parse(raw);
        if (!obj || typeof obj.left !== "number") return null;
        return obj;
    } catch (_) { return null; }
}

function defaultDockRect() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = Math.min(640, Math.max(360, vw - SIDEBAR_W - 80));
    const height = Math.min(720, Math.max(360, vh - 140));
    const left = Math.round((vw - width) / 2);
    const top = Math.round((vh - height) / 2);
    return { left, top, width, height };
}

function setupChatDock() {
    const dock = els.chatDock;
    if (!dock) return;

    // На мобильной ширине — оставляем CSS-поведение (фикс снизу), JS не вмешивается.
    const mq = window.matchMedia("(max-width: 720px)");
    let mobileMode = mq.matches;

    function initialPlace() {
        if (mobileMode) {
            // сброс инлайн-стилей, пусть работает CSS
            dock.style.left = dock.style.top = dock.style.width = dock.style.height = "";
            dock.style.right = dock.style.bottom = "";
            return;
        }
        const saved = loadDockRect();
        const rect = saved || defaultDockRect();
        applyDockRect(rect);
    }

    initialPlace();

    mq.addEventListener?.("change", (e) => {
        mobileMode = e.matches;
        initialPlace();
    });

    window.addEventListener("resize", () => {
        if (mobileMode) return;
        const r = dock.getBoundingClientRect();
        applyDockRect({
            left: r.left, top: r.top, width: r.width, height: r.height,
        });
    });

    // ---- DRAG ----
    let dragStart = null;
    function onDragPointerDown(e) {
        if (mobileMode) return;
        // не начинать драг, если кликнули по кнопке reset
        if (e.target.closest("#chat-dock-reset")) return;
        const r = dock.getBoundingClientRect();
        dragStart = {
            x: e.clientX,
            y: e.clientY,
            left: r.left,
            top: r.top,
            width: r.width,
            height: r.height,
        };
        dock.classList.add("is-dragging");
        els.chatDockDrag.setPointerCapture?.(e.pointerId);
        e.preventDefault();
    }
    function onDragPointerMove(e) {
        if (!dragStart) return;
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        applyDockRect({
            left: dragStart.left + dx,
            top:  dragStart.top  + dy,
            width: dragStart.width,
            height: dragStart.height,
        });
    }
    function onDragPointerUp(e) {
        if (!dragStart) return;
        dragStart = null;
        dock.classList.remove("is-dragging");
        els.chatDockDrag.releasePointerCapture?.(e.pointerId);
        const r = dock.getBoundingClientRect();
        saveDockRect({ left: r.left, top: r.top, width: r.width, height: r.height });
    }

    els.chatDockDrag.addEventListener("pointerdown", onDragPointerDown);
    els.chatDockDrag.addEventListener("pointermove", onDragPointerMove);
    els.chatDockDrag.addEventListener("pointerup", onDragPointerUp);
    els.chatDockDrag.addEventListener("pointercancel", onDragPointerUp);

    // ---- RESIZE ----
    let resizeStart = null;
    function onResizePointerDown(e) {
        if (mobileMode) return;
        const r = dock.getBoundingClientRect();
        resizeStart = {
            x: e.clientX,
            y: e.clientY,
            left: r.left,
            top: r.top,
            width: r.width,
            height: r.height,
        };
        dock.classList.add("is-resizing");
        els.chatDockResize.setPointerCapture?.(e.pointerId);
        e.preventDefault();
        e.stopPropagation();
    }
    function onResizePointerMove(e) {
        if (!resizeStart) return;
        const dx = e.clientX - resizeStart.x;
        const dy = e.clientY - resizeStart.y;
        applyDockRect({
            left: resizeStart.left,
            top: resizeStart.top,
            width: resizeStart.width + dx,
            height: resizeStart.height + dy,
        });
    }
    function onResizePointerUp(e) {
        if (!resizeStart) return;
        resizeStart = null;
        dock.classList.remove("is-resizing");
        els.chatDockResize.releasePointerCapture?.(e.pointerId);
        const r = dock.getBoundingClientRect();
        saveDockRect({ left: r.left, top: r.top, width: r.width, height: r.height });
    }

    els.chatDockResize.addEventListener("pointerdown", onResizePointerDown);
    els.chatDockResize.addEventListener("pointermove", onResizePointerMove);
    els.chatDockResize.addEventListener("pointerup", onResizePointerUp);
    els.chatDockResize.addEventListener("pointercancel", onResizePointerUp);

    // ---- RESET ----
    els.chatDockReset?.addEventListener("click", () => {
        try { localStorage.removeItem(DOCK_STORAGE_KEY); } catch (_) {}
        if (!mobileMode) {
            applyDockRect(defaultDockRect());
        }
    });
}

// ---------- Init / lifecycle ----------

async function initSession() {
    let sid = state.sessionId || localStorage.getItem(STORAGE_KEY);
    if (sid) {
        const data = await apiGetSession(sid);
        if (data) {
            state.sessionId = sid;
            localStorage.setItem(STORAGE_KEY, sid);
            renderHistory(data.history || []);
            applyServerState(data);
            return;
        }
    }
    appendBubble("hint", "Сессия не найдена. Вернитесь на главную и начните заново.");
    setTimeout(() => { window.location.href = "/"; }, 1500);
}

function wireEvents() {
    els.composer.addEventListener("submit", (e) => {
        e.preventDefault();
        const val = els.composerInput.value.trim();
        if (!val) return;
        sendUserMessage(val);
        els.composerInput.value = "";
    });

    els.btnNew.addEventListener("click", () => {
        localStorage.removeItem(STORAGE_KEY);
        window.location.href = "/";
    });

    els.btnDebug.addEventListener("click", () => {
        state.debug = !state.debug;
        els.btnDebug.setAttribute("aria-pressed", state.debug ? "true" : "false");
        els.debug.hidden = !state.debug;
        renderQuickActions();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindAudioEvents();
    wireEvents();
    setupSpeechRecognition();
    setupChatDock();
    initSession();
});
