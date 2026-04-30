from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from chromadb.config import Settings

from sqlalchemy.orm import Session
from sqlalchemy import func
import io
from database import engine, SessionLocal, get_db
import models

from pydantic import BaseModel
from datetime import datetime
from typing import List, Tuple, Optional
from pathlib import Path
import asyncio
import time
import shutil
import zipfile
import secrets
import hashlib
import csv
import warnings
import logging
import os


# ---------------------------------------------------------------------------
# Suppress noisy logs
# ---------------------------------------------------------------------------
warnings.filterwarnings("ignore", message=".*Failed to send telemetry event.*")
warnings.filterwarnings("ignore", message=".*telemetry.*")
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Static branch data
# ---------------------------------------------------------------------------
GLOBAL_FACTS = """
1. **الرياض:**
   - حي الحمراء: https://maps.app.goo.gl/GyV2WBj9qdr19Gnw8
   - حي الاندلس: https://maps.app.goo.gl/zYZSZdgyJnN3Ni3p7?g_st=awb
   - حي ظهرة لبن: https://maps.app.goo.gl/YosPLMqJuDKPC3oM8

2. **الدمام:**
   - حي الزهور: https://maps.app.goo.gl/peEN6jUXJCBeoPsVA
   - حي الشاطئ الغربي: https://maps.app.goo.gl/C1fMA4iDmKBQLzde9

3. **خميس مشيط:**
   - حي الظرفة: https://maps.app.goo.gl/mp5jKJDvZmCo3fN58
   - حي الضيافة: https://maps.app.goo.gl/2bPMoWxnCezzBTRn7

4. **المدينة المنورة:**
   - حي الحرة الغربية: https://maps.app.goo.gl/UKXdWt55fL3VdJzR8

5. **حفر الباطن:**
   - حي المصيف: https://maps.app.goo.gl/2irsjbweCJT5axWJ8
   - حي الواحه: https://maps.app.goo.gl/F1ji25q1GAxGU6Vd9

6. **سكاكا الجوف:**
   - حي العزيزية: https://maps.app.goo.gl/hK8Ye5R21ynr27tc7

ملاحظة مهمة: لا يوجد أي فروع أخرى غير الفروع المدرجة أعلاه.

---

1. **Riyadh:**
* Al Hamra District: https://maps.app.goo.gl/GyV2WBj9qdr19Gnw8
* Al Andalus District: https://maps.app.goo.gl/zYZSZdgyJnN3Ni3p7?g_st=awb
* Dhahrat Laban District: https://maps.app.goo.gl/YosPLMqJuDKPC3oM8

2. **Dammam:**
* Az Zuhur District: https://maps.app.goo.gl/peEN6jUXJCBeoPsVA
* Ash Shati Al Gharbi District: https://maps.app.goo.gl/C1fMA4iDmKBQLzde9

3. **Khamis Mushait:**
* Al Tharfah District: https://maps.app.goo.gl/mp5jKJDvZmCo3fN58
* Al Diyafa District: https://maps.app.goo.gl/2bPMoWxnCezzBTRn7

4. **Madinah:**
* Al Harrah Al Gharbiyah District: https://maps.app.goo.gl/UKXdWt55fL3VdJzR8

5. **Hafar Al-Batin:**
* Al Masif District: https://maps.app.goo.gl/2irsjbweCJT5axWJ8
* Al Wahah District: https://maps.app.goo.gl/F1ji25q1GAxGU6Vd9

6. **Sakaka Al-Jouf:**
* Al Aziziyah District: https://maps.app.goo.gl/hK8Ye5R21ynr27tc7

Important Note: There are no other branches other than the branches listed above.
"""

load_dotenv()

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")


# ---------------------------------------------------------------------------
# Background task: classify question category with GPT
# ---------------------------------------------------------------------------
async def classify_question_background(log_id: int, question: str):
    db = SessionLocal()
    try:
        categories = db.query(models.QuestionCategory).all()
        
        # --- Step 1: Classify category ---
        category = "other"
        if categories:
            categories_list = "\n".join([
                f"- {c.name}: {c.description}" for c in categories
            ])
            cat_prompt = f"""
You are a question classifier for a Saudi training institute chatbot.
Classify the following question into one of these categories:

{categories_list}
- other: does not fit any category above

Question: "{question}"

Reply with ONLY the category name in Arabic exactly as written above, or "other".
No explanation, no punctuation, just the category name ,dont take any greetings as a category.
"""
            cat_response = await llm.ainvoke(cat_prompt)
            category = cat_response.content.strip()
            valid_names = [c.name for c in categories] + ["other"]
            if category not in valid_names:
                category = "other"

        # --- Step 2: Assign topic (smart clustering) ---
        existing_topics = (
            db.query(models.ChatLog.topic)
            .filter(models.ChatLog.topic != None)
            .distinct()
            .all()
        )
        topics_list = [t[0] for t in existing_topics if t[0]]

        if topics_list:
            topics_str = "\n".join([f"- {t}" for t in topics_list])
            topic_prompt = f"""
You are a question topic classifier for a Saudi training institute chatbot.
These are the existing topics:
{topics_str}

New question: "{question}"

Rules:
1. If this question is similar to an existing topic, return that EXACT topic name.
2. If it's a new topic, create a short Arabic topic name (max 4 words).
3. Return ONLY the topic name, nothing else.
"""
        else:
            topic_prompt = f"""
Create a short Arabic topic name (max 4 words) for this question:
"{question}"

Return ONLY the topic name, nothing else.
"""
        topic_response = await llm.ainvoke(topic_prompt)
        topic = topic_response.content.strip()

        # --- Save to DB ---
        log = db.query(models.ChatLog).filter(models.ChatLog.id == log_id).first()
        if log:
            log.category = category
            log.topic    = topic
            db.commit()
            print(f"--- [CLASSIFY] '{question[:30]}' → category:{category} topic:{topic} ---")

    except Exception as e:
        print(f"--- [ERROR] Classification failed: {e} ---")
    finally:
        db.close()
# ---------------------------------------------------------------------------
# DB table creation (runs on startup)
# ---------------------------------------------------------------------------
models.Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

CHROMA_PATH_ENV = os.getenv("CHROMA_PATH")

if CHROMA_PATH_ENV:
    CHROMA_PATH = Path(CHROMA_PATH_ENV)
    if not os.path.exists(CHROMA_PATH) or (
        os.path.isdir(CHROMA_PATH) and not any(CHROMA_PATH.iterdir())
    ):
        LOCAL_DATA_PATH = BASE_DIR / "data" / "chroma_db"
        if os.path.exists(LOCAL_DATA_PATH) and any(LOCAL_DATA_PATH.iterdir()):
            CHROMA_PATH = LOCAL_DATA_PATH
            print(f"--- [CHROMA INFO] Persistent volume empty, using local data at: {CHROMA_PATH} ---")
        else:
            print(f"--- [CHROMA INFO] Using Environment Path at: {CHROMA_PATH} (will be created if needed) ---")
    else:
        print(f"--- [CHROMA INFO] Using Environment Path at: {CHROMA_PATH} ---")
else:
    CHROMA_PATH = BASE_DIR / "data" / "chroma_db"
    print(f"--- [CHROMA INFO] Using Local Directory at: {CHROMA_PATH} ---")

COLLECTION_NAME = "example_collection"
MAINTENANCE_MODE = False

security = HTTPBasic()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="RAG API Final System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

print("--- [INFO] Loading models... ---")
embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(temperature=0.1, model="gpt-4o-mini")
vector_store = None
#---------------------------------------------------------------------------
#
#---------------------------------------------------------------------------
import json

