// document.addEventListener('DOMContentLoaded', () => {

//     // ---------------------------------------------------------------------------
//     // Element references
//     // ---------------------------------------------------------------------------
//     const chatBox        = document.getElementById('chatBox');
//     const userInput      = document.getElementById('userInput');
//     const sendBtn        = document.getElementById('sendBtn');
//     const typingIndicator = document.getElementById('typingIndicator');

//     // ---------------------------------------------------------------------------
//     // Session ID — unique per browser tab
//     // ---------------------------------------------------------------------------
//     const sessionId = "sess_" + Date.now().toString(36) + "_" + Math.random().toString(36).substr(2, 9);
//     console.log("Session ID:", sessionId);

//     let chatHistory = [];

//     // ---------------------------------------------------------------------------
//     // Lead tracking — updated as the user asks questions
//     // ---------------------------------------------------------------------------
//     let leadData = {
//         session_id: sessionId,
//         phone_number: null,
//         question_count: 0,
//         asked_about_price: false,
//         asked_about_registration: false,
//     };
//     function updateLeadKeywords(message) {
//         // intentionally empty — intent detection handled by backend LLM
//     }

//     // ---------------------------------------------------------------------------
//     // Submit lead to backend (called after phone is collected OR after 3 questions)
//     // ---------------------------------------------------------------------------
//     async function submitLead() {
//         if (!leadData.phone_number) return; // no phone = nothing to submit
//         try {
//             await fetch('/api/lead/submit', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 body: JSON.stringify(leadData)
//             });
//         } catch (e) {
//             console.warn("Lead submit failed:", e);
//         }
//     }

//     // ---------------------------------------------------------------------------
//     // DOMPurify hook — open all links in new tab
//     // ---------------------------------------------------------------------------
//     if (typeof DOMPurify !== 'undefined') {
//         DOMPurify.addHook('afterSanitizeAttributes', function (node) {
//             if (node.tagName === 'A') {
//                 node.setAttribute('target', '_blank');
//                 node.setAttribute('rel', 'noopener noreferrer');
//             }
//         });
//     }

//     // ---------------------------------------------------------------------------
//     // Helpers
//     // ---------------------------------------------------------------------------
//     function scrollToBottom() {
//         chatBox.scrollTop = chatBox.scrollHeight;
//     }

//     function createMessageElement(sender) {
//         const div = document.createElement('div');
//         div.className = `message ${sender}-message`;
//         chatBox.insertBefore(div, typingIndicator);
//         return div;
//     }

//     function appendUserMessage(text) {
//         const div = createMessageElement('user');
//         div.textContent = text;
//         scrollToBottom();
//     }

//     function setInputDisabled(state) {
//         userInput.disabled = state;
//         sendBtn.disabled   = state;
//     }

//     // ---------------------------------------------------------------------------
//     // Phone form — injected into the chat area before the first message
//     // ---------------------------------------------------------------------------
// function showPhoneForm() {
//         // Disable chat until phone is handled
//         setInputDisabled(true);

//         // هنا بنشوف هل إحنا في صفحة الإنجليزي ولا العربي من اللينك
//         const isEnglish = window.location.pathname.includes('/chat-en');

//         // تحديد النصوص بناءً على الصفحة
//         const welcomeText = isEnglish ? '👋 Welcome!' : '👋 أهلاً بك!';
//         const instructionText = isEnglish 
//             ? 'To help you better,<br>please enter your mobile number to start.' 
//             : 'عشان نقدر نساعدك أحسن،<br>ادخل رقم موبايلك وهنكمل معاك.';
//         const btnText = isEnglish ? 'Start' : 'ابدأ';
//         const alignText = isEnglish ? 'left' : 'right'; // لضبط المحاذاة

//         const formDiv = document.createElement('div');
//         formDiv.id = 'phoneFormWrapper';
//         formDiv.className = 'message bot-message';
//         formDiv.style.cssText = `max-width:340px; padding:18px 20px; text-align: ${alignText};`;

