// ========================================================================
//  Chat UI — Frontend Logic (with Shared Memory)
// ========================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// --- State ---
let models = {};
let currentProvider = "openai";
let currentModel = "gpt-4o";
let conversations = JSON.parse(localStorage.getItem("chat-conversations") || "[]");
let activeConvoId = null;
let currentParams = {};
let isStreaming = false;
let abortController = null;
let lastAssistantMessage = "";
let contextPanelOpen = false;
let socraticMode = false;
let socraticParticipants = [];
let validProviders = {};  // { openai: true, anthropic: false, ... }

let codeMode = false;
let codeApiMessages = [];  // Full Anthropic-format messages for multi-turn code sessions

const PERSONA_COLORS = ["p0", "p1", "p2", "p3"];

// --- Provider icons ---
const PROVIDER_ICONS = {
    openai: "O",
    anthropic: "A",
    google: "G",
    grok: "X",
};

const PROVIDER_NAMES = {
    openai: "OpenAI",
    anthropic: "Anthropic",
    google: "Google",
    grok: "xAI (Grok)",
};

// --- Presets ---
const PRESETS = {
    creative: { temperature: 1.5, top_p: 0.95 },
    precise: { temperature: 0.2, top_p: 0.1 },
    balanced: { temperature: 0.7, top_p: 0.9 },
    deterministic: { temperature: 0, top_p: 1.0 },
};

// ========================================================================
//  INIT
// ========================================================================

async function init() {
    const res = await fetch("/api/models");
    models = await res.json();

    const carriersRes = await fetch("/api/carriers");
    const carriers = await carriersRes.json();

    populateProviders();
    populateCarriers(carriers);
    loadConversations();
    bindEvents();
    await initSocratic();
    await validateApiKeys();

    if (!activeConvoId) newChat();
}

function populateProviders() {
    const sel = $("#provider-select");
    sel.innerHTML = "";
    for (const [key, val] of Object.entries(models)) {
        const opt = document.createElement("option");
        opt.value = key;
        opt.textContent = val.name;
        sel.appendChild(opt);
    }
    sel.value = currentProvider;
    populateModels();
}

function populateModels() {
    const sel = $("#model-select");
    sel.innerHTML = "";
    const providerData = models[currentProvider];
    if (!providerData) return;

    for (const m of providerData.models) {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.name;
        sel.appendChild(opt);
    }
    sel.value = currentModel;
    buildParamControls();
    updateHeader();
    updateContextMeter();
}

function populateCarriers(carriers) {
    const sel = $("#sms-carrier");
    sel.innerHTML = "";
    for (const [key, name] of Object.entries(carriers)) {
        const opt = document.createElement("option");
        opt.value = key;
        opt.textContent = name;
        sel.appendChild(opt);
    }
    sel.value = "verizon";
}

// ========================================================================
//  CONTEXT HELPERS
// ========================================================================

function getContextWindow() {
    // Find the ctx value for the current model
    const providerData = models[currentProvider];
    if (!providerData) return 128000;
    const m = providerData.models.find((m) => m.id === currentModel);
    return m?.ctx || 128000;
}

function estimateTokens(text) {
    if (!text) return 0;
    return Math.max(1, Math.ceil(text.length / 4) + 4);
}

function formatTokenCount(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "K";
    return n.toString();
}

function getConvoTokens(convo) {
    if (!convo) return 0;
    let total = 0;
    for (const msg of convo.messages) {
        total += estimateTokens(msg.content);
    }
    const sys = $("#system-prompt")?.value?.trim();
    if (sys) total += estimateTokens(sys);
    return total;
}

function updateContextMeter() {
    const convo = getActiveConvo();
    const used = getConvoTokens(convo);
    const max = getContextWindow();
    const pct = Math.min(100, (used / max) * 100);

    const fill = $("#context-bar-fill");
    fill.style.width = pct + "%";
    fill.classList.remove("warn", "danger");
    if (pct > 80) fill.classList.add("danger");
    else if (pct > 50) fill.classList.add("warn");

    $("#context-label").textContent = `${formatTokenCount(used)} / ${formatTokenCount(max)}`;

    if (contextPanelOpen) renderContextPanel();
}

function renderContextPanel() {
    const body = $("#context-panel-body");
    const convo = getActiveConvo();
    body.innerHTML = "";

    if (!convo || convo.messages.length === 0) {
        body.innerHTML = '<div style="padding:12px 16px;color:var(--text-muted);font-size:12px;">No messages yet. Start chatting to see shared memory context.</div>';
        $("#context-total").textContent = "0 tokens";
        return;
    }

    const sys = $("#system-prompt")?.value?.trim();
    let total = 0;

    // System prompt row
    if (sys) {
        const tokens = estimateTokens(sys);
        total += tokens;
        const row = document.createElement("div");
        row.className = "ctx-row";
        row.innerHTML = `
            <div class="ctx-role system">S</div>
            <span class="ctx-model-tag">system</span>
            <span class="ctx-preview">${escapeHtml(sys.slice(0, 80))}${sys.length > 80 ? "..." : ""}</span>
            <span class="ctx-tokens">~${tokens}</span>
        `;
        body.appendChild(row);
    }

    // Message rows
    for (const msg of convo.messages) {
        const tokens = estimateTokens(msg.content);
        total += tokens;
        const provider = msg.provider || "openai";
        const modelId = msg.model || "";
        const modelShort = getModelShortName(provider, modelId);
        const isUser = msg.role === "user";

        const row = document.createElement("div");
        row.className = "ctx-row";
        row.innerHTML = `
            <div class="ctx-role ${isUser ? "user" : provider}">${isUser ? "U" : PROVIDER_ICONS[provider] || "?"}</div>
            ${!isUser ? `<span class="ctx-model-tag">${escapeHtml(modelShort)}</span>` : '<span class="ctx-model-tag">you</span>'}
            <span class="ctx-preview">${escapeHtml(msg.content.slice(0, 100))}${msg.content.length > 100 ? "..." : ""}</span>
            <span class="ctx-tokens">~${tokens}</span>
        `;
        body.appendChild(row);
    }

    $("#context-total").textContent = `~${formatTokenCount(total)} tokens`;
}

