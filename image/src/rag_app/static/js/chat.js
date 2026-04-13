document.addEventListener('DOMContentLoaded', () => {

    // ---------------------------------------------------------------------------
    // Element references
    // ---------------------------------------------------------------------------
    const chatBox        = document.getElementById('chatBox');
    const userInput      = document.getElementById('userInput');
    const sendBtn        = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');

    // ---------------------------------------------------------------------------
    // Session ID — unique per browser tab
    // ---------------------------------------------------------------------------
    const sessionId = "sess_" + Date.now().toString(36) + "_" + Math.random().toString(36).substr(2, 9);
    console.log("Session ID:", sessionId);

    let chatHistory = [];

    // ---------------------------------------------------------------------------
    // Lead tracking — updated as the user asks questions
    // ---------------------------------------------------------------------------
    let leadData = {
        session_id: sessionId,
        phone_number: null,
        question_count: 0,
        asked_about_price: false,
        asked_about_registration: false,
    };
    function updateLeadKeywords(message) {
        // intentionally empty — intent detection handled by backend LLM
    }

    // ---------------------------------------------------------------------------
    // Submit lead to backend (called after phone is collected OR after 3 questions)
    // ---------------------------------------------------------------------------
    async function submitLead() {
        if (!leadData.phone_number) return; // no phone = nothing to submit
        try {
            await fetch('/api/lead/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(leadData)
            });
        } catch (e) {
            console.warn("Lead submit failed:", e);
        }
    }

    // ---------------------------------------------------------------------------
    // DOMPurify hook — open all links in new tab
    // ---------------------------------------------------------------------------
    if (typeof DOMPurify !== 'undefined') {
        DOMPurify.addHook('afterSanitizeAttributes', function (node) {
            if (node.tagName === 'A') {
                node.setAttribute('target', '_blank');
                node.setAttribute('rel', 'noopener noreferrer');
            }
        });
    }

    // ---------------------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------------------
    function scrollToBottom() {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function createMessageElement(sender) {
        const div = document.createElement('div');
        div.className = `message ${sender}-message`;
        chatBox.insertBefore(div, typingIndicator);
        return div;
    }

    function appendUserMessage(text) {
        const div = createMessageElement('user');
        div.textContent = text;
        scrollToBottom();
    }

    function setInputDisabled(state) {
        userInput.disabled = state;
        sendBtn.disabled   = state;
    }

    // ---------------------------------------------------------------------------
    // Phone form — injected into the chat area before the first message
    // ---------------------------------------------------------------------------
function showPhoneForm() {
        // Disable chat until phone is handled
        setInputDisabled(true);

        // هنا بنشوف هل إحنا في صفحة الإنجليزي ولا العربي من اللينك
        const isEnglish = window.location.pathname.includes('/chat-en');

        // تحديد النصوص بناءً على الصفحة
        const welcomeText = isEnglish ? '👋 Welcome!' : '👋 أهلاً بك!';
        const instructionText = isEnglish 
            ? 'To help you better,<br>please enter your mobile number to start.' 
            : 'عشان نقدر نساعدك أحسن،<br>ادخل رقم موبايلك وهنكمل معاك.';
        const btnText = isEnglish ? 'Start' : 'ابدأ';
        const alignText = isEnglish ? 'left' : 'right'; // لضبط المحاذاة

        const formDiv = document.createElement('div');
        formDiv.id = 'phoneFormWrapper';
        formDiv.className = 'message bot-message';
        formDiv.style.cssText = `max-width:340px; padding:18px 20px; text-align: ${alignText};`;

        formDiv.innerHTML = `
            <div style="font-weight:700; margin-bottom:8px; color:#008537;">
                ${welcomeText}
            </div>
            <p style="font-size:0.9rem; margin:0 0 14px; line-height:1.5; color:#444;">
                ${instructionText}
            </p>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; direction: ltr;">
                <input
                    id="phoneInput"
                    type="tel"
                    placeholder="05xxxxxxxx"
                    maxlength="10"
                    style="flex:1; min-width:130px; padding:9px 14px; border:1px solid #ced4da;
                           border-radius:25px; font-family:inherit; font-size:0.9rem; outline:none; text-align: left;">
                <button
                    id="phoneSubmitBtn"
                    style="background:#008537; color:white; border:none; padding:9px 18px;
                           border-radius:25px; cursor:pointer; font-weight:700; font-size:0.9rem;
                           white-space:nowrap;">
                    ${btnText}
                </button>
            </div>
        `;

        chatBox.insertBefore(formDiv, typingIndicator);
        scrollToBottom();

        // Focus phone input
        setTimeout(() => document.getElementById('phoneInput')?.focus(), 100);

        // Submit handler
        document.getElementById('phoneSubmitBtn').addEventListener('click', handlePhoneSubmit);
        document.getElementById('phoneInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handlePhoneSubmit();
        });
    }

    function handlePhoneSubmit() {
        const phone = document.getElementById('phoneInput')?.value.trim();
        if (!phone || phone.length < 9) {
            document.getElementById('phoneInput').style.borderColor = '#dc3545';
            return;
        }
        leadData.phone_number = phone;
        removePhoneForm();
        submitLead();
        addBotGreeting(phone);
        setInputDisabled(false);
        userInput.focus();
    }

    function handlePhoneSkip() {
        // Phone skipped — still track behaviour, just no phone
        removePhoneForm();
        addBotGreeting(null);
        setInputDisabled(false);
        userInput.focus();
    }

    function removePhoneForm() {
        document.getElementById('phoneFormWrapper')?.remove();
    }

function addBotGreeting(phone) {
        // بنشيك برضه إحنا في صفحة الإنجليزي ولا لأ
        const isEnglish = window.location.pathname.includes('/chat-en');
        const div = createMessageElement('bot');

        // تحديد الرسالة بناءً على اللغة
        if (isEnglish) {
            div.innerHTML = phone
                ? `<strong>Hello!</strong> How can I help you today?`
                : `<strong>Welcome!</strong> How can I help you today?`;
        } else {
            div.innerHTML = phone
                ? `<strong>أهلاً!</strong> كيف يمكنني خدمتك اليوم؟`
                : `<strong>مرحباً بك!</strong> كيف يمكنني خدمتك اليوم؟`;
        }
        
        scrollToBottom();
    }

    // ---------------------------------------------------------------------------
    // Main send function
    // ---------------------------------------------------------------------------
    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        userInput.value = '';
        setInputDisabled(true);

        // Track lead keywords
        leadData.question_count += 1;
        updateLeadKeywords(message);

        // Re-submit lead data on every message if we have a phone number
        // (keeps question_count + keyword flags up to date in the DB)
        if (leadData.phone_number) submitLead();

        appendUserMessage(message);

        typingIndicator.style.display = 'block';
        scrollToBottom();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message:    message,
                    history:    chatHistory,
                    session_id: sessionId
                })
            });

            if (!response.ok) throw new Error('Server error');

            const reader  = response.body.getReader();
            const decoder = new TextDecoder();
            let botMessageFull = '';
            let botMessageDiv  = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                botMessageFull += chunk;

                if (!botMessageDiv) {
                    typingIndicator.style.display = 'none';
                    botMessageDiv = createMessageElement('bot');
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
            setInputDisabled(false);
            userInput.focus();
            scrollToBottom();
        }
    }

    // ---------------------------------------------------------------------------
    // Event listeners
    // ---------------------------------------------------------------------------
    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // ---------------------------------------------------------------------------
    // Init — show phone form first, then let user chat
    // ---------------------------------------------------------------------------
    showPhoneForm();

});