//         formDiv.innerHTML = `
//             <div style="font-weight:700; margin-bottom:8px; color:#008537;">
//                 ${welcomeText}
//             </div>
//             <p style="font-size:0.9rem; margin:0 0 14px; line-height:1.5; color:#444;">
//                 ${instructionText}
//             </p>
//             <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; direction: ltr;">
//                 <input
//                     id="phoneInput"
//                     type="tel"
//                     placeholder="05xxxxxxxx"
//                     maxlength="10"
//                     style="flex:1; min-width:130px; padding:9px 14px; border:1px solid #ced4da;
//                            border-radius:25px; font-family:inherit; font-size:0.9rem; outline:none; text-align: left;">
//                 <button
//                     id="phoneSubmitBtn"
//                     style="background:#008537; color:white; border:none; padding:9px 18px;
//                            border-radius:25px; cursor:pointer; font-weight:700; font-size:0.9rem;
//                            white-space:nowrap;">
//                     ${btnText}
//                 </button>
//             </div>
//         `;

//         chatBox.insertBefore(formDiv, typingIndicator);
//         scrollToBottom();

//         // Focus phone input
//         setTimeout(() => document.getElementById('phoneInput')?.focus(), 100);

//         // Submit handler
//         document.getElementById('phoneSubmitBtn').addEventListener('click', handlePhoneSubmit);
//         document.getElementById('phoneInput').addEventListener('keypress', (e) => {
//             if (e.key === 'Enter') handlePhoneSubmit();
//         });
//     }

//     function handlePhoneSubmit() {
//         const phone = document.getElementById('phoneInput')?.value.trim();
//         if (!phone || phone.length < 9) {
//             document.getElementById('phoneInput').style.borderColor = '#dc3545';
//             return;
//         }
//         leadData.phone_number = phone;
//         removePhoneForm();
//         submitLead();
//         addBotGreeting(phone);
//         setInputDisabled(false);
//         userInput.focus();
//     }

//     function handlePhoneSkip() {
//         // Phone skipped — still track behaviour, just no phone
//         removePhoneForm();
//         addBotGreeting(null);
//         setInputDisabled(false);
//         userInput.focus();
//     }

//     function removePhoneForm() {
//         document.getElementById('phoneFormWrapper')?.remove();
//     }

// function addBotGreeting(phone) {
//         // بنشيك برضه إحنا في صفحة الإنجليزي ولا لأ
//         const isEnglish = window.location.pathname.includes('/chat-en');
//         const div = createMessageElement('bot');

//         // تحديد الرسالة بناءً على اللغة
//         if (isEnglish) {
//             div.innerHTML = phone
//                 ? `<strong>Hello!</strong> How can I help you today?`
//                 : `<strong>Welcome!</strong> How can I help you today?`;
//         } else {
//             div.innerHTML = phone
//                 ? `<strong>أهلاً!</strong> كيف يمكنني خدمتك اليوم؟`
//                 : `<strong>مرحباً بك!</strong> كيف يمكنني خدمتك اليوم؟`;
//         }
        
//         scrollToBottom();
//     }

//     // ---------------------------------------------------------------------------
//     // Main send function
//     // ---------------------------------------------------------------------------
//     async function sendMessage() {
//         const message = userInput.value.trim();
//         if (!message) return;

//         userInput.value = '';
//         setInputDisabled(true);

//         // Track lead keywords
//         leadData.question_count += 1;
//         updateLeadKeywords(message);

//         // Re-submit lead data on every message if we have a phone number
//         // (keeps question_count + keyword flags up to date in the DB)
//         if (leadData.phone_number) submitLead();

//         appendUserMessage(message);

//         typingIndicator.style.display = 'block';
//         scrollToBottom();

//         try {
//             const response = await fetch('/chat', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 body: JSON.stringify({
//                     message:    message,
//                     history:    chatHistory,
//                     session_id: sessionId
//                 })
//             });

//             if (!response.ok) throw new Error('Server error');

//             const reader  = response.body.getReader();
//             const decoder = new TextDecoder();
//             let botMessageFull = '';
//             let botMessageDiv  = null;

//             while (true) {
//                 const { done, value } = await reader.read();
//                 if (done) break;

//                 const chunk = decoder.decode(value, { stream: true });
//                 botMessageFull += chunk;

//                 if (!botMessageDiv) {
//                     typingIndicator.style.display = 'none';
//                     botMessageDiv = createMessageElement('bot');
//                 }

//                 botMessageDiv.innerHTML = DOMPurify.sanitize(marked.parse(botMessageFull));
//                 scrollToBottom();
//             }

//             chatHistory.push([message, botMessageFull]);

//         } catch (error) {
//             console.error("Error:", error);
//             typingIndicator.style.display = 'none';
//             const errorDiv = createMessageElement('bot');
//             errorDiv.textContent = "عذراً، حدث خطأ في الاتصال.";
//             errorDiv.style.color = "red";