async def detect_intent_background(session_id: str, message: str):
    db = SessionLocal()
    try:
        # 1. التحقق المبكر لتوفير التكلفة
        lead = db.query(models.Lead).filter(models.Lead.session_id == session_id).first()
        if not lead:
            return  
            
        # إذا سأل عن الاثنين مسبقاً، لا داعي للاتصال بـ GPT نهائياً
        if lead.asked_about_price and lead.asked_about_registration:
            return

        # 2. جلب **جميع أسئلة العميل فقط** في هذه الجلسة (بدون ردود البوت)
        all_user_logs = (
            db.query(models.ChatLog.user_query)
            .filter(models.ChatLog.session_id == session_id)
            .order_by(models.ChatLog.timestamp.asc())
            .all()
        )
        
        if not all_user_logs:
            return

        # تجميع أسئلة العميل في نص واحد
        user_questions_text = "\n".join([f"- {log[0]}" for log in all_user_logs if log[0]])

        # 3. توجيه النموذج لتحليل القائمة
        intent_prompt = f"""
You are a strict sales intent classifier for a Saudi training institute.
Below are ALL the messages sent by a single user in a chat session.

User Messages:
{user_questions_text}

RULES:
- Be conservative. Only mark True if the evidence is CLEAR and EXPLICIT.
- When in doubt → false.
- Ignore greetings, general questions about courses/content, and location questions.

[CONCEPT 1]: PRICE INTENT
True ONLY if the user explicitly asks about cost, price, fees, payment, or discounts.
True examples: "بكم"، "كم التكلفة"، "عندكم خصم"، "كم ادفع"، "الرسوم كم"، "how much"، "price"
False examples: "وين الفرع"، "ما هي الدورات"، "متى يبدأ"، "كم مدة الدورة"، "ما تخصصاتكم"

[CONCEPT 2]: REGISTRATION INTENT
True ONLY if the user explicitly asks about registering, applying, joining, or enrollment steps.
True examples: "كيف اسجل"، "وش الشروط"، "ابي انضم"، "رابط التسجيل"، "كيف القبول"، "how to apply"
False examples: "عندكم دبلوم"، "ما هي الدورات"، "كم مدة الدورة"

Respond ONLY with valid JSON, no explanation:
{{
    "price_intent": true or false,
    "registration_intent": true or false
}}
"""
        # 4. إرسال الطلب للنموذج
        intent_response = await llm.ainvoke(intent_prompt)
        response_text = intent_response.content.strip()
        
        # تنظيف الرد
        if response_text.startswith("```json"):
            response_text = response_text[7:-3].strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:-3].strip()
            
        # 5. استخراج البيانات (Parsing)
        parsed_intent = json.loads(response_text)
        touched_price = parsed_intent.get("price_intent", False)
        touched_reg = parsed_intent.get("registration_intent", False)
        

        # 6. تحديث قاعدة البيانات إذا وجدنا نية جديدة
        updated = False
        if touched_price and not lead.asked_about_price:
            lead.asked_about_price = True
            updated = True
        if touched_reg and not lead.asked_about_registration:
            lead.asked_about_registration = True
            updated = True
            
        if updated:
            lead.lead_status = _compute_lead_status(
                lead.question_count, lead.asked_about_price, lead.asked_about_registration
            )
            db.commit()

    except json.JSONDecodeError as e:
        print(f"--- [ERROR] Intent parsing failed (Invalid JSON): {e} ---")
    except Exception as e:
        print(f"--- [ERROR] Intent detection failed: {e} ---")
    finally:
        db.close()
async def generate_session_summary_background(session_id: str):
    db = SessionLocal()
    try:
        # التأكد من وجود العميل أولاً
        lead = db.query(models.Lead).filter(models.Lead.session_id == session_id).first()
        if not lead:
            return  
            
        # جلب جميع أسئلة العميل في الجلسة
        all_user_logs = (
            db.query(models.ChatLog.user_query)
            .filter(models.ChatLog.session_id == session_id)
            .order_by(models.ChatLog.timestamp.asc())
            .all()
        )
        
        if not all_user_logs:
            return

        # تجميع الأسئلة في نص واحد
        user_questions_text = "\n".join([f"- {log[0]}" for log in all_user_logs if log[0]])

        # توجيه النموذج لعمل ملخص فقط وبدون JSON
        summary_prompt = f"""
You are an expert sales analyst for a Saudi Institute. 
Analyze the following user questions from a single session and write a brief summary.

User Questions:
{user_questions_text}

Task: Create a very short Arabic summary of what the user is looking for (maximum 10 words).
Example: "اهتمام بدبلوم القانون وفروع الرياض"
Example: "استفسار عن دبلوم البرمجة وطريقة التسجيل"

Respond ONLY with the Arabic summary text, nothing else. No formatting, no markdown.
"""
        # إرسال الطلب
        summary_response = await llm.ainvoke(summary_prompt)
        summary_text = summary_response.content.strip()

        # تحديث قاعدة البيانات
        lead.session_summary = summary_text
        db.commit()
        
        print(f"--- [DEBUG] SESSION SUMMARY UPDATED: {summary_text} ---")

    except Exception as e:
        print(f"--- [ERROR] Summary generation failed: {e} ---")
    finally:
        db.close()
# ---------------------------------------------------------------------------
# Vector store helpers
# ---------------------------------------------------------------------------
def load_vector_store():
    global vector_store
    if os.path.exists(CHROMA_PATH):
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings_model,
            persist_directory=str(CHROMA_PATH),
            client_settings=Settings(anonymized_telemetry=False),
        )
        print("--- [INFO] Vector store loaded. ---")
    else:
        print("--- [WARNING] ChromaDB folder not found. Please upload DB via admin panel. ---")


load_vector_store()


def reload_vector_store():
    print("--- [INFO] Reloading Vector Store... ---")
    load_vector_store()


def get_chroma_stats():
    if vector_store:
        try:
            count = vector_store._collection.count()
            return {"status": "Connected", "total_documents": count}
        except:
            pass
    return {"status": "Not Loaded", "total_documents": 0}


# ---------------------------------------------------------------------------
# Admin auth (existing HTTPBasic for /admin/* routes)
# ---------------------------------------------------------------------------
def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---------------------------------------------------------------------------
# Dashboard session auth helpers
# Uses a simple signed cookie: "username|role" hashed with a server secret
# ---------------------------------------------------------------------------
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "change-me-in-production")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _make_session_token(username: str, role: str) -> str:
    payload = f"{username}|{role}"
    sig = hashlib.sha256(f"{payload}{DASHBOARD_SECRET}".encode()).hexdigest()
    return f"{payload}|{sig}"


def _verify_session_token(token: str):
    """Returns (username, role) or raises HTTPException."""
    try:
        parts = token.split("|")
        username, role, sig = parts[0], parts[1], parts[2]
        expected = hashlib.sha256(f"{username}|{role}{DASHBOARD_SECRET}".encode()).hexdigest()
        if not secrets.compare_digest(sig, expected):
            raise ValueError("bad signature")
        return username, role
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")


def get_dashboard_user(request: Request):
    token = request.cookies.get("dashboard_session")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/dashboard/login"})
    return _verify_session_token(token)


def get_trackdashboard_user(request: Request):
    """Only admin role can access trackdashboard."""
    token = request.cookies.get("dashboard_session")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/dashboard/login"})
    username, role = _verify_session_token(token)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return username, role


# ---------------------------------------------------------------------------
# Lead scoring helper
# ---------------------------------------------------------------------------
_MONTHS_AR = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
_WEEK_ORDINALS_AR = ["الأول","الثاني","الثالث","الرابع","الخامس"]

def _week_label(year: int, week_num: int) -> str:
    from datetime import datetime
    start = datetime.fromisocalendar(year, week_num, 1)
    week_of_month = (start.day - 1) // 7
    return f"الأسبوع {_WEEK_ORDINALS_AR[week_of_month]} من {_MONTHS_AR[start.month - 1]}"

def _compute_lead_status(question_count: int, asked_price: bool, asked_reg: bool) -> str:
    if asked_price or asked_reg:
        return "hot"
    if question_count >= 5:
        return "warm"
    return "cold"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Tuple[str, str]]] = []
    session_id: str = "unknown"


class LeadSubmitRequest(BaseModel):
    session_id: str
    phone_number: str
    question_count: int = 0
    asked_about_price: bool = False
    is_registered: Optional[str] = None
    city: Optional[str] = None


