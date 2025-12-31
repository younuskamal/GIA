/**
 * GIA Frontend Logic - ChatGPT-Style UI
 */

const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const loadingOverlay = document.getElementById('loadingOverlay');
const modelBadge = document.getElementById('modelBadge');
const trainButton = document.getElementById('trainButton');
const newChatBtn = document.getElementById('newChatBtn');

// API Configuration
const API_URL = 'http://127.0.0.1:8000';

/**
 * Utility: Create a message element
 */
function createMessage(text, isBot = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isBot ? 'bot-message' : 'user-message'}`;

    // Convert bold markdown to HTML for better display
    const formattedText = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');

    messageDiv.innerHTML = `
        <div class="message-wrapper">
            <div class="message-avatar">${isBot ? '💎' : '👤'}</div>
            <div class="message-content">
                <div class="message-text">${formattedText}</div>
            </div>
        </div>
    `;

    return messageDiv;
}

/**
 * Send Message to Backend
 */
async function sendMessage(text) {
    if (!text.trim()) return;

    // 1. Add User Message
    chatMessages.appendChild(createMessage(text, false));
    messageInput.value = '';
    messageInput.style.height = 'auto'; // Reset height
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // 2. Show Loading
    loadingOverlay.style.display = 'flex';

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        if (!response.ok) throw new Error('فشل الاتصال بـ GIA');

        const data = await response.json();

        // 3. Add Bot Response
        chatMessages.appendChild(createMessage(data.response, true));
    } catch (error) {
        chatMessages.appendChild(createMessage(`❌ خطأ: ${error.message}`, true));
    } finally {
        loadingOverlay.style.display = 'none';
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

/**
 * Manual Training Trigger
 */
async function triggerTraining() {
    if (!confirm('هل أنت متأكد من رغبتك في بدء عملية إعادة التدريب؟ قد تستغرق بضع دقائق.')) return;

    try {
        trainButton.innerHTML = '<span>⏳</span> جاري التدريب...';
        trainButton.disabled = true;

        const response = await fetch(`${API_URL}/train/manual`, { method: 'POST' });
        const data = await response.json();

        alert(data.message);
    } catch (error) {
        alert('حدث خطأ أثناء تشغيل التدريب.');
    } finally {
        trainButton.innerHTML = '<span>🔄</span> تحديث الذكاء';
        trainButton.disabled = false;
    }
}

/**
 * Poll Model Status
 */
async function updateModelStatus() {
    try {
        const response = await fetch(`${API_URL}/model/status`);
        if (!response.ok) return;

        const data = await response.json();
        modelBadge.textContent = data.active_version || 'Stable v1';

        if (data.status.includes('Training')) {
            modelBadge.classList.add('updating');
            modelBadge.textContent = 'Learning...';
        } else {
            modelBadge.classList.remove('updating');
        }
    } catch (e) {
        console.error('Status fetch failed');
    }
}

// --- Event Listeners ---

// Send on Click
sendButton.addEventListener('click', () => sendMessage(messageInput.value));

// New Chat (Clear Messages)
newChatBtn.addEventListener('click', () => {
    // Keep the welcome message only
    const welcome = chatMessages.querySelector('.bot-message');
    chatMessages.innerHTML = '';
    if (welcome) chatMessages.appendChild(welcome);
});

// Auto-expand textarea
messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Send on Enter (but not Shift+Enter)
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(messageInput.value);
    }
});

// Quick Action Buttons
document.querySelectorAll('.sidebar-link, .quick-action-pill').forEach(btn => {
    btn.addEventListener('click', () => {
        const msg = btn.getAttribute('data-message');
        sendMessage(msg);
    });
});

trainButton.addEventListener('click', triggerTraining);

// Initial state
updateModelStatus();
setInterval(updateModelStatus, 15000); // Check every 15s