function getModelShortName(provider, modelId) {
    if (!modelId) return provider;
    const providerData = models[provider];
    if (!providerData) return modelId;
    const m = providerData.models.find((m) => m.id === modelId);
    return m?.name || modelId;
}

// ========================================================================
//  PARAMETER CONTROLS
// ========================================================================

function buildParamControls() {
    const container = $("#params-container");
    container.innerHTML = "";
    const providerData = models[currentProvider];
    if (!providerData) return;

    currentParams = {};

    for (const [key, cfg] of Object.entries(providerData.params)) {
        currentParams[key] = cfg.default;

        const div = document.createElement("div");
        div.className = "param-slider";

        const displayName = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

        div.innerHTML = `
            <div class="param-slider-header">
                <span class="param-name">${displayName}</span>
                <span class="param-value">
                    <input type="text" id="param-val-${key}" value="${cfg.default ?? 'null'}" />
                </span>
            </div>
            <input type="range" id="param-${key}"
                min="${cfg.min}" max="${cfg.max}" step="${cfg.step}"
                value="${cfg.default ?? cfg.min}" />
        `;

        container.appendChild(div);

        const slider = div.querySelector(`#param-${key}`);
        const valInput = div.querySelector(`#param-val-${key}`);

        slider.addEventListener("input", () => {
            const v = parseFloat(slider.value);
            currentParams[key] = v;
            valInput.value = formatNumber(v, cfg.step);
        });

        valInput.addEventListener("change", () => {
            let v = valInput.value.trim();
            if (v === "null" || v === "") {
                currentParams[key] = null;
                valInput.value = "null";
                return;
            }
            v = parseFloat(v);
            if (isNaN(v)) return;
            v = Math.max(cfg.min, Math.min(cfg.max, v));
            currentParams[key] = v;
            slider.value = v;
            valInput.value = formatNumber(v, cfg.step);
        });
    }
}

function formatNumber(v, step) {
    if (v === null || v === undefined) return "null";
    if (step >= 1) return Math.round(v).toString();
    if (step >= 0.1) return v.toFixed(1);
    return v.toFixed(2);
}

function applyPreset(name) {
    const preset = PRESETS[name];
    if (!preset) return;

    $$(".preset-btn").forEach((b) => b.classList.remove("active"));
    $(`.preset-btn[data-preset="${name}"]`)?.classList.add("active");

    for (const [key, val] of Object.entries(preset)) {
        if (currentParams.hasOwnProperty(key)) {
            currentParams[key] = val;
            const slider = $(`#param-${key}`);
            const valInput = $(`#param-val-${key}`);
            if (slider) slider.value = val;
            if (valInput) valInput.value = val;
        }
    }
}

// ========================================================================
//  CONVERSATIONS
// ========================================================================

function newChat() {
    const convo = {
        id: Date.now().toString(),
        title: "New Chat",
        provider: currentProvider,
        model: currentModel,
        messages: [],
        created: new Date().toISOString(),
    };
    conversations.unshift(convo);
    activeConvoId = convo.id;
    saveConversations();
    renderConversations();
    renderMessages();
    updateContextMeter();
}

function getActiveConvo() {
    return conversations.find((c) => c.id === activeConvoId);
}

function saveConversations() {
    localStorage.setItem("chat-conversations", JSON.stringify(conversations));
}

function loadConversations() {
    renderConversations();
    if (conversations.length > 0 && !activeConvoId) {
        activeConvoId = conversations[0].id;
        const convo = getActiveConvo();
        if (convo) {
            currentProvider = convo.provider;
            currentModel = convo.model;
            $("#provider-select").value = currentProvider;
            populateModels();
        }
        renderMessages();
    }
}

function renderConversations() {
    const list = $("#conversations-list");
    list.innerHTML = "";

    for (const convo of conversations) {
        // Show multiple provider tags if the conversation has messages from different providers
        const usedProviders = [...new Set(convo.messages.filter((m) => m.provider).map((m) => m.provider))];
        if (usedProviders.length === 0) usedProviders.push(convo.provider);

        const div = document.createElement("div");
        div.className = `convo-item${convo.id === activeConvoId ? " active" : ""}`;

        const tags = usedProviders
            .map((p) => `<span class="convo-provider-tag ${p}">${PROVIDER_ICONS[p]}</span>`)
            .join("");

        div.innerHTML = `
            ${tags}
            <span class="convo-title">${escapeHtml(convo.title)}</span>
            <button class="convo-delete" title="Delete">&times;</button>
        `;

        div.querySelector(".convo-title").addEventListener("click", () => {
            activeConvoId = convo.id;
            // When switching to a convo, restore the last-used provider/model
            // but DON'T force it — let the user keep their current selection
            renderMessages();
            renderConversations();
            updateContextMeter();
        });

        div.querySelector(".convo-delete").addEventListener("click", (e) => {
            e.stopPropagation();
            conversations = conversations.filter((c) => c.id !== convo.id);
            if (activeConvoId === convo.id) {
                activeConvoId = conversations[0]?.id || null;
                if (!activeConvoId) newChat();
                else {
                    renderMessages();
                }
            }
            saveConversations();
            renderConversations();
            updateContextMeter();
        });

        list.appendChild(div);
    }
}