class LeadUpdateRequest(BaseModel):
    admin_note: Optional[str] = None
    lead_status: Optional[str] = None


# ---------------------------------------------------------------------------
# RAG logic (unchanged)
# ---------------------------------------------------------------------------
def prepare_rag_context(message: str, history: List[Tuple[str, str]]):
    if not vector_store:
        return None, message, [], history

    MEMORY_WINDOW_SIZE = 3
    SIMILARITY_THRESHOLD = 1.5
    TOP_K_RESULTS = 5

    limited_history = history[-MEMORY_WINDOW_SIZE:]

    formatted_history_text = ""
    if limited_history:
        formatted_history_text = "\n".join(
            [f"User: {u}\nAssistant: {a}" for u, a in limited_history]
        )

    search_query = message

    if history:
        rephrase_prompt = f"""
You are an expert at understanding conversation context.
You have a previous conversation and a new user message.

Conversation history:
{formatted_history_text}

Latest user message: {message}

Task:
- If the user reply is an answer to an assistant question, infer the next logical step and use that as the search query.
- If it is a new question, rephrase it clearly.
- IMPORTANT: Keep the search query in the SAME language as the user message.

Output only the improved search query with no preamble:
"""
        try:
            search_query = llm.invoke(rephrase_prompt).content.strip()
            print(f"--- [DEBUG] Smart Search Query: {search_query} ---")
        except Exception as e:
            print(f"--- [ERROR] Rephrase failed: {e} ---")
            search_query = message

    results = vector_store.similarity_search_with_score(search_query, k=TOP_K_RESULTS)
    good_docs = [doc.page_content for doc, score in results if score < SIMILARITY_THRESHOLD]
    knowledge = "\n\n".join(good_docs)
    print(f"--- [DEBUG] Found {len(good_docs)} relevant documents ---")
    

    rag_prompt = f"""
    You are a smart assistant for the Saudi Specialized Higher Institute for Training.
    You answer questions from website visitors.

    === GLOBAL FACTS ===
    {GLOBAL_FACTS}

    === RETRIEVED CONTEXT ===
    {knowledge}

    === CONVERSATION HISTORY ===
    {formatted_history_text}


    === GUIDELINES ===
    1. CRITICAL: Detect the language of the User message: "{message}". 
    You MUST reply in that exact language — if English, reply in English only.
    If Arabic, reply in Arabic only. Never mix languages.
    2. If asked about a city not in the list, apologize and mention available branches.
    3. For pricing or registration questions, share: unified number 920012673 and WhatsApp 0562510671.
    4. Be direct and concise.

    User: {message}
    Assistant:
    """


    return rag_prompt, search_query, good_docs, limited_history


