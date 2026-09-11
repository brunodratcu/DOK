// ============================================================
// Sidebar de conversas (sempre visível no desktop; deslizante
// em telas pequenas, via sidebar-toggle)
// ============================================================
const sidebarToggle = document.getElementById("sidebar-toggle");
const chatSidebar = document.getElementById("chat-sidebar");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const chatList = document.getElementById("chat-list");
const chatListEmpty = document.getElementById("chat-list-empty");
const newChatBtn = document.getElementById("new-chat-btn");

let currentChatId = null;

function openSidebar() {
    chatSidebar.classList.add("open");
    sidebarOverlay.classList.add("show");
}
function closeSidebar() {
    chatSidebar.classList.remove("open");
    sidebarOverlay.classList.remove("show");
}
sidebarToggle.addEventListener("click", () => {
    chatSidebar.classList.contains("open") ? closeSidebar() : openSidebar();
});
sidebarOverlay.addEventListener("click", closeSidebar);

async function loadChatList() {
    try {
        const res = await fetch("/api/chats");
        const chats = await res.json();

        chatList.querySelectorAll(".chat-list-item").forEach((el) => el.remove());

        if (chats.length === 0) {
            chatListEmpty.hidden = false;
            return;
        }
        chatListEmpty.hidden = true;

        chats.forEach((chat) => {
            const item = document.createElement("div");
            item.className = "chat-list-item" + (chat.id === currentChatId ? " active" : "");
            item.innerHTML = `
                <span class="title">${escapeHtml(chat.title)}</span>
                <span class="preview">${escapeHtml(chat.preview)}</span>
            `;
            item.addEventListener("click", () => selectChat(chat.id));
            chatList.appendChild(item);
        });
    } catch (err) {
        console.error("Falha ao carregar conversas", err);
    }
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
}

async function selectChat(chatId) {
    currentChatId = chatId;
    closeSidebar();
    try {
        const res = await fetch(`/api/chats/${chatId}`);
        const data = await res.json();
        if (!data.ok) return;
        renderMessages(data.chat.messages);
        loadChatList(); // re-renderiza pra marcar o item ativo
    } catch (err) {
        console.error("Falha ao abrir conversa", err);
    }
}

newChatBtn.addEventListener("click", async () => {
    try {
        const res = await fetch("/api/chats", { method: "POST" });
        const data = await res.json();
        if (data.ok) {
            currentChatId = data.id;
            renderMessages([]);
            loadChatList();
            closeSidebar();
            messageInput.focus();
        }
    } catch (err) {
        console.error("Falha ao criar conversa", err);
    }
});

// ============================================================
// Conversa ativa
// ============================================================
const messagesEl = document.getElementById("messages");
const emptyChatMsg = document.getElementById("empty-chat-msg");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");

function appendBubble(role, content, pending = false) {
    emptyChatMsg.hidden = true;
    const bubble = document.createElement("div");
    bubble.className = `msg-bubble ${role}` + (pending ? " pending" : "");
    bubble.textContent = content;
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
}

function renderMessages(messages) {
    messagesEl.querySelectorAll(".msg-bubble").forEach((el) => el.remove());
    if (!messages || messages.length === 0) {
        emptyChatMsg.hidden = false;
        return;
    }
    emptyChatMsg.hidden = true;
    messages.forEach((m) => appendBubble(m.role, m.content));
}

messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
});

composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    await sendMessage();
});

messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    if (!currentChatId) {
        try {
            const res = await fetch("/api/chats", { method: "POST" });
            const data = await res.json();
            if (!data.ok) return;
            currentChatId = data.id;
        } catch (err) {
            console.error("Falha ao criar conversa", err);
            return;
        }
    }

    // limpa a caixa ANTES de esperar resposta — nunca deixa string presa
    messageInput.value = "";
    messageInput.style.height = "auto";
    sendBtn.disabled = true;
    messageInput.disabled = true;

    appendBubble("user", text);
    const pendingBubble = appendBubble("assistant", "Verificando…", true);

    try {
        const res = await fetch(`/api/chats/${currentChatId}/message`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text }),
        });
        const data = await res.json();
        pendingBubble.classList.remove("pending");
        pendingBubble.textContent = data.reply || "Não consegui responder agora.";
    } catch (err) {
        pendingBubble.classList.remove("pending");
        pendingBubble.textContent = "Falha de conexão. Tenta de novo.";
    } finally {
        sendBtn.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
        loadChatList(); // atualiza título/preview na lista
    }
}

// ============================================================
// Botão + : anexar pasta ou arquivos (seletor nativo do SO)
// ============================================================
const attachToggleBtn = document.getElementById("attach-toggle-btn");
const attachMenu = document.getElementById("attach-menu");
const attachFolderBtn = document.getElementById("attach-folder-btn");
const attachFilesBtn = document.getElementById("attach-files-btn");

attachToggleBtn.addEventListener("click", () => {
    attachMenu.hidden = !attachMenu.hidden;
});

function hasNativePicker() {
    return typeof window.pywebview !== "undefined" && window.pywebview.api;
}

attachFolderBtn.addEventListener("click", async () => {
    attachMenu.hidden = true;
    if (!hasNativePicker()) {
        alert("Selecionar pasta só funciona no app instalado (não no modo navegador de desenvolvimento).");
        return;
    }
    try {
        const path = await window.pywebview.api.pick_folder();
        if (path) insertAttachedPath(path);
    } catch (err) {
        console.error("Falha ao escolher pasta", err);
    }
});

attachFilesBtn.addEventListener("click", async () => {
    attachMenu.hidden = true;
    if (!hasNativePicker()) {
        alert("Selecionar arquivos só funciona no app instalado (não no modo navegador de desenvolvimento).");
        return;
    }
    try {
        const paths = await window.pywebview.api.pick_files();
        if (paths && paths.length) insertAttachedPath(paths.join(", "));
    } catch (err) {
        console.error("Falha ao escolher arquivos", err);
    }
});

function insertAttachedPath(path) {
    const current = messageInput.value.trim();
    messageInput.value = current ? `${current}\n${path}` : path;
    messageInput.dispatchEvent(new Event("input"));
    messageInput.focus();
}

// --- Inicialização ---
loadChatList();