// ========================================================================
//  MESSAGES
// ========================================================================

function renderMessages() {
    const container = $("#messages");
    container.innerHTML = "";
    const convo = getActiveConvo();
    if (!convo) return;

    let lastProvider = null;
    let lastModel = null;

    for (const msg of convo.messages) {
        const msgProvider = msg.provider || convo.provider;
        const msgModel = msg.model || convo.model;

        // Socratic messages get their own rendering
        if (msg.socratic_name) {
            const pIdx = socraticNameToIdx(msg.socratic_name, convo);
            appendSocraticMessageEl(msg.socratic_name, msg.content, msgProvider, msgModel, pIdx);
            lastProvider = msgProvider;
            lastModel = msgModel;
            continue;
        }

        // Insert a model-switch divider when the responding model changes
        if (msg.role === "assistant" && lastProvider !== null) {
            if (msgProvider !== lastProvider || msgModel !== lastModel) {
                insertModelSwitchDivider(container, lastProvider, lastModel, msgProvider, msgModel);
            }
        }

        appendMessageEl(msg.role, msg.content, msgProvider, msgModel);

        if (msg.role === "assistant") {
            lastProvider = msgProvider;
            lastModel = msgModel;
        }
    }
    scrollToBottom();
    updateContextMeter();
}

function insertModelSwitchDivider(container, fromProvider, fromModel, toProvider, toModel) {
    const fromName = getModelShortName(fromProvider, fromModel);
    const toName = getModelShortName(toProvider, toModel);

    const div = document.createElement("div");
    div.className = "model-switch-divider";
    div.innerHTML = `
        <div class="divider-line"></div>
        <div class="divider-label">
            <span class="switch-dot ${fromProvider}"></span>
            ${escapeHtml(fromName)}
            &rarr;
            <span class="switch-dot ${toProvider}"></span>
            ${escapeHtml(toName)}
        </div>
        <div class="divider-line"></div>
    `;
    container.appendChild(div);
}

function appendMessageEl(role, content, provider, model) {
    const container = $("#messages");
    const div = document.createElement("div");
    div.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = `msg-avatar${role === "assistant" ? ` ${provider || currentProvider}` : ""}`;
    avatar.textContent = role === "user" ? "U" : PROVIDER_ICONS[provider || currentProvider] || "?";

    const body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = formatContent(content);

    const meta = document.createElement("div");
    meta.className = "msg-meta";

    // Show model tag on assistant messages
    if (role === "assistant" && model) {
        const modelTag = document.createElement("span");
        modelTag.className = "msg-model-tag";
        modelTag.textContent = getModelShortName(provider, model);
        meta.appendChild(modelTag);
    }

    if (role === "assistant") {
        const copyBtn = document.createElement("button");
        copyBtn.textContent = "Copy";
        copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(content);
            showToast("Copied to clipboard", "success");
        });
        meta.appendChild(copyBtn);
    }

    // Token estimate
    const tokenSpan = document.createElement("span");
    tokenSpan.style.cssText = "font-size:10px;font-family:var(--mono);color:var(--text-muted);";
    tokenSpan.textContent = `~${estimateTokens(content)} tok`;
    meta.appendChild(tokenSpan);

    const wrapper = document.createElement("div");
    wrapper.appendChild(body);
    wrapper.appendChild(meta);

    div.appendChild(avatar);
    div.appendChild(wrapper);
    container.appendChild(div);

    return body;
}

function formatContent(text) {
    if (!text) return "";
    let html = escapeHtml(text);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // Italic
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

    return html;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    const container = $("#messages");
    container.scrollTop = container.scrollHeight;
}

function updateHeader() {
    $("#active-provider").textContent = PROVIDER_NAMES[currentProvider] || currentProvider;
    $("#active-model").textContent = currentModel;

    const colors = {
        openai: "var(--openai-color)",
        anthropic: "var(--anthropic-color)",
        google: "var(--google-color)",
        grok: "var(--grok-color)",
    };
    $("#active-provider").style.color = colors[currentProvider] || "var(--accent)";
}