async def generate_response_stream(
    message: str, history: List[Tuple[str, str]], session_id: str, db: Session
):
    start_time = time.time()

    rag_prompt, search_query, docs, _ = prepare_rag_context(message, history)

    full_answer = ""
    first_token_time = None
    is_unanswered = False

    if not rag_prompt:
        err_msg = "Sorry, the knowledge base is not ready yet."
        yield err_msg
        full_answer = err_msg
        response_time_to_log = time.time() - start_time
    else:
        try:
            async for chunk in llm.astream(rag_prompt):
                if chunk.content:
                    if first_token_time is None:
                        first_token_time = time.time() - start_time
                    full_answer += chunk.content
                    yield chunk.content

            response_time_to_log = (
                first_token_time if first_token_time is not None else (time.time() - start_time)
            )

            # Detect unanswered questions from bot response
            unanswered_phrases = [
                "عذراً", "عذرا", "لا أملك", "لا يوجد لدي",
                "لا تتوفر", "لا أعرف", "غير متاح", "لا يوجد",
                "sorry", "i don't have", "i do not have"
            ]
            is_unanswered = any(
                phrase in full_answer.lower()
                for phrase in unanswered_phrases
            )

        except Exception as e:
            yield f"Error: {str(e)}"
            response_time_to_log = time.time() - start_time

    # Update question count only — no intent analysis here
    try:
        lead = db.query(models.Lead).filter(
            models.Lead.session_id == session_id
        ).first()
        if lead:
            lead.question_count += 1
            lead.lead_status = _compute_lead_status(
                lead.question_count,
                lead.asked_about_price,
                lead.asked_about_registration
            )
            db.commit()
    except Exception as e:
        print(f"--- [ERROR] Lead update failed: {e} ---")

    # Save chat log
    try:
        new_log = models.ChatLog(
            session_id=session_id,
            user_query=message,
            bot_answer=full_answer,
            response_time=response_time_to_log,
            timestamp=datetime.now(),
            is_unanswered=is_unanswered,
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        print(f"RAG_EVAL_START", flush=True)
        print(f"RAG_EVAL | Question: {message}", flush=True)
        print(f"RAG_EVAL | Context: {docs}", flush=True)
        print(f"RAG_EVAL | Answer: {full_answer}", flush=True)
        print(f"RAG_EVAL_END", flush=True)
        print(f"--- [LOG] Response Time Saved: {response_time_to_log:.2f}s ---")
        asyncio.create_task(classify_question_background(new_log.id, message))
        asyncio.create_task(detect_intent_background(session_id, message))
        asyncio.create_task(generate_session_summary_background(session_id))

    except Exception as e:
        print(f"--- [ERROR] DB Save failed: {e} ---")
#===================================================
# to get all unanswered questions for the current week
#ُ=====================================================
@app.get("/api/unanswered-questions")
async def get_unanswered_questions(
    request: Request,
    week: int = None,
    year: int = None,
    db: Session = Depends(get_db),
):
    get_dashboard_user(request)

    from datetime import date
    from collections import Counter

    if not week: week = date.today().isocalendar()[1]
    if not year: year = date.today().year

    all_unanswered = db.query(models.ChatLog).filter(
        models.ChatLog.is_unanswered == True
    ).all()

    week_unanswered = [
        log for log in all_unanswered
        if log.timestamp.isocalendar()[1] == week
        and log.timestamp.year == year
    ]

    counter = Counter(log.user_query for log in week_unanswered)

    return [
        {"query": q, "count": c}
        for q, c in counter.most_common(20)
    ]


# ===========================================================================
# EXISTING ROUTES (unchanged)
# ===========================================================================

@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    if MAINTENANCE_MODE:
        return templates.TemplateResponse("user_maintenance.html", {"request": request})
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/chat-en", response_class=HTMLResponse)
async def chat_page_en(request: Request):
    if MAINTENANCE_MODE:
        return templates.TemplateResponse("user_maintenance_en.html", {"request": request})
    return templates.TemplateResponse("chat_en.html", {"request": request})


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    if MAINTENANCE_MODE:
        async def msg():
            yield "Sorry, the system is under maintenance. Please refresh the page."
        return StreamingResponse(msg(), media_type="text/plain")

    return StreamingResponse(
        generate_response_stream(request.message, request.history, request.session_id, db),
        media_type="text/plain",
    )


@app.get("/admin/maintenance", response_class=HTMLResponse)
def maintenance_page(request: Request, username: str = Depends(get_current_admin)):
    stats = get_chroma_stats()
    return templates.TemplateResponse(
        "maintenance.html",
        {"request": request, "is_maintenance": MAINTENANCE_MODE, "db_stats": stats},
    )


@app.post("/admin/toggle-maintenance")
async def toggle_maintenance(request: Request, username: str = Depends(get_current_admin)):
    global MAINTENANCE_MODE
    form_data = await request.form()
    state = form_data.get("state")
    if state == "on":
        MAINTENANCE_MODE = True
    elif state == "off":
        MAINTENANCE_MODE = False

    stats = get_chroma_stats()
    return templates.TemplateResponse(
        "maintenance.html",
        {"request": request, "is_maintenance": MAINTENANCE_MODE, "db_stats": stats},
    )


@app.post("/admin/upload-db")
async def upload_db(
    request: Request,
    file: UploadFile = File(...),
    username: str = Depends(get_current_admin),
):
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = True
    try:
        temp_zip = "temp.zip"
        with open(temp_zip, "wb") as b:
            shutil.copyfileobj(file.file, b)

        if os.path.exists(CHROMA_PATH):
            try:
                shutil.rmtree(CHROMA_PATH)
            except:
                pass

        CHROMA_PATH.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(temp_zip, "r") as z:
            z.extractall(CHROMA_PATH.parent)

        os.remove(temp_zip)
        reload_vector_store()

        stats = get_chroma_stats()
        return templates.TemplateResponse(
            "maintenance.html",
            {
                "request": request,
                "is_maintenance": False,
                "db_stats": stats,
                "message": "Knowledge base updated successfully!",
            },
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        MAINTENANCE_MODE = False


@app.get("/admin/kpi", response_class=HTMLResponse)
def kpi_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    logs = (
        db.query(models.ChatLog)
        .order_by(models.ChatLog.timestamp.desc())
        .limit(50)
        .all()
    )

    grouped_sessions = {}
    for log in logs:
        sid = log.session_id or "Anonymous"
        if sid not in grouped_sessions:
            grouped_sessions[sid] = []
        grouped_sessions[sid].append(log)

    total_chats = db.query(models.ChatLog).count()

    avg_speed_all = 0
    avg_speed_last_10 = 0

    if total_chats > 0:
        all_logs = db.query(models.ChatLog.response_time).all()
        all_times = [r[0] for r in all_logs if r[0] is not None]
        if all_times:
            avg_speed_all = sum(all_times) / len(all_times)

        last_10_logs = (
            db.query(models.ChatLog.response_time)
            .order_by(models.ChatLog.timestamp.desc())
            .limit(10)
            .all()
        )
        last_10_times = [r[0] for r in last_10_logs if r[0] is not None]
        if last_10_times:
            avg_speed_last_10 = sum(last_10_times) / len(last_10_times)

    return templates.TemplateResponse(
        "kpi.html",
        {
            "request": request,
            "grouped_sessions": grouped_sessions,
            "logs": logs,
            "total_chats": total_chats,
            "avg_speed_all": round(avg_speed_all, 2),
            "avg_speed_last_10": round(avg_speed_last_10, 2),
            "now": datetime.now(),
        },
    )


@app.get("/admin/kpi/{log_id}", response_class=HTMLResponse)
def view_chat_log(
    log_id: int,
    request: Request,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    log = db.query(models.ChatLog).filter(models.ChatLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return templates.TemplateResponse("chat_details.html", {"request": request, "log": log})


@app.get("/admin/export-csv")
def export_logs_csv(
    db: Session = Depends(get_db), username: str = Depends(get_current_admin)
):
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["ID", "Date", "Time", "User Question", "Bot Answer", "Response Time (s)"])
    for log in logs:
        writer.writerow([
            log.id,
            log.timestamp.strftime("%Y-%m-%d"),
            log.timestamp.strftime("%H:%M:%S"),
            log.user_query,
            log.bot_answer,
            f"{log.response_time:.2f}",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chat_logs_report.csv"},
    )


@app.get("/admin/full-report")
def full_report_page(
    request: Request,
    download: bool = False,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).all()
    context = {"request": request, "logs": logs, "generated_at": datetime.now()}
    if download:
        html_content = templates.get_template("full_report.html").render(context)
        return HTMLResponse(
            content=html_content,
            headers={"Content-Disposition": f"attachment; filename=full_report_{datetime.now().strftime('%Y-%m-%d')}.html"},
        )
    return templates.TemplateResponse("full_report.html", context)


@app.delete("/admin/kpi/delete/{log_id}")
def delete_chat_log(
    log_id: int,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    log = db.query(models.ChatLog).filter(models.ChatLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    db.delete(log)
    db.commit()
    return {"status": "success", "message": f"Log {log_id} deleted"}


@app.get("/admin/db-info")
def db_info_endpoint(username: str = Depends(get_current_admin)):
    return {"maintenance_mode": MAINTENANCE_MODE, "db_stats": get_chroma_stats()}


@app.delete("/admin/kpi/delete-session/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    rows_deleted = (
        db.query(models.ChatLog)
        .filter(models.ChatLog.session_id == session_id)
        .delete()
    )
    db.commit()
    if rows_deleted == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "message": f"Session {session_id} deleted ({rows_deleted} logs)"}


# ===========================================================================
# NEW ROUTE: Lead submission from chat popup
# ===========================================================================

@app.post("/api/lead/submit")
async def submit_lead(payload: LeadSubmitRequest, db: Session = Depends(get_db)):
    """
    Called from chat.js when the user submits their phone number.
    Creates or updates a Lead record for the session.
    Starts as pending (is_approved=False) until admin approves.
    """
    existing = db.query(models.Lead).filter(models.Lead.session_id == payload.session_id).first()
    
    if existing:
        existing.phone_number = payload.phone_number
        existing.question_count = payload.question_count
        
        # Update the new fields if provided in the payload
        if payload.is_registered is not None:
            existing.is_registered = payload.is_registered
        if payload.city is not None:
            existing.city = payload.city
            
        # Don't override asked_about_price/reg - managed by LLM in background
        existing.lead_status = _compute_lead_status(
            payload.question_count, existing.asked_about_price, existing.asked_about_registration
        )
        db.commit()
        return {"status": "updated", "lead_id": existing.id}

    # Create new lead if it doesn't exist
    lead = models.Lead(
        session_id=payload.session_id,
        phone_number=payload.phone_number,
        is_registered=payload.is_registered,  # New field
        city=payload.city,                    # New field
        question_count=payload.question_count,
        asked_about_price=False,
        asked_about_registration=False,
        lead_status=_compute_lead_status(
            payload.question_count, False, False
        ),
        is_approved=False,
    )
    
    db.add(lead)
    db.commit()
    db.refresh(lead)
    
    return {"status": "created", "lead_id": lead.id}


# ===========================================================================
# NEW ROUTES: Dashboard login / logout
# ===========================================================================

@app.get("/dashboard/login", response_class=HTMLResponse)
async def dashboard_login_page(request: Request):
    return templates.TemplateResponse("dashboard_login.html", {"request": request, "error": None})


@app.post("/dashboard/login")
async def dashboard_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    hashed = _hash_password(password)
    user = (
        db.query(models.DashboardUser)
        .filter(
            models.DashboardUser.username == username,
            models.DashboardUser.hashed_password == hashed,
            models.DashboardUser.is_active == True,
        )
        .first()
    )
    if not user:
        return templates.TemplateResponse(
            "dashboard_login.html",
            {"request": request, "error": "Invalid username or password."},
        )

    # Update last login timestamp
    user.last_login = datetime.now()
    db.commit()

    token = _make_session_token(user.username, user.role)
    redirect_url = "/trackdashboard" if user.role == "admin" else "/dashboard"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="dashboard_session",
        value=token,
        httponly=True,
        max_age=60 * 60 * 8,  # 8 hours
        samesite="lax",
    )
    return response


@app.get("/dashboard/logout")
async def dashboard_logout():
    response = RedirectResponse(url="/dashboard/login", status_code=302)
    response.delete_cookie("dashboard_session")
    return response


# ===========================================================================
# NEW ROUTES: /dashboard  (sales team view — approved data only)
# ===========================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def sales_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        username, role = get_dashboard_user(request)
    except HTTPException:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    from datetime import datetime, timedelta
    from collections import Counter

    # Get current date to load the current week on first page visit
    now = datetime.utcnow()
    year = now.year
    week_num = now.isocalendar()[1]

    # Calculate start and end of the current week
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

    # 1. Fetch leads for top stats (current week only)
    week_leads = db.query(models.Lead).filter(
        models.Lead.timestamp >= start_of_week,
        models.Lead.timestamp <= end_of_week
    ).all()

    week_session_count = len(week_leads)
    week_hot = sum(1 for l in week_leads if l.lead_status == "hot")
    week_warm = sum(1 for l in week_leads if l.lead_status == "warm")
    week_maxq = max((l.question_count for l in week_leads), default=0)

    # 2. Fetch all leads for the table (current week only)
    leads = (
        db.query(models.Lead)
        .filter(
            models.Lead.timestamp >= start_of_week,
            models.Lead.timestamp <= end_of_week
        )
        .order_by(models.Lead.timestamp.desc())
        .all()
    )

    # 3. Fetch active weekly note
    weekly_note = (
        db.query(models.WeeklyNote)
        .filter(
            models.WeeklyNote.week_number == week_num,
            models.WeeklyNote.year == year,
            models.WeeklyNote.is_published == True,
        )
        .first()
    )

    # 4. Fetch peak reports
    peak_reports = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "peak_hours",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .all()
    )

    # 5. Fetch visible sections settings
    sections = {
        s.section_key: s.is_visible
        for s in db.query(models.DashboardSection).all()
    }

    # 6. Check if a questions report exists for the current week
    questions_report = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "questions",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year == year,
        )
        .first()
    )

    # 7. Top questions from approved sessions only (current week)
    session_ids = [l.session_id for l in leads]
    top_questions = []
    
    if session_ids:
        week_queries = (
            db.query(models.ChatLog.user_query)
            .filter(
                models.ChatLog.session_id.in_(session_ids),
                models.ChatLog.timestamp >= start_of_week,
                models.ChatLog.timestamp <= end_of_week
            )
            .all()
        )
        
        counter = Counter(q[0] for q in week_queries if q[0])     
        # Format as expected by Jinja template on initial load
        top_questions = [
            type('obj', (object,), {'user_query': q, 'cnt': c})()
            for q, c in counter.most_common()
        ]
    # Leads report for current week
    leads_report = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "leads",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .order_by(models.UploadedReport.uploaded_at.desc())
        .first()
    )
    # Repeated visitors reports (all for this week)
    repeated_reports_raw = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "repeated_visitors",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .order_by(models.UploadedReport.uploaded_at.desc())
        .all()
    )
    # Render template with initial data
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request":             request,
            "username":            username,
            "leads":               leads,
            "weekly_note":         weekly_note,
            "sections":            sections,
            "top_questions":       top_questions,
            "week_num":            week_num,
            "year_num":            year,
            "week_label":          _week_label(year, week_num),
            "week_session_count":  week_session_count,
            "has_questions_report": questions_report is not None,
            "week_hot":  week_hot,
            "week_warm": week_warm,
            "week_maxq": week_maxq,

            "peak_reports": [
                {
                    "id":           r.id,
                    "period_label": r.period_label,
                    "uploaded_at":  r.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                }
                for r in peak_reports
            ],
            "leads_report": leads_report,
            "repeated_reports": [
                {
                    "id":           r.id,
                    "period_label": r.period_label or f"أسبوع {week_num} / {year}",
                    "uploaded_at":  r.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                }
                for r in repeated_reports_raw
            ],
        }
    )
