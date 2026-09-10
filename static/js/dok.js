const chatList = document.getElementById("chat-list");
const chatListEmpty = document.getElementById("chat-list-empty");
const messagesEl = document.getElementById("messages");
const emptyChatMsg = document.getElementById("empty-chat-msg");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const menuToggle = document.getElementById("menu-toggle");
const chatDrawer = document.getElementById("chat-drawer");
const drawerOverlay = document.getElementById("drawer-overlay");
const tabBtns = document.querySelectorAll(".tab-btn");
const panelChats = document.getElementById("panel-chats");
const panelProjetos = document.getElementById("panel-projetos");

let currentChatId = null;

// --- Abas Chats / Projetos ---
tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
        tabBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const tab = btn.dataset.tab;
        panelChats.hidden = tab !== "chats";
        panelProjetos.hidden = tab !== "projetos";
        if (tab === "projetos") loadProjectsHistory();
    });
});

// --- Drawer responsivo (telas pequenas) ---
function openDrawer() {
    chatDrawer.classList.add("open");
    drawerOverlay.classList.add("show");
}
function closeDrawer() {
    chatDrawer.classList.remove("open");
    drawerOverlay.classList.remove("show");
}
menuToggle.addEventListener("click", () => {
    chatDrawer.classList.contains("open") ? closeDrawer() : openDrawer();
});
drawerOverlay.addEventListener("click", closeDrawer);

// --- Lista de conversas ---
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

// --- Selecionar / abrir uma conversa ---
async function selectChat(chatId) {
    currentChatId = chatId;
    closeDrawer();

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

function renderMessages(messages) {
    messagesEl.querySelectorAll(".msg-bubble").forEach((el) => el.remove());

    if (!messages || messages.length === 0) {
        emptyChatMsg.hidden = false;
        return;
    }
    emptyChatMsg.hidden = true;

    messages.forEach((m) => appendBubble(m.role, m.content));
    scrollToBottom();
}

function appendBubble(role, content, pending = false) {
    emptyChatMsg.hidden = true;
    const bubble = document.createElement("div");
    bubble.className = `msg-bubble ${role}` + (pending ? " pending" : "");
    bubble.textContent = content;
    messagesEl.appendChild(bubble);
    scrollToBottom();
    return bubble;
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Nova conversa ---
newChatBtn.addEventListener("click", async () => {
    try {
        const res = await fetch("/api/chats", { method: "POST" });
        const data = await res.json();
        if (data.ok) {
            currentChatId = data.id;
            renderMessages([]);
            loadChatList();
            messageInput.focus();
        }
    } catch (err) {
        console.error("Falha ao criar conversa", err);
    }
});

// --- Auto-resize da caixa de texto ---
messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
});

// --- Enviar mensagem ---
composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    await sendCurrentMessage();
});

// Enter envia, Shift+Enter quebra linha
messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendCurrentMessage();
    }
});

async function sendCurrentMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    // Se não tem conversa selecionada, cria uma primeiro
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

    // Limpa a caixa de texto IMEDIATAMENTE — antes mesmo da resposta chegar,
    // pra nunca deixar string presa nela.
    messageInput.value = "";
    messageInput.style.height = "auto";

    sendBtn.disabled = true;
    messageInput.disabled = true;

    appendBubble("user", text);
    const pendingBubble = appendBubble("assistant", "…", true);

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

// --- Inicialização ---
loadChatList();

// ============================================================
// Aba Projetos — diagnóstico com ferramentas reais (MCP)
// ============================================================
const projectsMessages = document.getElementById("projects-messages");
const emptyProjectsMsg = document.getElementById("empty-projects-msg");
const projectsComposer = document.getElementById("projects-composer");
const projectsInput = document.getElementById("projects-input");
const projectsSendBtn = document.getElementById("projects-send-btn");

function appendProjectBubble(role, content, pending = false) {
    emptyProjectsMsg.hidden = true;
    const bubble = document.createElement("div");
    bubble.className = `msg-bubble ${role}` + (pending ? " pending" : "");
    bubble.textContent = content;
    projectsMessages.appendChild(bubble);
    projectsMessages.scrollTop = projectsMessages.scrollHeight;
    return bubble;
}

async function loadProjectsHistory() {
    try {
        const res = await fetch("/api/projects/history");
        const messages = await res.json();

        projectsMessages.querySelectorAll(".msg-bubble").forEach((el) => el.remove());

        if (!messages || messages.length === 0) {
            emptyProjectsMsg.hidden = false;
            return;
        }
        emptyProjectsMsg.hidden = true;
        messages.forEach((m) => appendProjectBubble(m.role, m.content));
    } catch (err) {
        console.error("Falha ao carregar histórico de projetos", err);
    }
}

projectsInput.addEventListener("input", () => {
    projectsInput.style.height = "auto";
    projectsInput.style.height = Math.min(projectsInput.scrollHeight, 160) + "px";
});

projectsComposer.addEventListener("submit", async (e) => {
    e.preventDefault();
    await sendProjectMessage();
});

projectsInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendProjectMessage();
    }
});

async function sendProjectMessage() {
    const text = projectsInput.value.trim();
    if (!text) return;

    // limpa a caixa ANTES de esperar resposta — mesma regra da aba Chats
    projectsInput.value = "";
    projectsInput.style.height = "auto";

    projectsSendBtn.disabled = true;
    projectsInput.disabled = true;

    appendProjectBubble("user", text);
    const pendingBubble = appendProjectBubble(
        "assistant", "Verificando… (pode levar alguns segundos)", true
    );

    try {
        const res = await fetch("/api/projects/message", {
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
        projectsSendBtn.disabled = false;
        projectsInput.disabled = false;
        projectsInput.focus();
    }
}