function showToast(msg, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ========================================================================
//  CHAT / STREAMING (with Shared Memory)
// ========================================================================

async function sendMessage() {
    if (codeMode) return sendCodeMessage();
    if (socraticMode) return sendSocraticMessage();

    const input = $("#user-input");
    const text = input.value.trim();
    if (!text || isStreaming) return;

    const convo = getActiveConvo();
    if (!convo) return;

    // Update convo's last-used provider/model (for history display)
    convo.provider = currentProvider;
    convo.model = currentModel;

    // Add user message with current provider context
    convo.messages.push({
        role: "user",
        content: text,
        provider: currentProvider,
        model: currentModel,
    });

    // Auto-title from first message
    if (convo.title === "New Chat") {
        convo.title = text.slice(0, 50) + (text.length > 50 ? "..." : "");
        renderConversations();
    }

    appendMessageEl("user", text, currentProvider, currentModel);
    input.value = "";
    autoResize(input);
    scrollToBottom();

    // Check if we're switching models mid-conversation
    const prevAssistantMsgs = convo.messages.filter((m) => m.role === "assistant");
    const lastAssistant = prevAssistantMsgs[prevAssistantMsgs.length - 1];
    const isSwitching = lastAssistant && (lastAssistant.provider !== currentProvider || lastAssistant.model !== currentModel);

    if (isSwitching) {
        insertModelSwitchDivider(
            $("#messages"),
            lastAssistant.provider,
            lastAssistant.model,
            currentProvider,
            currentModel,
        );
    }

    // Create assistant message element for streaming
    const bodyEl = appendMessageEl("assistant", "", currentProvider, currentModel);
    bodyEl.classList.add("streaming-cursor");
    scrollToBottom();

    isStreaming = true;
    $("#send-btn").classList.add("hidden");
    $("#stop-btn").classList.remove("hidden");
    lastAssistantMessage = "";

    abortController = new AbortController();

    try {
        // Build API messages — the full conversation is the "shared memory"
        // All messages go to the new model regardless of who generated them
        const apiMessages = convo.messages
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m) => ({
                role: m.role,
                content: m.content,
            }));

        // Build a handoff system prompt if switching models
        let systemPrompt = $("#system-prompt").value.trim();
        if (isSwitching) {
            const fromName = getModelShortName(lastAssistant.provider, lastAssistant.model);
            const handoff = `[Context: You are continuing a conversation that was previously handled by ${fromName}. The full conversation history is provided above. Continue seamlessly from where the previous model left off, maintaining the same tone and context.]`;
            systemPrompt = systemPrompt ? `${systemPrompt}\n\n${handoff}` : handoff;
        }

        const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                provider: currentProvider,
                model: currentModel,
                messages: apiMessages,
                params: currentParams,
                system_prompt: systemPrompt,
            }),
            signal: abortController.signal,
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const data = JSON.parse(jsonStr);
                    if (data.token) {
                        lastAssistantMessage += data.token;
                        bodyEl.innerHTML = formatContent(lastAssistantMessage);
                        scrollToBottom();
                    } else if (data.error) {
                        bodyEl.innerHTML = `<span style="color:var(--danger)">Error: ${escapeHtml(data.error)}</span>`;
                        bodyEl.classList.remove("streaming-cursor");
                    }
                } catch (e) {
                    // Skip malformed JSON
                }
            }
        }
    } catch (e) {
        if (e.name !== "AbortError") {
            bodyEl.innerHTML = `<span style="color:var(--danger)">Error: ${escapeHtml(e.message)}</span>`;
        }
    }

    bodyEl.classList.remove("streaming-cursor");
    isStreaming = false;
    $("#send-btn").classList.remove("hidden");
    $("#stop-btn").classList.add("hidden");

    // Save assistant message with provider/model metadata
    if (lastAssistantMessage) {
        convo.messages.push({
            role: "assistant",
            content: lastAssistantMessage,
            provider: currentProvider,
            model: currentModel,
        });
    }
    saveConversations();
    updateContextMeter();

    if (lastAssistantMessage) {
        $("#sms-send").disabled = false;
    }
}

function stopStreaming() {
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
}

// ========================================================================
//  SMS
// ========================================================================

async function sendSMS() {
    const phone = $("#sms-phone").value.trim();
    const carrier = $("#sms-carrier").value;
    const message = lastAssistantMessage;

    if (!phone || !message) {
        showToast("Enter phone number and have a response to send", "error");
        return;
    }

    try {
        const res = await fetch("/api/sms", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, carrier, message }),
        });
        const data = await res.json();
        if (data.success) {
            showToast(`SMS sent to ${data.sent_to}`, "success");
        } else {
            showToast(data.error || "SMS failed", "error");
        }
    } catch (e) {
        showToast(`SMS error: ${e.message}`, "error");
    }
}

// ========================================================================
//  EXPORT
// ========================================================================