# ===========================================================================
# NEW ROUTES: /trackdashboard  (admin control panel)
# ===========================================================================

@app.get("/trackdashboard", response_class=HTMLResponse)
async def track_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        username, role = get_trackdashboard_user(request)
    except HTTPException:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    # All leads (pending + approved)
    leads = db.query(models.Lead).order_by(models.Lead.timestamp.desc()).all()

    # Dashboard users
    users = db.query(models.DashboardUser).order_by(models.DashboardUser.created_at.desc()).all()

    # Sections
    sections = db.query(models.DashboardSection).all()

    # Weekly notes
    from datetime import date
    week_num = date.today().isocalendar()[1]
    year = date.today().year
    weekly_note = (
        db.query(models.WeeklyNote)
        .filter(
            models.WeeklyNote.week_number == week_num,
            models.WeeklyNote.year == year,
        )
        .first()
    )

    # Stats summary
    total_leads = db.query(models.Lead).count()
    hot_leads = db.query(models.Lead).filter(models.Lead.lead_status == "hot").count()

    return templates.TemplateResponse(
        "trackdashboard.html",
        {
            "request": request,
            "username": username,
            "leads": leads,
            "users": users,
            "sections": sections,
            "weekly_note": weekly_note,
            "week_num": week_num,
            "total_leads": total_leads,
            "hot_leads": hot_leads,
            "now": datetime.now(),
        },
    )


# ---------------------------------------------------------------------------
# trackdashboard: reject a lead
# ---------------------------------------------------------------------------

