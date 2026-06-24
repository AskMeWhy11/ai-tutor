"use strict";

const STORAGE_KEY = "ai_tutor_session_id";

async function createSession({ employeeName, productId }) {
    const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            employee_name: employeeName,
            product_id: productId,
        }),
    });
    if (!res.ok) {
        throw new Error(`Не удалось создать сессию: ${res.status}`);
    }
    const data = await res.json();
    localStorage.setItem(STORAGE_KEY, data.session_id);
    // Прокидываем initial-effects в session-страницу.
    sessionStorage.setItem(`ai_tutor_initial_${data.session_id}`, JSON.stringify(data));
    return data.session_id;
}

async function checkSessionExists(sessionId) {
    try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        return res.ok;
    } catch {
        return false;
    }
}

async function initResume() {
    const savedId = localStorage.getItem(STORAGE_KEY);
    if (!savedId) {
        return;
    }
    const alive = await checkSessionExists(savedId);
    if (!alive) {
        localStorage.removeItem(STORAGE_KEY);
        return;
    }
    const block = document.getElementById("resume-block");
    block.hidden = false;

    document.getElementById("btn-resume").addEventListener("click", () => {
        window.location.href = `/session/${savedId}`;
    });
    document.getElementById("btn-forget").addEventListener("click", () => {
        localStorage.removeItem(STORAGE_KEY);
        block.hidden = true;
    });
}

function initStartForm() {
    const form = document.getElementById("start-form");
    const btn = document.getElementById("btn-start");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const data = new FormData(form);
        const employeeName = String(data.get("employee_name") || "").trim();
        const productId = String(data.get("product_id") || "cc_novichok");

        btn.disabled = true;
        btn.textContent = "Запускаю…";
        try {
            const id = await createSession({ employeeName, productId });
            window.location.href = `/session/${id}`;
        } catch (err) {
            console.error(err);
            alert(String(err));
            btn.disabled = false;
            btn.textContent = "Начать обучение";
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initResume();
    initStartForm();
});