function exportChat() {
    const convo = getActiveConvo();
    if (!convo || convo.messages.length === 0) {
        showToast("Nothing to export", "error");
        return;
    }

    let text = `# ${convo.title}\n`;
    text += `Date: ${new Date(convo.created).toLocaleDateString()}\n\n`;
    text += "---\n\n";

    let lastProvider = null;
    let lastModel = null;

    for (const msg of convo.messages) {
        const provider = msg.provider || convo.provider;
        const model = msg.model || convo.model;

        if (msg.role === "assistant" && lastProvider !== null && (provider !== lastProvider || model !== lastModel)) {
            text += `---\n*Switched to ${getModelShortName(provider, model)}*\n---\n\n`;
        }

        const role = msg.role === "user" ? "You" : `${getModelShortName(provider, model)}`;
        text += `**${role}:**\n${msg.content}\n\n`;

        if (msg.role === "assistant") {
            lastProvider = provider;
            lastModel = model;
        }
    }

    const blob = new Blob([text], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${convo.title.slice(0, 30).replace(/[^a-z0-9]/gi, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Chat exported", "success");
}

// ========================================================================
//  API KEY VALIDATION
// ========================================================================

async function validateApiKeys() {
    try {
        const res = await fetch("/api/validate-keys");
        validProviders = await res.json();
        updateProviderIndicators();
    } catch (e) {
        // If endpoint doesn't exist yet, assume all valid
        for (const key of Object.keys(models)) {
            validProviders[key] = true;
        }
    }
}

function updateProviderIndicators() {
    // Mark invalid providers in the provider select dropdown
    const sel = $("#provider-select");
    for (const opt of sel.options) {
        const valid = validProviders[opt.value] !== false;
        opt.textContent = models[opt.value]?.name + (valid ? "" : " (no key)");
        opt.style.color = valid ? "" : "var(--danger, #ef4444)";
    }
    // Update Socratic cards if they exist
    if (socraticParticipants.length > 0) renderSocraticCards();
}

// ========================================================================
//  SOCRATIC MODE
// ========================================================================

async function initSocratic() {
    try {
        const res = await fetch("/api/socratic/defaults");
        socraticParticipants = await res.json();
    } catch (e) {
        socraticParticipants = [];
    }
}

function toggleSocratic() {
    socraticMode = !socraticMode;
    const btn = $("#socratic-toggle");
    const panel = $("#socratic-panel");

    if (socraticMode) {
        btn.classList.add("active");
        panel.classList.remove("hidden");
        renderSocraticCards();
    } else {
        btn.classList.remove("active");
        panel.classList.add("hidden");
    }
}

function renderSocraticCards() {
    const container = $("#socratic-participants");
    container.innerHTML = "";

    socraticParticipants.forEach((p, i) => {
        const colorClass = PERSONA_COLORS[i % PERSONA_COLORS.length];
        const avatarLetter = p.name.startsWith("The ") ? p.name.charAt(4) : p.name.charAt(0);
        const providerValid = validProviders[p.provider] !== false;

        const card = document.createElement("div");
        card.className = `socratic-card`;

        // Build provider options
        const providerOpts = Object.entries(models)
            .map(([key, val]) => {
                const valid = validProviders[key] !== false;
                return `<option value="${key}"${key === p.provider ? " selected" : ""}${!valid ? ' style="color:#ef4444"' : ""}>${val.name}${valid ? "" : " ✗"}</option>`;
            })
            .join("");

        // Build model options for selected provider
        const modelOpts = (models[p.provider]?.models || [])
            .map((m) => `<option value="${m.id}"${m.id === p.model ? " selected" : ""}>${m.name}</option>`)
            .join("");

        card.innerHTML = `
            ${socraticParticipants.length > 2 ? `<button class="socratic-card-remove" data-idx="${i}" title="Remove">&times;</button>` : ""}
            <div class="socratic-card-header">
                <div class="socratic-avatar ${colorClass}">${avatarLetter}</div>
                <div class="socratic-card-name">
                    <input value="${escapeHtml(p.name)}" data-idx="${i}" />
                </div>
                ${!providerValid ? '<span style="color:#ef4444;font-size:10px;font-weight:600;" title="API key invalid or missing">NO KEY</span>' : ""}
            </div>
            <div class="socratic-card-model">
                <select class="soc-provider" data-idx="${i}">${providerOpts}</select>
                <select class="soc-model" data-idx="${i}">${modelOpts}</select>
            </div>
            <textarea data-idx="${i}" rows="2" placeholder="Persona system prompt...">${escapeHtml(p.system || "")}</textarea>
        `;
        container.appendChild(card);
    });

    // Add participant button (max 6)
    if (socraticParticipants.length < 6) {
        const addBtn = document.createElement("button");
        addBtn.style.cssText =
            "grid-column:1/-1;padding:6px;font-size:11px;border:1px dashed var(--border);border-radius:var(--radius);background:transparent;color:var(--text-muted);cursor:pointer;transition:all 0.15s;";
        addBtn.textContent = "+ Add Participant";
        addBtn.addEventListener("mouseover", () => {
            addBtn.style.borderColor = "var(--accent)";
            addBtn.style.color = "var(--accent)";
        });
        addBtn.addEventListener("mouseout", () => {
            addBtn.style.borderColor = "var(--border)";
            addBtn.style.color = "var(--text-muted)";
        });
        addBtn.addEventListener("click", () => {
            socraticParticipants.push({
                name: `Participant ${socraticParticipants.length + 1}`,
                provider: "openai",
                model: "gpt-4o-mini",
                system: "",
            });
            renderSocraticCards();
        });
        container.appendChild(addBtn);
    }

    // Bind card events
    bindSocraticCardEvents(container);
}

function bindSocraticCardEvents(container) {
    container.querySelectorAll(".socratic-card-name input").forEach((input) => {
        input.addEventListener("change", (e) => {
            socraticParticipants[+e.target.dataset.idx].name = e.target.value;
        });
    });

    container.querySelectorAll(".soc-provider").forEach((sel) => {
        sel.addEventListener("change", (e) => {
            const idx = +e.target.dataset.idx;
            socraticParticipants[idx].provider = e.target.value;
            const providerModels = models[e.target.value]?.models || [];
            socraticParticipants[idx].model = providerModels[0]?.id || "";
            renderSocraticCards();
        });
    });

    container.querySelectorAll(".soc-model").forEach((sel) => {
        sel.addEventListener("change", (e) => {
            socraticParticipants[+e.target.dataset.idx].model = e.target.value;
        });
    });

    container.querySelectorAll(".socratic-card textarea").forEach((ta) => {
        ta.addEventListener("change", (e) => {
            socraticParticipants[+e.target.dataset.idx].system = e.target.value;
        });
    });

    container.querySelectorAll(".socratic-card-remove").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            socraticParticipants.splice(+e.target.dataset.idx, 1);
            renderSocraticCards();
        });
    });
}

function socraticNameToIdx(name, convo) {
    const names = [];
    for (const m of convo.messages) {
        if (m.socratic_name && !names.includes(m.socratic_name)) {
            names.push(m.socratic_name);
        }
    }
    return Math.max(0, names.indexOf(name));
}

function appendSocraticMessageEl(name, content, provider, model, participantIdx) {
    const container = $("#messages");
    const div = document.createElement("div");
    const colorClass = PERSONA_COLORS[participantIdx % PERSONA_COLORS.length];
    div.className = "message assistant socratic";

    const avatarLetter = name.startsWith("The ") ? name.charAt(4) : name.charAt(0);

    const avatar = document.createElement("div");
    avatar.className = `socratic-avatar ${colorClass}`;
    avatar.textContent = avatarLetter;

    const nameLabel = document.createElement("div");
    nameLabel.className = `socratic-name-label ${colorClass}`;
    nameLabel.textContent = name;

    const badge = document.createElement("span");
    badge.className = "socratic-badge";
    badge.innerHTML = `<span class="dot"></span>${escapeHtml(getModelShortName(provider, model))}`;

    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:4px;";
    header.appendChild(nameLabel);
    header.appendChild(badge);

    const body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = formatContent(content);

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const copyBtn = document.createElement("button");
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(content);
        showToast("Copied to clipboard", "success");
    });
    meta.appendChild(copyBtn);
    const tokenSpan = document.createElement("span");
    tokenSpan.style.cssText = "font-size:10px;font-family:var(--mono);color:var(--text-muted);";
    tokenSpan.textContent = `~${estimateTokens(content)} tok`;
    meta.appendChild(tokenSpan);

    const wrapper = document.createElement("div");
    wrapper.appendChild(header);
    wrapper.appendChild(body);
    wrapper.appendChild(meta);

    div.appendChild(avatar);
    div.appendChild(wrapper);
    container.appendChild(div);

    return body;
}