@app.post("/trackdashboard/leads/{lead_id}/reject")
async def reject_lead(lead_id: int, request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()
    return {"status": "rejected", "lead_id": lead_id}


@app.patch("/trackdashboard/leads/{lead_id}/note")
async def update_lead_note(
    lead_id: int, payload: LeadUpdateRequest, request: Request, db: Session = Depends(get_db)
):
    get_trackdashboard_user(request)
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if payload.admin_note is not None:
        lead.admin_note = payload.admin_note
    if payload.lead_status is not None:
        lead.lead_status = payload.lead_status
    db.commit()
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# trackdashboard: weekly note
# ---------------------------------------------------------------------------

@app.post("/trackdashboard/weekly-note")
async def save_weekly_note(
    request: Request,
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)
    from datetime import date
    week_num = date.today().isocalendar()[1]
    year = date.today().year

    note = (
        db.query(models.WeeklyNote)
        .filter(models.WeeklyNote.week_number == week_num, models.WeeklyNote.year == year)
        .first()
    )
    if note:
        note.content = content
    else:
        note = models.WeeklyNote(week_number=week_num, year=year, content=content, is_published=False)
        db.add(note)
    db.commit()
    return {"status": "saved"}


@app.post("/trackdashboard/weekly-note/publish")
async def publish_weekly_note(request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    from datetime import date
    week_num = date.today().isocalendar()[1]
    year = date.today().year

    note = (
        db.query(models.WeeklyNote)
        .filter(models.WeeklyNote.week_number == week_num, models.WeeklyNote.year == year)
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="No note found for this week. Save it first.")
    note.is_published = True
    note.published_at = datetime.now()
    db.commit()
    return {"status": "published"}


# ---------------------------------------------------------------------------
# trackdashboard: section visibility toggle
# ---------------------------------------------------------------------------

@app.post("/trackdashboard/sections/{section_key}/toggle")
async def toggle_section(section_key: str, request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    section = (
        db.query(models.DashboardSection)
        .filter(models.DashboardSection.section_key == section_key)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    section.is_visible = not section.is_visible
    section.last_updated = datetime.now()
    db.commit()
    return {"status": "toggled", "is_visible": section.is_visible}


# ---------------------------------------------------------------------------
# trackdashboard: user management
# ---------------------------------------------------------------------------

@app.post("/trackdashboard/users/create")
async def create_dashboard_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(default="sales"),
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)
    existing = db.query(models.DashboardUser).filter(models.DashboardUser.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = models.DashboardUser(
        username=username,
        hashed_password=_hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return {"status": "created", "username": username, "role": role}


@app.post("/trackdashboard/users/{user_id}/toggle")
async def toggle_dashboard_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    user = db.query(models.DashboardUser).filter(models.DashboardUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"status": "toggled", "is_active": user.is_active}


@app.delete("/trackdashboard/users/{user_id}")
async def delete_dashboard_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    user = db.query(models.DashboardUser).filter(models.DashboardUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# trackdashboard: seed default sections on first run
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def seed_default_sections():
    """
    Creates default dashboard sections if they don't exist yet.
    All start hidden (is_visible=False). Admin enables them from trackdashboard.
    """
    db = SessionLocal()
    try:
        default_sections = [
            ("hot_leads", "Hot Leads"),
            ("top_questions", "أكثر الأسئلة"),
            ("unanswered_questions", "أسئلة بلا رد"),
            ("peak_hours", "أوقات الذروة"),
            ("weekly_note", "الملاحظة الأسبوعية"),
            ("repeated_visitors", "الزوار المتكررون"),
        ]
        for key, name in default_sections:
            exists = db.query(models.DashboardSection).filter(
                models.DashboardSection.section_key == key
            ).first()
            if not exists:
                db.add(models.DashboardSection(section_key=key, section_name=name, is_visible=False))
        db.commit()
    finally:
        db.close()
# ---------------------------------------------------------------------------
# Report requests — sales submits, admin sees in trackdashboard
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def run_migrations():
    from sqlalchemy import text
    columns = [
        ("chat_logs",  "is_unanswered", "BOOLEAN DEFAULT 0"),
        ("chat_logs",  "category",  "VARCHAR"),
        ("chat_logs",  "topic",     "VARCHAR"),
        ("leads",      "is_approved", "BOOLEAN DEFAULT 0"),
        ("leads",      "approved_at", "DATETIME"),
        ("leads",      "admin_note",  "TEXT"),
        ("leads",      "session_summary", "TEXT"),

        ("leads",      "is_registered", "VARCHAR"),
        ("leads",      "city", "VARCHAR"),
        ("leads",      "question_count", "INTEGER"),

        ("uploaded_reports", "request_id",    "INTEGER"),
        ("uploaded_reports", "report_period", "VARCHAR"),
        ("uploaded_reports", "period_label",  "VARCHAR"),
        ("weekly_notes",     "published_at",  "DATETIME"),
    
    ]
    with engine.connect() as conn:
        for table, col, col_type in columns:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
                print(f"--- [MIGRATE] ✓ {table}.{col} added ---")
            except Exception as e:
                print(f"--- [MIGRATE] • {table}.{col}: already exists ---")

@app.post("/dashboard/request-report")
async def request_report(
    request: Request,
    report_type: str = Form(...),
    note: str = Form(default=""),
    week_num: int = Form(default=None),   
    year: int = Form(default=None),    
    db: Session = Depends(get_db),
):
    username, role = get_dashboard_user(request)
    from datetime import date
    # Use the week the user is currently viewing
    if not week_num:
        week_num = date.today().isocalendar()[1]
    if not year:
        year = date.today().year

    req = models.ReportRequest(
        requested_by=username,
        report_type=report_type,
        week_number=week_num,
        year=year,
        note=note,
        is_seen=False,
    )
    db.add(req)
    db.commit()
    return {"status": "sent"}


@app.get("/trackdashboard/notifications")
async def get_notifications(request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    unseen = (
        db.query(models.ReportRequest)
        .filter(models.ReportRequest.is_seen == False)
        .order_by(models.ReportRequest.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "requested_by": r.requested_by,
            "report_type": r.report_type,
            "week_number": r.week_number,
            "note": r.note,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in unseen
    ]


@app.post("/trackdashboard/notifications/{req_id}/seen")
async def mark_notification_seen(
    req_id: int, request: Request, db: Session = Depends(get_db)
):
    get_trackdashboard_user(request)
    req = db.query(models.ReportRequest).filter(models.ReportRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    req.is_seen = True
    req.seen_at = datetime.now()
    db.commit()
    return {"status": "seen"}


# ---------------------------------------------------------------------------
# Weekly data — sales navigates between past weeks
# ---------------------------------------------------------------------------

@app.get("/dashboard/week/{week_num}/{year}")
async def get_week_data(
    week_num: int,
    year: int,
    request: Request,
    db: Session = Depends(get_db),
):
    get_dashboard_user(request)
    
    from datetime import datetime, timedelta
    from collections import Counter
    

    # 1. Calculate the exact start and end dates for the requested week
    try:
        start_of_week = datetime.fromisocalendar(year, week_num, 1)
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    except ValueError:
        # Fallback in case of invalid week/year sent from frontend
        return {"error": "Invalid week or year"}

    # 2. Fetch ONLY approved leads for the specific week directly from DB (Much faster)
    week_leads = (
        db.query(models.Lead)
        .filter(
            models.Lead.timestamp >= start_of_week,
            models.Lead.timestamp <= end_of_week
        )
        .all()
    )

    # 3. Get top questions ONLY from the sessions of these approved leads
    session_ids = [l.session_id for l in week_leads]
    top_questions = []
    
    if session_ids:
        # Fetch only the query text to save memory and increase speed
        week_queries = (
            db.query(models.ChatLog.user_query)
            .filter(
                models.ChatLog.session_id.in_(session_ids),
                models.ChatLog.timestamp >= start_of_week,
                models.ChatLog.timestamp <= end_of_week
            )
            .all()
        )
        
        # Count and format the questions
        counter = Counter(q[0] for q in week_queries if q[0])
        top_questions = [
            {"query": q, "count": c}
            for q, c in counter.most_common(25)
        ]

    # 4. Fetch the weekly note
    note = (
        db.query(models.WeeklyNote)
        .filter(
            models.WeeklyNote.week_number == week_num,
            models.WeeklyNote.year == year,
            models.WeeklyNote.is_published == True,
        )
        .first()
    )
    
    # 5. Fetch the peak report
    peak_report = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "peak_hours",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .first()
    )

    # Get hot and warm leads for the table 
    hot_leads_list = [l for l in week_leads if l.lead_status == 'hot']
    warm_leads_list = [l for l in week_leads if l.lead_status == 'warm']
    visible_leads = (hot_leads_list + warm_leads_list)

    # Format the leads for the JSON response
    visible_leads_data = [
        {
            "id": l.id,
            "question_count": l.question_count,
            "status": l.lead_status
        }
        for l in visible_leads
    ]
    leads_report = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "leads",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .order_by(models.UploadedReport.uploaded_at.desc())
        .first()
    )

    # 6. Return the exact JSON structure expected by loadWeek() in Javascript
    return {
        "week_num":      week_num,
        "year":          year,
        "week_label":    _week_label(year, week_num),
        "total_leads":   len(week_leads),
        "hot_leads":     sum(1 for l in week_leads if l.lead_status == "hot"),
        "warm_leads":    sum(1 for l in week_leads if l.lead_status == "warm"),
        "max_questions": max((l.question_count for l in week_leads), default=0),
        "weekly_note":   note.content if note else None,
        "top_questions": top_questions,
        "peak_report_id":    peak_report.id if peak_report else None,
        "peak_report_label": peak_report.period_label if peak_report else None,
        "peak_report_time":  peak_report.uploaded_at.strftime("%Y-%m-%d %H:%M") if peak_report else None,
        "visible_leads": visible_leads_data,
        "leads_report": {
            "id": leads_report.id
        } if leads_report else None,

    }
# ---------------------------------------------------------------------------
# Export leads report as HTML (for sales to download and share with team)
# ---------------------------------------------------------------------------
from typing import Optional
from fastapi.responses import HTMLResponse

@app.get("/trackdashboard/export-leads-html")
async def export_leads_html(
    request: Request,
    week: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)

    from datetime import datetime, timedelta, date
    
    # 1. Default to current week and year if not provided
    if not week: week = date.today().isocalendar()[1]
    if not year: year = date.today().year

    # 2. Calculate the exact start and end dates for the target week
    try:
        start_of_week = datetime.fromisocalendar(year, week, 1)
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    except ValueError:
        # Fallback just in case
        return HTMLResponse(content="Invalid week or year format", status_code=400)

    # 3. Fast DB-level filtering (Only fetch leads for this specific week)
    leads = (
        db.query(models.Lead)
        .filter(
            models.Lead.timestamp >= start_of_week,
            models.Lead.timestamp <= end_of_week
        )
        .order_by(models.Lead.timestamp.desc()) # رتبهم من الأحدث للأقدم عشان التقرير يبقى شيك
        .all()
    )

    context = {
        "request":      request,
        "leads":        leads,
        "generated_at": datetime.now(),
        "week_num":     week,
        "year":         year,
        "week_label":   _week_label(year, week),
    }

    # Render template and return as downloadable file
    html_content = templates.get_template("leads_report.html").render(context)
    return HTMLResponse(
        content=html_content,
        headers={
            "Content-Disposition": f"attachment; filename=leads_week{week}_{year}.html"
        },
    )
# ---------------------------------------------------------------------------
# Upload HTML report from trackdashboard
# ---------------------------------------------------------------------------

@app.post("/trackdashboard/notifications/{req_id}/upload-report")
async def upload_report_for_request(
    req_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)

    req = db.query(models.ReportRequest).filter(
        models.ReportRequest.id == req_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    content      = await file.read()
    html_content = content.decode("utf-8", errors="ignore")

    # Determine period label
    from datetime import date
    today = date.today()

    if req.report_type == "peak_hours":
        # اشوف هو اسبوعي ولا شهري من اسم الملف
        fname = file.filename.lower()
        if "monthly" in fname or "month" in fname:
            months_ar = ["","يناير","فبراير","مارس","أبريل","مايو","يونيو",
                        "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
            month_num = today.month
            period_label  = f"شهري — {months_ar[month_num]} {req.year}"
            report_period = "monthly"
        else:
            period_label  = f"أسبوعي — أسبوع {req.week_number} / {req.year}"
            report_period = "weekly"

    elif req.report_type == "repeated_visitors":
        fname = file.filename.lower()
        if "monthly" in fname or "month" in fname:
            months_ar = ["","يناير","فبراير","مارس","أبريل","مايو","يونيو",
                        "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
            month_num = today.month
            period_label  = f"شهري — {months_ar[month_num]} {req.year}"
            report_period = "monthly"
        elif "daily" in fname or "day" in fname:
            period_label  = f"يومي — {today.strftime('%Y-%m-%d')}"
            report_period = "daily"
        else:
            period_label  = f"أسبوعي — أسبوع {req.week_number} / {req.year}"
            report_period = "weekly"

    else:
        period_label  = f"أسبوع {req.week_number} / {req.year}"
        report_period = req.report_type

    # Replace if already uploaded for same request
    existing = db.query(models.UploadedReport).filter(
        models.UploadedReport.request_id == req_id
    ).first()
    if existing:
        existing.html_content  = html_content
        existing.filename      = file.filename
        existing.uploaded_at   = datetime.now()
        existing.period_label  = period_label
        existing.report_period = report_period
    else:
        db.add(models.UploadedReport(
            request_id    = req_id,
            report_type   = req.report_type,
            report_period = report_period,
            period_label  = period_label,
            filename      = file.filename,
            html_content  = html_content,
            week_number   = req.week_number,
            year          = req.year,
        ))

    req.is_seen = True
    req.seen_at = datetime.now()
    db.commit()
    return {"status": "uploaded"}


@app.get("/view-report/{report_id}", response_class=HTMLResponse)
async def view_report_by_id(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    get_dashboard_user(request)
    report = db.query(models.UploadedReport).filter(
        models.UploadedReport.id == report_id
    ).first()
    if not report:
        return HTMLResponse("<h3 style='text-align:center;margin-top:50px;color:#aaa;'>لا يوجد تقرير</h3>")
    return HTMLResponse(content=report.html_content)

# ---------------------------------------------------------------------------
# Peak hours reports can be viewed for past weeks, so separate route with report_id
# ---------------------------------------------------------------------------
@app.get("/dashboard/peak-report/{report_id}", response_class=HTMLResponse)
async def view_peak_report(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    get_dashboard_user(request)
    report = db.query(models.UploadedReport).filter(
        models.UploadedReport.id == report_id
    ).first()
    if not report:
        return HTMLResponse("""
            <div style='text-align:center;margin-top:80px;font-family:sans-serif;color:#aaa;'>
                <div style='font-size:40px;margin-bottom:12px;'>⏳</div>
                <h3>التقرير لم يُرفع بعد</h3>
            </div>
        """)
    return HTMLResponse(content=report.html_content)

@app.get("/dashboard/peak-reports/{week_num}/{year}")
async def get_peak_reports(
    week_num: int,
    year: int,
    request: Request,
    db: Session = Depends(get_db),
):
    get_dashboard_user(request)
    reports = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "peak_hours",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .order_by(models.UploadedReport.uploaded_at.desc())
        .all()
    )
    return [
        {
            "id":           r.id,
            "period_label": r.period_label or f"أسبوع {week_num} / {year}",
            "uploaded_at":  str(r.uploaded_at)[:16],
        }
        for r in reports
    ]
# ---------------------------------------------------------------------------
# Question categories management (trackdashboard)
# ---------------------------------------------------------------------------

@app.post("/trackdashboard/categories/create")
async def create_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)
    existing = db.query(models.QuestionCategory).filter(
        models.QuestionCategory.name == name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")
    cat = models.QuestionCategory(name=name, description=description, is_visible=False)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"status": "created", "id": cat.id, "name": cat.name}


@app.post("/trackdashboard/categories/{cat_id}/toggle")
async def toggle_category(cat_id: int, request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    cat = db.query(models.QuestionCategory).filter(
        models.QuestionCategory.id == cat_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.is_visible = not cat.is_visible
    db.commit()
    return {"status": "toggled", "is_visible": cat.is_visible}


@app.delete("/trackdashboard/categories/{cat_id}")
async def delete_category(cat_id: int, request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    cat = db.query(models.QuestionCategory).filter(
        models.QuestionCategory.id == cat_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(cat)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/categories/questions")
async def get_category_questions(request: Request,week: int = None,year: int = None, db: Session = Depends(get_db)):
    """
    Returns visible categories with their top questions.
    Called by dashboard.html on load.
    """
    get_dashboard_user(request)
    categories = db.query(models.QuestionCategory).filter(
        models.QuestionCategory.is_visible == True
    ).all()

    result = []
    for cat in categories:
        from datetime import datetime
        if week and year:
            try:
                from datetime import timedelta
                start_of_week = datetime.fromisocalendar(year, week, 1).replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_week   = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
                q_filter = (
                    models.ChatLog.category == cat.name,
                    models.ChatLog.timestamp >= start_of_week,
                    models.ChatLog.timestamp <= end_of_week,
                )
            except ValueError:
                q_filter = (models.ChatLog.category == cat.name,)
        else:
            q_filter = (models.ChatLog.category == cat.name,)

        questions = (
            db.query(models.ChatLog.user_query, func.count(models.ChatLog.user_query).label("cnt"))
            .filter(*q_filter)
            .group_by(models.ChatLog.user_query)
            .order_by(func.count(models.ChatLog.user_query).desc())
            .limit(10)
            .all()
        )
        result.append({
            "id":        cat.id,
            "name":      cat.name,
            "questions": [{"query": q.user_query, "count": q.cnt} for q in questions],
        })

    return result


@app.get("/trackdashboard/categories/data")
async def get_all_categories(request: Request, db: Session = Depends(get_db)):
    """Returns all categories for trackdashboard management."""
    get_trackdashboard_user(request)
    cats = db.query(models.QuestionCategory).order_by(models.QuestionCategory.created_at).all()
    return [
        {
            "id":          c.id,
            "name":        c.name,
            "description": c.description,
            "is_visible":  c.is_visible,
        }
        for c in cats
    ]
#=======================================================================================
# to make html export of questions + answers for a category, so sales can share with team
#========================================================================================
@app.get("/trackdashboard/categories/{cat_id}/questions")
async def get_category_questions_full(
    cat_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)
    cat = db.query(models.QuestionCategory).filter(
        models.QuestionCategory.id == cat_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Get all logs in this category
    logs = (
        db.query(models.ChatLog)
        .filter(models.ChatLog.category == cat.name)
        .order_by(models.ChatLog.timestamp.desc())
        .all()
    )

    # Get phone numbers linked to sessions
    session_ids = list(set(log.session_id for log in logs))
    leads = (
        db.query(models.Lead)
        .filter(models.Lead.session_id.in_(session_ids))
        .all()
    )
    phone_map = {l.session_id: l.phone_number for l in leads}

    # Group questions by phone number
    contacts = {}
    no_phone = []

    for log in logs:
        phone = phone_map.get(log.session_id)
        qa = {
            "user_query": log.user_query,
            "bot_answer": log.bot_answer,
            "timestamp":  log.timestamp.strftime("%Y-%m-%d %H:%M"),
        }
        if phone:
            if phone not in contacts:
                contacts[phone] = {
                    "phone":     phone,
                    "questions": [],
                    "first_seen": log.timestamp.strftime("%Y-%m-%d %H:%M"),
                }
            contacts[phone]["questions"].append(qa)
        else:
            no_phone.append(qa)

    return {
        "category":  cat.name,
        "contacts":  list(contacts.values()),
        "no_phone":  no_phone,
    }


# ---------------------------------------------------------------------------
# Peak hours report — weekly
# ---------------------------------------------------------------------------
@app.get("/trackdashboard/peak-hours/weekly")
async def peak_hours_weekly(
    request: Request,
    week: int = None,
    year: int = None,
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)

    from datetime import date, timedelta
    from collections import defaultdict

    today = date.today()
    if not week: week = today.isocalendar()[1]
    if not year: year = today.year

    days_ar = ["الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]

    all_logs = db.query(models.ChatLog).all()
    week_logs = [
        l for l in all_logs
        if l.timestamp.isocalendar()[1] == week
        and l.timestamp.year == year
    ]

    day_counts  = defaultdict(int)
    hour_counts = defaultdict(int)
    for log in week_logs:
        day_counts[log.timestamp.weekday()] += 1
        hour_counts[log.timestamp.hour]     += 1

    peak_day  = max(day_counts, key=day_counts.get) if day_counts else 0
    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0

    import json

    context = {
        "request":         request,
        "report_type":     "weekly",
        "week_num":        week,
        "year":            year,
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "peak_day":        days_ar[peak_day] if day_counts else "—",
        "peak_hour":       f"{peak_hour:02d}:00 — {peak_hour+1:02d}:00",
        "total_sessions":  len(set(l.session_id for l in week_logs)),
        "total_questions": len(week_logs),
        "days_labels":     json.dumps([d for d in days_ar]),
        "days_data":       json.dumps([day_counts.get(i, 0) for i in range(7)]),
        "hours_labels":    json.dumps([f"{h:02d}:00" for h in range(24)]),
        "hours_data":      json.dumps([hour_counts.get(i, 0) for i in range(24)]),
        "extra_labels":    "null",
        "extra_data":      "null",
        "extra_title":     "",
    }

    html = templates.get_template("peak_hours_report.html").render(context)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f"attachment; filename=peak_weekly_{week}_{year}.html"},
    )


# ---------------------------------------------------------------------------
# Peak hours report — monthly
# ---------------------------------------------------------------------------
@app.get("/trackdashboard/peak-hours/monthly")
async def peak_hours_monthly(
    request: Request,
    month: int = None,
    year: int = None,
    db: Session = Depends(get_db),
):
    get_trackdashboard_user(request)

    from datetime import date
    from collections import defaultdict

    today = date.today()
    if not month: month = today.month
    if not year:  year  = today.year

    days_ar    = ["الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
    months_ar  = ["","يناير","فبراير","مارس","أبريل","مايو","يونيو",
                  "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]

    all_logs = db.query(models.ChatLog).all()
    month_logs = [
        l for l in all_logs
        if l.timestamp.month == month
        and l.timestamp.year == year
    ]

    day_counts  = defaultdict(int)
    hour_counts = defaultdict(int)
    week_counts = defaultdict(int)

    for log in month_logs:
        day_counts[log.timestamp.weekday()]              += 1
        hour_counts[log.timestamp.hour]                  += 1
        week_counts[log.timestamp.isocalendar()[1]]      += 1

    peak_day  = max(day_counts,  key=day_counts.get)  if day_counts  else 0
    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0

    sorted_weeks = dict(sorted(week_counts.items()))

    import json

    context = {
        "request":         request,
        "report_type":     "monthly",
        "week_num":        month,
        "year":            year,
        "month_name":      months_ar[month],
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "peak_day":        days_ar[peak_day] if day_counts else "—",
        "peak_hour":       f"{peak_hour:02d}:00 — {peak_hour+1:02d}:00",
        "total_sessions":  len(set(l.session_id for l in month_logs)),
        "total_questions": len(month_logs),
        "days_labels":     json.dumps([d for d in days_ar]),
        "days_data":       json.dumps([day_counts.get(i, 0) for i in range(7)]),
        "hours_labels":    json.dumps([f"{h:02d}:00" for h in range(24)]),
        "hours_data":      json.dumps([hour_counts.get(i, 0) for i in range(24)]),
        "extra_labels":    json.dumps([f"أسبوع {w}" for w in sorted_weeks.keys()]),
        "extra_data":      json.dumps(list(sorted_weeks.values())),
        "extra_title":     "📈 توزيع النشاط على أسابيع الشهر",
    }
    html = templates.get_template("peak_hours_report.html").render(context)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f"attachment; filename=peak_monthly_{month}_{year}.html"},
    )
@app.get("/api/topics/questions")
async def get_topic_questions(
    request: Request,
    week: int = None,
    year: int = None,
    db: Session = Depends(get_db)
):
    get_dashboard_user(request)

    from datetime import date
    from collections import Counter

    if not week: week = date.today().isocalendar()[1]
    if not year: year = date.today().year

    all_logs = (
        db.query(models.ChatLog)
        .filter(models.ChatLog.topic != None)
        .all()
    )

    week_logs = [
        log for log in all_logs
        if log.timestamp.isocalendar()[1] == week
        and log.timestamp.year == year
    ]

    counter = Counter(log.topic for log in week_logs)

    return [
        {"topic": topic, "count": count}
        for topic, count in counter.most_common(10)
    ]

# to identify repeated visitors by phone number, and show their questions across visits/sessions
@app.get("/trackdashboard/repeated-visitors")
async def get_repeated_visitors(request: Request, db: Session = Depends(get_db)):
    get_trackdashboard_user(request)
    from collections import defaultdict

    # Get all leads with phone numbers
    leads = (
        db.query(models.Lead)
        .filter(models.Lead.phone_number != None)
        .order_by(models.Lead.timestamp.asc())
        .all()
    )

    # Group by phone number
    phone_groups = defaultdict(list)
    for lead in leads:
        phone_groups[lead.phone_number].append(lead)

    # Keep only repeated visitors
    repeated = {
        phone: visits
        for phone, visits in phone_groups.items()
        if len(visits) > 1
    }

    result = []
    for phone, visits in repeated.items():
        # Get all questions for each visit
        visits_data = []
        for visit in visits:
            logs = (
                db.query(models.ChatLog)
                .filter(models.ChatLog.session_id == visit.session_id)
                .order_by(models.ChatLog.timestamp.asc())
                .all()
            )
            visits_data.append({
                "session_id":    visit.session_id,
                "timestamp":     visit.timestamp.strftime("%Y-%m-%d %H:%M"),
                "question_count": visit.question_count,
                "asked_price":   visit.asked_about_price,
                "asked_reg":     visit.asked_about_registration,
                "lead_status":   visit.lead_status,
                "questions": [
                    {"q": l.user_query, "a": l.bot_answer}
                    for l in logs
                ],
            })

        result.append({
            "phone":        phone,
            "visit_count":  len(visits),
            "asked_price_ever": any(v["asked_price"] for v in visits_data),
            "asked_reg_ever":   any(v["asked_reg"]   for v in visits_data),
            "visits":       visits_data,
        })

    # Sort by visit count
    result.sort(key=lambda x: x["visit_count"], reverse=True)
    return result

#to get the latest repeated visitors report for a specific week,in lasr week and next week 
@app.get("/dashboard/repeated-reports/{week_num}/{year}")
async def get_repeated_report(
    week_num: int,
    year: int,
    request: Request,
    db: Session = Depends(get_db),
):
    get_dashboard_user(request)
    reports = (
        db.query(models.UploadedReport)
        .filter(
            models.UploadedReport.report_type == "repeated_visitors",
            models.UploadedReport.week_number == week_num,
            models.UploadedReport.year        == year,
        )
        .order_by(models.UploadedReport.uploaded_at.desc())
        .all()
    )
    return {
        "reports": [
            {
                "id":           r.id,
                "period_label": r.period_label or f"أسبوع {week_num} / {year}",
                "uploaded_at":  r.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            }
            for r in reports
        ]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)