//         } finally {
//             setInputDisabled(false);
//             userInput.focus();
//             scrollToBottom();
//         }
//     }

//     // ---------------------------------------------------------------------------
//     // Event listeners
//     // ---------------------------------------------------------------------------
//     sendBtn.addEventListener('click', sendMessage);
//     userInput.addEventListener('keypress', (e) => {
//         if (e.key === 'Enter') sendMessage();
//     });

//     // ---------------------------------------------------------------------------
//     // Init — show phone form first, then let user chat
//     // ---------------------------------------------------------------------------
//     showPhoneForm();

// });

document.addEventListener('DOMContentLoaded', () => {

    // ---------------------------------------------------------------------------
    // Element references
    // ---------------------------------------------------------------------------
    const chatBox        = document.getElementById('chatBox');
    const userInput      = document.getElementById('userInput');
    const sendBtn        = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');

    // ---------------------------------------------------------------------------
    // Session ID - unique per browser tab
    // ---------------------------------------------------------------------------
    const sessionId = "sess_" + Date.now().toString(36) + "_" + Math.random().toString(36).substr(2, 9);
    console.log("Session ID:", sessionId);

    let chatHistory = [];

    // ---------------------------------------------------------------------------
    // Lead tracking - updated as the user asks questions
    // ---------------------------------------------------------------------------
    let leadData = {
        session_id: sessionId,
        phone_number: null,
        is_registered: null, // New field for registration status
        city: null,          // New field for city
        question_count: 0,
        asked_about_price: false,
        asked_about_registration: false,
    };
    
    function updateLeadKeywords(message) {
        // Intentionally empty - intent detection handled by backend LLM
    }

    // ---------------------------------------------------------------------------
    // Submit lead to backend (called after data is collected OR after 3 questions)
    // ---------------------------------------------------------------------------
    async function submitLead() {
        if (!leadData.phone_number) return; // No phone = nothing to submit
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
    // DOMPurify hook - open all links in new tab
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
    // Phone & Info form - injected into the chat area before the first message
    // ---------------------------------------------------------------------------
    function showPhoneForm() {
        // Disable chat until form is handled
        setInputDisabled(true);

        // Check if we are on the English or Arabic page from the URL
        const isEnglish = window.location.pathname.includes('/chat-en');

        // Set texts based on the page language
        const welcomeText = isEnglish ? '👋 Welcome!' : '👋 أهلاً بك!';
        const instructionText = isEnglish 
            ? 'To help you better, please provide your details to start.' 
            : 'عشان نقدر نساعدك أحسن، يرجى إدخال بياناتك للبدء.';
        const btnText = isEnglish ? 'Start' : 'ابدأ';
        const alignText = isEnglish ? 'left' : 'right';

        // Dropdown Labels & Options
        const regLabelText = isEnglish ? 'Are you registered with us?' : 'هل أنت مسجل لدينا؟';
        const cityLabelText = isEnglish ? 'Select your city' : 'اختر مدينتك';
        const selectPlaceholder = isEnglish ? '-- Select --' : '-- اختر --';
        const yesText = isEnglish ? 'Yes' : 'نعم';
        const noText = isEnglish ? 'No' : 'لا';

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
            
            <div style="margin-bottom:12px;">
                <label style="font-size:0.85rem; color:#444; margin-bottom:4px; display:block; font-weight:700;">${regLabelText}</label>
                <select id="registeredSelect" style="width:100%; padding:10px; border:2px solid #008537; border-radius:12px; background-color:#e8f5e9; color:#008537; font-weight:bold; font-family:inherit; font-size:0.9rem; outline:none; cursor:pointer;">
                    <option value="" disabled selected>${selectPlaceholder}</option>
                    <option value="yes">${yesText}</option>
                    <option value="no">${noText}</option>
                </select>
            </div>

            <div style="margin-bottom:14px;">
                <label style="font-size:0.85rem; color:#444; margin-bottom:4px; display:block; font-weight:600;">${cityLabelText}</label>
                <select id="citySelect" style="width:100%; padding:9px 14px; border:1px solid #ced4da; border-radius:12px; font-family:inherit; font-size:0.9rem; outline:none; cursor:pointer;">
                    <option value="Riyadh">الرياض - Riyadh</option>
                    <option value="Jeddah">جدة - Jeddah</option>
                    <option value="Makkah">مكة المكرمة - Makkah</option>
                    <option value="Madinah">المدينة المنورة - Madinah</option>
                    <option value="Dammam">الدمام - Dammam</option>
                    <option value="Khobar">الخبر - Khobar</option>
                    <option value="Dhahran">الظهران - Dhahran</option>
                    <option value="Ahsa">الأحساء - Ahsa</option>
                    <option value="Taif">الطائف - Taif</option>
                    <option value="Abha">أبها - Abha</option>
                    <option value="Khamis Mushait">خميس مشيط - Khamis Mushait</option>
                    <option value="Buraidah">بريدة - Buraidah</option>
                    <option value="Unaizah">عنيزة - Unaizah</option>
                    <option value="Tabuk">تبوك - Tabuk</option>
                    <option value="Hail">حائل - Hail</option>
                    <option value="Jazan">جازان - Jazan</option>
                    <option value="Najran">نجران - Najran</option>
                    <option value="Al Bahah">الباحة - Al Bahah</option>
                    <option value="Sakaka">سكاكا - Sakaka</option>
                    <option value="Arar">عرعر - Arar</option>
                    <option value="Yanbu">ينبع - Yanbu</option>
                    <option value="Jubail">الجبيل - Jubail</option>
                    <option value="Al Khari">الخرج - Al Kharj</option>
                    <option value="Qatif">القطيف - Qatif</option>
                    <option value="Hafar Al-Batin">حفر الباطن - Hafar Al-Batin</option>
                    <option value="Other">أخرى - Other</option>
                </select>
            </div>

            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; direction: ltr;">
                <input
                    id="phoneInput"
                    type="tel"
                    placeholder="05xxxxxxxx"
                    maxlength="10"
                    style="flex:1; min-width:130px; padding:9px 14px; border:1px solid #ced4da; border-radius:25px; font-family:inherit; font-size:0.9rem; outline:none; text-align: left;">
                <button
                    id="phoneSubmitBtn"
                    style="background:#008537; color:white; border:none; padding:9px 18px; border-radius:25px; cursor:pointer; font-weight:700; font-size:0.9rem; white-space:nowrap;">
                    ${btnText}
                </button>
            </div>
        `;

        chatBox.insertBefore(formDiv, typingIndicator);
        scrollToBottom();

        // Submit handlers
        document.getElementById('phoneSubmitBtn').addEventListener('click', handlePhoneSubmit);
        document.getElementById('phoneInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handlePhoneSubmit();
        });
    }

    function handlePhoneSubmit() {
        const phoneInput = document.getElementById('phoneInput');
        const regSelect = document.getElementById('registeredSelect');
        const citySelect = document.getElementById('citySelect');

        const phone = phoneInput?.value.trim();
        const isRegistered = regSelect?.value;
        const city = citySelect?.value;

        let isValid = true;

        // Validate Registration Dropdown
        if (!isRegistered) {
            regSelect.style.borderColor = '#dc3545';
            isValid = false;
        } else {
            regSelect.style.borderColor = '#008537'; // Keep special border color
        }

        // Validate City Dropdown
        if (!city) {
            citySelect.style.borderColor = '#dc3545';
            isValid = false;
        } else {
            citySelect.style.borderColor = '#ced4da';
        }

        // Validate Phone Number
        if (!phone || phone.length < 9) {
            phoneInput.style.borderColor = '#dc3545';
            isValid = false;
        } else {
            phoneInput.style.borderColor = '#ced4da';
        }

        if (!isValid) return; // Stop if validation fails

        // Save data to leadData
        leadData.phone_number = phone;
        leadData.is_registered = isRegistered; 
        leadData.city = city;

        removePhoneForm();
        submitLead();
        addBotGreeting(phone);
        setInputDisabled(false);
        userInput.focus();
    }

    function removePhoneForm() {
        document.getElementById('phoneFormWrapper')?.remove();
    }

    function addBotGreeting(phone) {
        // Check page language again
        const isEnglish = window.location.pathname.includes('/chat-en');
        const div = createMessageElement('bot');

        // Set message based on language
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
            
            // Check language for error message
            const isEnglish = window.location.pathname.includes('/chat-en');
            errorDiv.textContent = isEnglish ? "Sorry, a connection error occurred." : "عذراً، حدث خطأ في الاتصال.";
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
    // Init - show phone form first, then let user chat
    // ---------------------------------------------------------------------------
    showPhoneForm();

});