function insertSocraticRoundDivider(roundNum) {
    const container = $("#messages");
    const div = document.createElement("div");
    div.className = "socratic-round-divider";
    div.innerHTML = `
        <div class="divider-line"></div>
        <span class="round-label">Round ${roundNum}</span>
        <div class="divider-line"></div>
    `;
    container.appendChild(div);
}

async function sendSocraticMessage() {
    const input = $("#user-input");
    const text = input.value.trim();
    if (!text || isStreaming) return;

    const convo = getActiveConvo();
    if (!convo) return;

    // Filter out participants with invalid API keys
    const activeParticipants = socraticParticipants.filter((p) => validProviders[p.provider] !== false);
    if (activeParticipants.length === 0) {
        showToast("No participants have valid API keys. Check your provider keys.", "error");
        return;
    }

    const skipped = socraticParticipants.length - activeParticipants.length;
    if (skipped > 0) {
        const skippedNames = socraticParticipants
            .filter((p) => validProviders[p.provider] === false)
            .map((p) => p.name)
            .join(", ");
        showToast(`Skipping ${skipped} participant(s) with invalid keys: ${skippedNames}`, "error");
    }

    // Add user message
    convo.messages.push({
        role: "user",
        content: text,
        provider: "socratic",
        model: "roundtable",
    });

    if (convo.title === "New Chat") {
        convo.title = text.slice(0, 48) + (text.length > 48 ? "..." : "");
        renderConversations();
    }

    appendMessageEl("user", text, "socratic", "roundtable");
    input.value = "";
    autoResize(input);
    scrollToBottom();

    isStreaming = true;
    $("#send-btn").classList.add("hidden");
    $("#stop-btn").classList.remove("hidden");
    abortController = new AbortController();

    const rounds = parseInt($("#socratic-rounds").value) || 1;

    // Build history: all prior messages (excluding the one we just added)
    const apiHistory = convo.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .slice(0, -1)
        .map((m) => ({ role: m.role, content: m.content }));

    try {
        const response = await fetch("/api/socratic/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                participants: activeParticipants,
                history: apiHistory,
                user_message: text,
                rounds: rounds,
            }),
            signal: abortController.signal,
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let currentBodyEl = null;
        let currentContent = "";
        let currentParticipantInfo = null;
        let participantCounter = -1;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const data = JSON.parse(jsonStr);

                    if (data.participant_start) {
                        const { name, provider, model } = data.participant_start;
                        currentParticipantInfo = data.participant_start;
                        participantCounter++;
                        const pIdx = participantCounter % activeParticipants.length;
                        currentContent = "";
                        currentBodyEl = appendSocraticMessageEl(name, "", provider, model, pIdx);
                        currentBodyEl.classList.add("streaming-cursor");
                        scrollToBottom();
                    } else if (data.token && currentBodyEl) {
                        currentContent += data.token;
                        currentBodyEl.innerHTML = formatContent(currentContent);
                        scrollToBottom();
                    } else if (data.participant_done) {
                        if (currentBodyEl) {
                            currentBodyEl.classList.remove("streaming-cursor");
                        }
                        convo.messages.push({
                            role: "assistant",
                            content: data.participant_done.content,
                            provider: currentParticipantInfo?.provider || "unknown",
                            model: currentParticipantInfo?.model || "",
                            socratic_name: data.participant_done.name,
                        });
                    } else if (data.round) {
                        insertSocraticRoundDivider(data.round);
                        participantCounter = -1;
                    } else if (data.error) {
                        if (currentBodyEl) {
                            currentBodyEl.innerHTML = `<span style="color:var(--danger)">Error: ${escapeHtml(data.error)}</span>`;
                            currentBodyEl.classList.remove("streaming-cursor");
                        }
                    }
                } catch (e) {
                    // Skip malformed JSON
                }
            }
        }
    } catch (e) {
        if (e.name !== "AbortError") {
            showToast(`Socratic error: ${e.message}`, "error");
        }
    }

    isStreaming = false;
    $("#send-btn").classList.remove("hidden");
    $("#stop-btn").classList.add("hidden");
    saveConversations();
    updateContextMeter();
}

// ========================================================================
//  CODE MODE
// ========================================================================

function toggleCodeMode() {
    codeMode = !codeMode;
    const btn = $("#code-toggle");
    const panel = $("#code-panel");

    if (codeMode) {
        btn.classList.add("active");
        panel.classList.remove("hidden");
        if (socraticMode) toggleSocratic();
        codeApiMessages = [];
    } else {
        btn.classList.remove("active");
        panel.classList.add("hidden");
    }
}

