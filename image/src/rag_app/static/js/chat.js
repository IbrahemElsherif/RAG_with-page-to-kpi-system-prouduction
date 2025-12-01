// ==========================================
// تعريف العناصر (مع حماية ضد العدم null)
// ==========================================
const chatBox = document.getElementById('chatBox');
const userInput = document.getElementById('userInput');

// محاولة العثور على الزر سواء بالـ ID أو بالكلاس كاحتياط
const sendBtn = document.getElementById('sendBtn') || document.querySelector('button.btn-primary');

let chatHistory = []; 

// ==========================================
// إعدادات DOMPurify (لفتح الروابط وحمايتها)
// ==========================================
if (typeof DOMPurify !== 'undefined') {
    DOMPurify.addHook('afterSanitizeAttributes', function (node) {
        // التحقق من أن العنصر هو رابط
        if (node.tagName && node.tagName.toLowerCase() === 'a') {
            let href = node.getAttribute('href') || '';

            // إذا الرابط فارغ، نلغي فعاليته
            if (!href) {
                node.setAttribute('href', 'javascript:void(0)');
                node.style.pointerEvents = 'none'; // منع النقر
                node.style.color = '#6c757d'; // لون رمادي
                node.style.textDecoration = 'none';
                return;
            }

            // إضافة https إذا لم يكن موجوداً (للروابط الخارجية)
            if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href)) {
                if (!href.startsWith('/') && !href.startsWith('#')) {
                    href = 'https://' + href;
                    node.setAttribute('href', href);
                }
            }

            // فتح في نافذة جديدة دائماً
            node.setAttribute('target', '_blank');
            node.setAttribute('rel', 'noopener noreferrer');

            // تنسيق الرابط ليظهر بوضوح
            node.style.color = "#0056b3";
            node.style.fontWeight = "bold";
            node.style.textDecoration = "underline";
        }
    });
} else {
    console.warn("تنبيه: مكتبة DOMPurify غير محملة، الروابط قد لا تعمل بشكل آمن.");
}

// ==========================================
// التعامل مع زر Enter
// ==========================================
if (userInput) {
    userInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); 
            sendMessage();
        }
    });
}

// ==========================================
// دالة إرسال الرسالة (الأساسية)
// ==========================================
async function sendMessage() {
    // 1. التحقق من وجود نص
    if (!userInput) return; // حماية إضافية
    const text = userInput.value.trim();
    if (!text) return;

    // 2. تعطيل الواجهة (بشكل آمن)
    if (userInput) userInput.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    // 3. عرض رسالة المستخدم فوراً
    appendMessage(text, 'user-message');
    userInput.value = '';
    userInput.style.height = 'auto'; 

    // 4. إنشاء عنصر الرد (Placeholder)
    const botMsgDiv = document.createElement('div');
    botMsgDiv.className = 'message bot-message';
    botMsgDiv.innerHTML = '<span class="typing-indicator">جاري الكتابة... ⏳</span>';
    chatBox.appendChild(botMsgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, history: chatHistory })
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        
        botMsgDiv.innerHTML = ""; // مسح مؤشر الكتابة
        let fullBotResponse = "";

        // قراءة الستريم (Stream)
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            fullBotResponse += chunk;

            // تحويل الماركداون (Markdown) وتنظيف الـ HTML
            if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                // نستخدم marked.parse إذا كانت دالة، وإلا قد تكون marked() حسب الإصدار
                const rawHTML = typeof marked.parse === 'function' ? marked.parse(fullBotResponse) : marked(fullBotResponse);
                botMsgDiv.innerHTML = DOMPurify.sanitize(rawHTML);
            } else {
                botMsgDiv.innerText = fullBotResponse; // fallback
            }
            
            // السكرول التلقائي للأسفل
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        // تحديث سجل المحادثة
        chatHistory.push([text, fullBotResponse]);

    } catch (error) {
        console.error("Chat Error:", error);
        botMsgDiv.innerText = "عذراً، حدث خطأ في الاتصال بالسيرفر.";
        botMsgDiv.style.color = "red";
    } finally {
        // 5. إعادة تفعيل الواجهة (بشكل آمن)
        if (userInput) {
            userInput.disabled = false;
            userInput.focus(); // إعادة المؤشر للكتابة
        }
        if (sendBtn) {
            sendBtn.disabled = false;
        }
    }
}

// ==========================================
// دالة مساعدة لإضافة الرسائل
// ==========================================
function appendMessage(text, className) {
    const div = document.createElement('div');
    div.className = `message ${className}`;
    // نستخدم innerText لرسائل المستخدم للحماية من XSS
    div.innerText = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}