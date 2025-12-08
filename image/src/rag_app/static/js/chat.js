document.addEventListener('DOMContentLoaded', () => {
    
    const chatBox = document.getElementById('chatBox');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');

    const sessionId = "sess_" + Date.now().toString(36) + "_" + Math.random().toString(36).substr(2, 9);
    let chatHistory = []; 

    function scrollToBottom() {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function createMessageElement(sender) {
        const div = document.createElement('div');
        div.className = `message ${sender}-message`;
        // إضافة الرسالة قبل المؤشر
        chatBox.insertBefore(div, typingIndicator);
        return div;
    }

    function appendUserMessage(text) {
        const div = createMessageElement('user');
        div.textContent = text;
        scrollToBottom();
    }

    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        userInput.value = '';
        userInput.disabled = true;
        sendBtn.disabled = true;

        // 1. عرض رسالة المستخدم
        appendUserMessage(message);

        // 2. إظهار النقط فوراً (بدون تأخير)
        typingIndicator.style.display = 'block';
        scrollToBottom();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    history: chatHistory,
                    session_id: sessionId 
                })
            });

            if (!response.ok) throw new Error('Server error');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let botMessageFull = '';
            let botMessageDiv = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                botMessageFull += chunk;

                // --- الحل السحري: إخفاء النقط وإنشاء الفقاعة عند أول حرف ---
                if (!botMessageDiv) {
                    typingIndicator.style.display = 'none'; // اختفاء النقط
                    botMessageDiv = createMessageElement('bot'); // ظهور الفقاعة
                }

                botMessageDiv.innerHTML = DOMPurify.sanitize(marked.parse(botMessageFull));
                scrollToBottom(); 
            }

            chatHistory.push([message, botMessageFull]);

        } catch (error) {
            console.error("Error:", error);
            typingIndicator.style.display = 'none';
            const errorDiv = createMessageElement('bot');
            errorDiv.textContent = "عذراً، حدث خطأ في الاتصال.";
            errorDiv.style.color = "red";
        } finally {
            userInput.disabled = false;
            sendBtn.disabled = false;
            userInput.focus();
            scrollToBottom();
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    userInput.focus();
});