async function sendCodeMessage() {
    const input = $("#user-input");
    const text = input.value.trim();
    if (!text || isStreaming) return;

    const convo = getActiveConvo();
    if (!convo) return;

    const model = $("#code-model-select").value;

    // Add user message to display
    convo.messages.push({
        role: "user",
        content: text,
        provider: "anthropic",
        model: model,
    });

    if (convo.title === "New Chat") {
        convo.title = text.slice(0, 48) + (text.length > 48 ? "..." : "");
        renderConversations();
    }

    appendMessageEl("user", text, "anthropic", model);
    input.value = "";
    autoResize(input);
    scrollToBottom();

    // Track in the Anthropic-format messages for multi-turn
    codeApiMessages.push({ role: "user", content: text });

    isStreaming = true;
    $("#send-btn").classList.add("hidden");
    $("#stop-btn").classList.remove("hidden");
    abortController = new AbortController();

    // Build the assistant message container
    const container = $("#messages");
    const assistantDiv = document.createElement("div");
    assistantDiv.className = "message assistant";

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar anthropic";
    avatar.textContent = "A";

    const wrapper = document.createElement("div");
    wrapper.style.cssText = "flex:1;min-width:0;";

    let bodyEl = document.createElement("div");
    bodyEl.className = "msg-body";
    wrapper.appendChild(bodyEl);

    assistantDiv.appendChild(avatar);
    assistantDiv.appendChild(wrapper);
    container.appendChild(assistantDiv);
    scrollToBottom();

    // Gather config
    const workingDir = $("#code-working-dir").value.trim() || ".";
    const maxTurns = parseInt($("#code-max-turns").value) || 25;
    const allowedTools = [];
    $$("#code-tools-checkboxes input:checked").forEach((cb) => allowedTools.push(cb.value));

    let fullTextContent = "";
    let currentToolBlock = null;

    try {
        const response = await fetch("/api/claude-code/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                messages: codeApiMessages,
                system_prompt: $("#system-prompt").value.trim(),
                working_directory: workingDir,
                max_turns: maxTurns,
                model: model,
                allowed_tools: allowedTools.length > 0 ? allowedTools : null,
            }),
            signal: abortController.signal,
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const data = JSON.parse(jsonStr);

                    if (data.turn) {
                        if (data.turn > 1) {
                            const turnDiv = document.createElement("div");
                            turnDiv.className = "turn-divider";
                            turnDiv.innerHTML = `
                                <div class="divider-line"></div>
                                <span class="turn-label">Turn ${data.turn} / ${data.max_turns}</span>
                                <div class="divider-line"></div>
                            `;
                            wrapper.appendChild(turnDiv);
                            // New body element for next turn's text
                            bodyEl = document.createElement("div");
                            bodyEl.className = "msg-body";
                            wrapper.appendChild(bodyEl);
                            fullTextContent = "";
                        }
                        $("#code-turn-counter").textContent = `Turn ${data.turn} / ${data.max_turns}`;
                    } else if (data.token) {
                        fullTextContent += data.token;
                        bodyEl.innerHTML = formatContent(fullTextContent);
                        bodyEl.classList.add("streaming-cursor");
                        scrollToBottom();
                    } else if (data.tool_call_start) {
                        bodyEl.classList.remove("streaming-cursor");
                        currentToolBlock = createToolCallBlock(data.tool_call_start.name, data.tool_call_start.id);
                        wrapper.appendChild(currentToolBlock);
                        scrollToBottom();
                    } else if (data.tool_call_input && currentToolBlock) {
                        const inputPre = currentToolBlock.querySelector(".tool-input-content");
                        if (inputPre) {
                            inputPre.textContent = formatToolInput(data.tool_call_input.name, data.tool_call_input.input);
                        }
                        scrollToBottom();
                    } else if (data.tool_call_result && currentToolBlock) {
                        const resultPre = currentToolBlock.querySelector(".tool-result-content");
                        const statusEl = currentToolBlock.querySelector(".tool-call-status");
                        if (resultPre) {
                            const result = data.tool_call_result.result;
                            const isError = !!result.error;
                            resultPre.textContent = result.output || result.error || "(no output)";
                            if (data.tool_call_result.name === "bash_exec" && !isError) {
                                resultPre.classList.add("bash-output");
                            }
                            if (isError) resultPre.classList.add("error-output");
                            if (statusEl) {
                                statusEl.textContent = isError ? "ERROR" : "DONE";
                                statusEl.className = `tool-call-status ${isError ? "error" : "success"}`;
                            }
                        }
                        // New body for text after tool call
                        bodyEl = document.createElement("div");
                        bodyEl.className = "msg-body";
                        wrapper.appendChild(bodyEl);
                        fullTextContent = "";
                        currentToolBlock = null;
                        scrollToBottom();
                    } else if (data.done) {
                        bodyEl.classList.remove("streaming-cursor");
                        if (data.turns_used) {
                            $("#code-turn-counter").textContent = `Done (${data.turns_used} turn${data.turns_used > 1 ? "s" : ""})`;
                        }
                    } else if (data.error) {
                        bodyEl.innerHTML = `<span style="color:var(--danger)">${escapeHtml(data.error)}</span>`;
                        bodyEl.classList.remove("streaming-cursor");
                    }
                } catch (e) {
                    // Skip malformed JSON
                }
            }
        }
    } catch (e) {
        if (e.name !== "AbortError") {
            bodyEl.innerHTML = `<span style="color:var(--danger)">Error: ${escapeHtml(e.message)}</span>`;
        }
    }

    bodyEl.classList.remove("streaming-cursor");
    isStreaming = false;
    $("#send-btn").classList.remove("hidden");
    $("#stop-btn").classList.add("hidden");

    // Save a simplified assistant message for conversation history
    if (fullTextContent) {
        convo.messages.push({
            role: "assistant",
            content: fullTextContent,
            provider: "anthropic",
            model: model,
        });
        // Add to code API messages for multi-turn context
        codeApiMessages.push({ role: "assistant", content: fullTextContent });
    }
    saveConversations();
    updateContextMeter();

    if (fullTextContent) {
        $("#sms-send").disabled = false;
        lastAssistantMessage = fullTextContent;
    }
}

