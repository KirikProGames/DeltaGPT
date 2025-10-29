class DeltaGPTApp {
    constructor() {
        this.currentChatId = null;
        this.chats = [];
        this.isProcessing = false;
        this.currentUser = null;
        this.thinkingMode = 'fast'; // 'fast' или 'deep'
        this.typingSpeed = 10; // Скорость печати (мс на символ)
        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.checkAuth();
        if (!this.currentUser) {
            this.showAuthModal();
        } else {
            await this.loadChats();
            this.showWelcome();
        }
    }

    setupEventListeners() {
        document.getElementById('userInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        document.getElementById('userInput').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });

        // Переключение режима мышления
        document.addEventListener('change', (e) => {
            if (e.target.id === 'thinkingMode') {
                this.thinkingMode = e.target.value;
                this.showNotification(`Режим: ${e.target.value === 'deep' ? 'Глубокое мышление' : 'Быстрый ответ'}`, 'info');
            }
        });
    }

    async checkAuth() {
        const savedUser = localStorage.getItem('deltagpt_user');
        if (savedUser) {
            this.currentUser = JSON.parse(savedUser);
            this.updateUserInfo();
            return true;
        }
        return false;
    }

    showAuthModal() {
        document.getElementById('authOverlay').style.display = 'flex';
    }

    hideAuthModal() {
        document.getElementById('authOverlay').style.display = 'none';
    }

    showLogin() {
        document.getElementById('loginForm').classList.add('active');
        document.getElementById('registerForm').classList.remove('active');
    }

    showRegister() {
        document.getElementById('registerForm').classList.add('active');
        document.getElementById('loginForm').classList.remove('active');
    }

    async login() {
        const username = document.getElementById('loginUsername').value;
        const password = document.getElementById('loginPassword').value;

        if (!username || !password) {
            this.showNotification('Заполните все поля', 'error');
            return;
        }

        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });

            const data = await response.json();
            
            if (data.success) {
                this.currentUser = data.user;
                this.hideAuthModal();
                this.showNotification('Успешный вход!', 'success');
                await this.loadChats();
                this.showWelcome();
                this.updateUserInfo();
            } else {
                this.showNotification(data.message, 'error');
            }
        } catch (error) {
            this.showNotification('Ошибка входа', 'error');
        }
    }

    async register() {
        const username = document.getElementById('regUsername').value;
        const email = document.getElementById('regEmail').value;
        const password = document.getElementById('regPassword').value;

        if (!username || !password || !email) {
            this.showNotification('Заполните все поля', 'error');
            return;
        }

        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password, email})
            });

            const data = await response.json();
            
            if (data.success) {
                this.showNotification('Регистрация успешна! Войдите в аккаунт.', 'success');
                this.showLogin();
                document.getElementById('regUsername').value = '';
                document.getElementById('regEmail').value = '';
                document.getElementById('regPassword').value = '';
            } else {
                this.showNotification(data.message, 'error');
            }
        } catch (error) {
            this.showNotification('Ошибка регистрации', 'error');
        }
    }

    updateUserInfo() {
        if (this.currentUser) {
            document.getElementById('sidebarUsername').textContent = this.currentUser.username;
            document.getElementById('sidebarTier').textContent = `Тип: ${this.currentUser.tier || 'Free'}`;
            localStorage.setItem('deltagpt_user', JSON.stringify(this.currentUser));
        }
    }

    logout() {
        this.currentUser = null;
        localStorage.removeItem('deltagpt_user');
        this.showAuthModal();
        this.clearChatMessages();
        this.chats = [];
        this.renderChatHistory();
        document.getElementById('sidebarUsername').textContent = 'Гость';
        document.getElementById('sidebarTier').textContent = 'Войдите в систему';
    }

    showNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 10px;
            color: white;
            z-index: 10000;
            background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
            animation: slideIn 0.3s ease;
        `;
        
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    async loadChats() {
        try {
            const response = await fetch(`/api/chats/user/${this.currentUser.username}`);
            const data = await response.json();
            
            if (data.success) {
                this.chats = data.chats;
                this.renderChatHistory();
            }
        } catch (error) {
            console.error('Error loading chats:', error);
        }
    }

    async newChat() {
        this.currentChatId = null;
        this.clearChatMessages();
        this.showWelcome();
        this.updateChatTitle('DELTAGPT');
        this.updateContextInfo(0);
    }

    async sendMessage() {
        if (this.isProcessing || !this.currentUser) {
            this.showAuthModal();
            return;
        }

        const input = document.getElementById('userInput');
        const message = input.value.trim();
        
        if (!message) return;

        this.isProcessing = true;
        this.updateSendButton();

        this.hideWelcome();

        this.addMessage(message, 'user');
        input.value = '';
        this.resetTextarea();

        // Показываем анимацию мышления
        this.showThinkingAnimation();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    message: message,
                    chat_id: this.currentChatId,
                    username: this.currentUser.username,
                    thinking_mode: this.thinkingMode
                })
            });

            const data = await response.json();
            
            this.removeThinkingAnimation();
            
            if (data.success) {
                // Очищаем текст от разметки и анимируем печать
                const cleanText = this.cleanText(data.response);
                await this.typeMessage(cleanText, 'assistant');
                this.currentChatId = data.chat_id;
                
                await this.loadChats();
                this.updateContextInfo(data.context_length);
            } else {
                this.addMessage(`❌ ${data.response}`, 'assistant');
            }
            
        } catch (error) {
            this.removeThinkingAnimation();
            this.addMessage('❌ Ошибка соединения с сервером', 'assistant');
        } finally {
            this.isProcessing = false;
            this.updateSendButton();
        }
    }

    // Очистка текста от разметки
    cleanText(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, '$1') // Убираем **жирный**
            .replace(/\*(.*?)\*/g, '$1')     // Убираем *курсив*
            .replace(/_(.*?)_/g, '$1')       // Убираем _подчеркивание_
            .replace(/`(.*?)`/g, '$1')       // Убираем `код`
            .replace(/#{1,6}\s?/g, '')       // Убираем заголовки ###
            .replace(/\[(.*?)\]\(.*?\)/g, '$1') // Убираем ссылки [текст](url)
            .replace(/<\/?[^>]+(>|$)/g, '')  // Убираем HTML теги
            .replace(/\n{3,}/g, '\n\n')      // Убираем лишние переносы
            .trim();
    }

    // Анимация печати текста
    async typeMessage(text, sender) {
        const messagesContainer = document.getElementById('chatMessages');
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-container';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = sender === 'user' ? 
            '<i class="fas fa-user"></i>' : 
            '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        
        contentDiv.appendChild(textDiv);
        messageContainer.appendChild(avatarDiv);
        messageContainer.appendChild(contentDiv);
        messageDiv.appendChild(messageContainer);
        messagesContainer.appendChild(messageDiv);
        
        // Анимация печати
        let index = 0;
        const typingInterval = setInterval(() => {
            if (index < text.length) {
                textDiv.innerHTML += text.charAt(index);
                index++;
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            } else {
                clearInterval(typingInterval);
                this.addCopyButtonListeners();
            }
        }, this.typingSpeed);
        
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    addMessage(text, sender) {
        const messagesContainer = document.getElementById('chatMessages');
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-container';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = sender === 'user' ? 
            '<i class="fas fa-user"></i>' : 
            '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.innerHTML = this.processContent(this.cleanText(text));
        
        contentDiv.appendChild(textDiv);
        messageContainer.appendChild(avatarDiv);
        messageContainer.appendChild(contentDiv);
        messageDiv.appendChild(messageContainer);
        messagesContainer.appendChild(messageDiv);
        
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        this.addCopyButtonListeners();
    }

    processContent(text) {
        // Обработка код-блоков (оставляем только их)
        let processed = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            const language = lang || 'text';
            return `
                <div class="code-block">
                    <div class="code-header">
                        <span class="code-language">${language}</span>
                        <button class="copy-btn" onclick="copyCodeToClipboard(this)">
                            <i class="fas fa-copy"></i> Копировать
                        </button>
                    </div>
                    <div class="code-content">
                        <pre><code>${this.escapeHtml(code.trim())}</code></pre>
                    </div>
                </div>
            `;
        });

        // Обработка переносов строк
        processed = processed.replace(/\n/g, '<br>');
        return processed;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async loadChat(chatId) {
        try {
            const response = await fetch(`/api/chat/${chatId}`);
            const data = await response.json();
            
            if (data.success) {
                this.clearChatMessages();
                this.hideWelcome();
                
                data.messages.forEach(msg => {
                    this.addMessage(msg.content, msg.role);
                });
                
                this.currentChatId = chatId;
                this.updateContextInfo(data.messages.length);
                
                if (data.chat_info) {
                    this.updateChatTitle(data.chat_info.title);
                }
            }
            
        } catch (error) {
            console.error('Error loading chat:', error);
        }
    }

    renderChatHistory() {
        const historyContainer = document.getElementById('chatHistory');
        historyContainer.innerHTML = '';

        this.chats.forEach(chat => {
            const chatItem = document.createElement('div');
            chatItem.className = `chat-history-item ${chat.id === this.currentChatId ? 'active' : ''}`;
            chatItem.onclick = () => this.loadChat(chat.id);
            
            chatItem.innerHTML = `
                <div class="chat-history-title">${chat.title}</div>
                <div class="chat-history-preview">${this.getChatPreview(chat.last_message)}</div>
                <div class="chat-history-meta">${this.formatDate(chat.updated_at)} • ${chat.message_count} сообщ.</div>
            `;
            
            historyContainer.appendChild(chatItem);
        });
    }

    getChatPreview(message) {
        if (!message || message === 'Нет сообщений') return 'Нет сообщений';
        const cleanText = this.cleanText(message);
        return cleanText.substring(0, 60) + (cleanText.length > 60 ? '...' : '');
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60 * 1000) return 'только что';
        if (diff < 60 * 60 * 1000) return `${Math.floor(diff / (60 * 1000))} мин назад`;
        if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / (60 * 60 * 1000))} ч назад`;
        
        return date.toLocaleDateString('ru-RU');
    }

    showWelcome() {
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">Δ</div>
                <h1>Добро пожаловать в DELTAGPT</h1>
                <p>Продвинутый AI ассистент с памятью контекста</p>
                <div class="thinking-mode-selector">
                    <label>Режим мышления:</label>
                    <select id="thinkingMode">
                        <option value="fast">🚀 Быстрый ответ</option>
                        <option value="deep">🧠 Глубокое мышление</option>
                    </select>
                </div>
                <div class="quick-actions">
                    <div class="quick-action" onclick="quickPrompt('Напиши код калькулятора на Python')">
                        <i class="fas fa-calculator"></i>
                        <span>Код калькулятора</span>
                    </div>
                    <div class="quick-action" onclick="quickPrompt('Объясни концепцию машинного обучения')">
                        <i class="fas fa-brain"></i>
                        <span>ML объяснение</span>
                    </div>
                    <div class="quick-action" onclick="quickPrompt('Помоги с оптимизацией кода')">
                        <i class="fas fa-rocket"></i>
                        <span>Оптимизация</span>
                    </div>
                </div>
            </div>
        `;
    }

    hideWelcome() {
        const welcome = document.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
        }
    }

    clearChatMessages() {
        document.getElementById('chatMessages').innerHTML = '';
    }

    // Анимация мышления
    showThinkingAnimation() {
        const messagesContainer = document.getElementById('chatMessages');
        const thinkingDiv = document.createElement('div');
        thinkingDiv.className = 'message assistant';
        thinkingDiv.id = 'thinking-animation';
        
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-container';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const thinkingContent = document.createElement('div');
        thinkingContent.className = 'thinking-animation';
        
        const thinkingText = document.createElement('div');
        thinkingText.className = 'thinking-text';
        thinkingText.textContent = this.thinkingMode === 'deep' ? 
            '🧠 Думаю глубоко...' : '⚡ Думаю...';
        
        const dots = document.createElement('div');
        dots.className = 'thinking-dots';
        dots.innerHTML = `
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
        `;
        
        thinkingContent.appendChild(thinkingText);
        thinkingContent.appendChild(dots);
        contentDiv.appendChild(thinkingContent);
        messageContainer.appendChild(avatarDiv);
        messageContainer.appendChild(contentDiv);
        thinkingDiv.appendChild(messageContainer);
        messagesContainer.appendChild(thinkingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    removeThinkingAnimation() {
        const thinkingAnimation = document.getElementById('thinking-animation');
        if (thinkingAnimation) {
            thinkingAnimation.remove();
        }
    }

    updateSendButton() {
        const btn = document.getElementById('sendBtn');
        if (this.isProcessing) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            btn.disabled = true;
        } else {
            btn.innerHTML = '<i class="fas fa-paper-plane"></i>';
            btn.disabled = false;
        }
    }

    updateChatTitle(title) {
        document.getElementById('currentChatTitle').textContent = title;
    }

    updateContextInfo(count) {
        document.getElementById('contextInfo').textContent = `Контекст: ${count} сообщений`;
    }

    resetTextarea() {
        const textarea = document.getElementById('userInput');
        textarea.style.height = 'auto';
    }

    addCopyButtonListeners() {
        document.querySelectorAll('.copy-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const codeBlock = this.closest('.code-block');
                const code = codeBlock.querySelector('code').textContent;
                copyCodeToClipboard(this, code);
            });
        });
    }
}

// Глобальные функции
function showLogin() {
    deltagptApp.showLogin();
}

function showRegister() {
    deltagptApp.showRegister();
}

function login() {
    deltagptApp.login();
}

function register() {
    deltagptApp.register();
}

function logout() {
    deltagptApp.logout();
}

function newChat() {
    deltagptApp.newChat();
}

function sendMessage() {
    deltagptApp.sendMessage();
}

function quickPrompt(prompt) {
    document.getElementById('userInput').value = prompt;
    document.getElementById('userInput').focus();
}

function copyCodeToClipboard(button, text = null) {
    if (!text) {
        const codeBlock = button.closest('.code-block');
        text = codeBlock.querySelector('code').textContent;
    }
    
    navigator.clipboard.writeText(text).then(() => {
        const originalHtml = button.innerHTML;
        button.innerHTML = '<i class="fas fa-check"></i> Скопировано!';
        
        setTimeout(() => {
            button.innerHTML = originalHtml;
        }, 2000);
    });
}

function clearContext() {
    if (deltagptApp.currentChatId) {
        fetch(`/api/chat/${deltagptApp.currentChatId}/clear`, { method: 'POST' })
            .then(() => {
                deltagptApp.clearChatMessages();
                deltagptApp.showWelcome();
                deltagptApp.updateContextInfo(0);
            });
    }
}

// Инициализация приложения
let deltagptApp;
document.addEventListener('DOMContentLoaded', function() {
    deltagptApp = new DeltaGPTApp();
});