function createToolCallBlock(toolName, toolId) {
    const block = document.createElement("div");
    block.className = "tool-call-block expanded";
    block.innerHTML = `
        <div class="tool-call-header">
            <span class="tool-call-icon">&#9654;</span>
            <span class="tool-call-name">${escapeHtml(toolName)}</span>
            <span class="tool-call-status running">RUNNING</span>
        </div>
        <div class="tool-call-body">
            <div class="tool-call-section">
                <div class="tool-call-section-label">Input</div>
                <pre class="tool-input-content">...</pre>
            </div>
            <div class="tool-call-section">
                <div class="tool-call-section-label">Output</div>
                <pre class="tool-result-content">Executing...</pre>
            </div>
        </div>
    `;
    block.querySelector(".tool-call-header").addEventListener("click", () => {
        block.classList.toggle("expanded");
    });
    return block;
}

function formatToolInput(toolName, input) {
    if (toolName === "bash_exec") return `$ ${input.command || ""}`;
    if (toolName === "read_file") {
        let s = input.file_path || "";
        if (input.offset) s += ` (from line ${input.offset})`;
        if (input.limit) s += ` (${input.limit} lines)`;
        return s;
    }
    if (toolName === "write_file") return `${input.file_path}\n---\n${input.content || ""}`;
    if (toolName === "edit_file") return `${input.file_path}\n--- old ---\n${input.old_string || ""}\n--- new ---\n${input.new_string || ""}`;
    if (toolName === "list_files") return input.pattern || "**/*";
    if (toolName === "search_files") return `/${input.pattern || ""}/ in ${input.file_glob || "**/*"}`;
    return JSON.stringify(input, null, 2);
}

// ========================================================================
//  AUTO-RESIZE TEXTAREA
// ========================================================================

function autoResize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
}

// ========================================================================
//  EVENT BINDINGS
// ========================================================================

function bindEvents() {
    // Provider change — no longer resets the conversation
    $("#provider-select").addEventListener("change", (e) => {
        currentProvider = e.target.value;
        const providerModels = models[currentProvider]?.models;
        currentModel = providerModels?.[0]?.id || "";
        populateModels();
        updateContextMeter();
    });

    // Model change
    $("#model-select").addEventListener("change", (e) => {
        currentModel = e.target.value;
        updateHeader();
        updateContextMeter();
    });

    // Send message
    $("#send-btn").addEventListener("click", sendMessage);
    $("#stop-btn").addEventListener("click", stopStreaming);

    // Enter to send, Shift+Enter for newline
    $("#user-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    $("#user-input").addEventListener("input", (e) => autoResize(e.target));

    // Sidebar toggle
    $("#sidebar-toggle").addEventListener("click", () => {
        $("#sidebar").classList.add("collapsed");
        $("#sidebar-open").classList.remove("hidden");
    });

    $("#sidebar-open").addEventListener("click", () => {
        $("#sidebar").classList.remove("collapsed");
        $("#sidebar-open").classList.add("hidden");
    });

    // New chat
    $("#new-chat").addEventListener("click", newChat);

    // Export
    $("#export-chat").addEventListener("click", exportChat);

    // Presets
    $$(".preset-btn").forEach((btn) => {
        btn.addEventListener("click", () => applyPreset(btn.dataset.preset));
    });

    // SMS
    $("#sms-send").addEventListener("click", sendSMS);

    // Token estimate on input
    $("#user-input").addEventListener("input", () => {
        const text = $("#user-input").value;
        const est = Math.ceil(text.length / 4);
        $("#token-estimate").textContent = text ? `~${est} tokens` : "";
    });

    // System prompt changes update context meter
    $("#system-prompt").addEventListener("input", () => updateContextMeter());

    // Context panel toggle
    $("#context-panel-toggle").addEventListener("click", () => {
        contextPanelOpen = !contextPanelOpen;
        const panel = $("#context-panel");
        const btn = $("#context-panel-toggle");
        if (contextPanelOpen) {
            panel.classList.remove("hidden");
            btn.classList.add("active");
            renderContextPanel();
        } else {
            panel.classList.add("hidden");
            btn.classList.remove("active");
        }
    });

    // Help / Docs
    $("#help-toggle").addEventListener("click", () => {
        $("#help-overlay").classList.remove("hidden");
    });
    $("#help-close").addEventListener("click", () => {
        $("#help-overlay").classList.add("hidden");
    });
    $("#help-overlay").addEventListener("click", (e) => {
        if (e.target === e.currentTarget) $("#help-overlay").classList.add("hidden");
    });
    $$("#help-nav .help-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            $$("#help-nav .help-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            $$("#help-body .help-section").forEach((s) => s.classList.add("hidden"));
            const target = $(`#help-body .help-section[data-tab="${tab.dataset.tab}"]`);
            if (target) target.classList.remove("hidden");
        });
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !$("#help-overlay").classList.contains("hidden")) {
            $("#help-overlay").classList.add("hidden");
        }
    });

    // Code mode toggle
    $("#code-toggle").addEventListener("click", toggleCodeMode);

    // Socratic mode toggle
    $("#socratic-toggle").addEventListener("click", toggleSocratic);

    // Socratic reset to defaults
    $("#socratic-reset").addEventListener("click", async () => {
        try {
            const res = await fetch("/api/socratic/defaults");
            socraticParticipants = await res.json();
        } catch (e) {}
        renderSocraticCards();
    });
}

// ========================================================================
//  BOOT
// ========================================================================

init();
