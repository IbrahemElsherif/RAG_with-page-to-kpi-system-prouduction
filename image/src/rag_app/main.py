from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from chromadb.config import Settings

from sqlalchemy.orm import Session
import io
from rag_app.database import engine, SessionLocal, get_db
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
import csv
import warnings
import logging
import os


# Suppress warnings
warnings.filterwarnings("ignore", message=".*Failed to send telemetry event.*")
warnings.filterwarnings("ignore", message=".*telemetry.*")
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)


# معلومات الفروع الثابتة
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
"""
load_dotenv()

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")
# table creation
models.Base.metadata.create_all(bind=engine)


# Make BASE_DIR dynamic
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
# Update TEMPLATES_DIR
TEMPLATES_DIR = BASE_DIR / "templates"
#  Point to the chroma_db folder inside your app directory
# Support environment variable for persistent volume (AWS/Docker)
CHROMA_PATH_ENV = os.getenv("CHROMA_PATH")

if CHROMA_PATH_ENV:
    # 1. الحالة الأولى: لو محددين مسار في الـ ENV (للـ Docker/AWS)
    CHROMA_PATH = Path(CHROMA_PATH_ENV)
    # If persistent volume is empty, fallback to local data folder in image
    if not os.path.exists(CHROMA_PATH) or (
        os.path.isdir(CHROMA_PATH) and not any(CHROMA_PATH.iterdir())
    ):
        LOCAL_DATA_PATH = BASE_DIR / "data" / "chroma_db"
        if os.path.exists(LOCAL_DATA_PATH) and any(LOCAL_DATA_PATH.iterdir()):
            CHROMA_PATH = LOCAL_DATA_PATH
            print(
                f"--- [CHROMA INFO] Persistent volume empty, using local data at: {CHROMA_PATH} ---"
            )
        else:
            print(
                f"--- [CHROMA INFO] Using Environment Path at: {CHROMA_PATH} (will be created if needed) ---"
            )
    else:
        print(f"--- [CHROMA INFO] Using Environment Path at: {CHROMA_PATH} ---")
else:
    # 2. الحالة الثانية: لو شغالين Local (ويندوز/ماك) - استخدم المجلد اللي في data
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


# --- دوال تحميل قاعدة المعرفة ---
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
        print(
            "--- [WARNING] ChromaDB folder not found. Please upload DB via admin panel. ---"
        )


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


# --- دوال الحماية (Admin Auth) ---
def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="بيانات غير صحيحة",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --- Models ---
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Tuple[str, str]]] = []
    session_id: str = "unknown"


# --- (RAG Logic) ---


def prepare_rag_context(message: str, history: List[Tuple[str, str]]):
    """
    دالة إعداد سياق RAG للمساعد الذكي

    Args:
        message: رسالة المستخدم الحالية
        history: تاريخ المحادثة [(user_msg, assistant_msg), ...]

    Returns:
        tuple: (البرومبت النهائي, استعلام البحث, المستندات المسترجعة, التاريخ المحدود)
    """
    # ===== التحقق من وجود قاعدة البيانات =====
    if not vector_store:
        return None, message, [], history

    # ===== إعدادات الذاكرة =====
    MEMORY_WINDOW_SIZE = 3
    SIMILARITY_THRESHOLD = 1.5
    TOP_K_RESULTS = 5

    # ===== الخطوة 1: تحديد نافذة الذاكرة =====
    limited_history = history[-MEMORY_WINDOW_SIZE:]

    # ===== الخطوة 2: تنسيق تاريخ المحادثة =====
    formatted_history_text = ""
    if limited_history:
        formatted_history_text = "\n".join(
            [
                f"User: {user_msg}\nAssistant: {assistant_msg}"
                for user_msg, assistant_msg in limited_history
            ]
        )

    # ===== الخطوة 3: إعادة صياغة الاستعلام (إذا وُجد تاريخ) =====
    search_query = message

    if history:
        rephrase_prompt = f"""
أنت خبير في فهم سياق المحادثات.
لديك محادثة سابقة وسؤال جديد من المستخدم.

تاريخ المحادثة:
{formatted_history_text}

رد المستخدم الأخير: {message}

المطلوب:
- إذا كان رد المستخدم إجابة على سؤال من المساعد (مثلاً المساعد سأل عن شرط، والمستخدم أكد تحقيقه):
  استنتج "الخطوة التالية" واجعلها هي جملة البحث.
  (مثال: إذا قال المستخدم "أنا غير مسجل" رداً على شرط التسجيل، اجعل البحث: "طريقة التسجيل لغير المسجلين").

- إذا كان سؤالاً جديداً تماماً، أعد صياغته ليكون واضحاً.

اكتب جملة البحث المحسنة فقط بدون أي مقدمات:
"""

        try:
            search_query = llm.invoke(rephrase_prompt).content.strip()
            print(f"--- [DEBUG] Smart Search Query: {search_query} ---")
        except Exception as e:
            print(f"--- [ERROR] Rephrase failed: {e} ---")
            search_query = message

    # ===== الخطوة 4: استرجاع المستندات ذات الصلة =====
    results = vector_store.similarity_search_with_score(search_query, k=TOP_K_RESULTS)

    good_docs = [
        doc.page_content for doc, score in results if score < SIMILARITY_THRESHOLD
    ]

    knowledge = "\n\n".join(good_docs)
    print(f"--- [DEBUG] Found {len(good_docs)} relevant documents ---")


    # rag_prompt = f"""
    # أنت مساعد ذكي للمعهد السعودي المتخصص العالي للتدريب.
    # تستخدم المعلومات المتاحة للإجابة على استفسارات الزوار.

    # === البيانات الثابتة (GLOBAL_FACTS) ===
    # {GLOBAL_FACTS}

    # === المعلومات المسترجعة (Context) ===
    # {knowledge}

    # === تاريخ المحادثة (History) ===
    # {formatted_history_text}

    # === تعليمات الإجابة (Guidelines) ===
    # 1. البيانات أعلاه (Context & Facts) باللغة العربية، لكن يجب أن ترد بناءً على لغة المستخدم.
    # 2. إذا سأل عن مدينة غير موجودة (مثل جدة، تبوك): اعتذر واذكر الفروع المتاحة.
    # 3. عند السؤال عن الأسعار أو التسجيل: أرسل الرقم الموحد 920012673 ورقم الواتساب 0554194677.
    # 4. كن مباشراً ومختصراً.

    # === LANGUAGE PROTOCOL (CRITICAL) ===
    # 1. **Detect User Language:** Check the last message sent by the user: "{message}".
    # 2. **IF ARABIC:** Answer directly in Arabic.
    # 3. **IF ENGLISH:** You MUST translate the relevant information from the Context/Facts into English and answer in English. - Example: If context says "فرع الرياض في حي الحمراء", and user asks "Where is Riyadh branch?", you MUST say: "The Riyadh branch is located in Al-Hamra district..." with the Google Map link.

    # User: {message}
    # Assistant:
    # """

    # ===== الخطوة 5: بناء البرومبت النهائي =====
    rag_prompt = f"""
أنت مساعد ذكي للمعهد السعودي المتخصص العالي للتدريب.
تساعد زوار الموقع الإلكتروني الخاص بالمعهد.

=== تعليمات مهمة ===
1. راجع (GLOBAL_FACTS) دائماً قبل الإجابة عن الفروع والمواقع
2. إذا سأل عن مدينة غير موجودة في القائمة (مثل عرعر، جدة، تبوك):
   - قل بوضوح: "عذراً، لا يوجد لدينا فرع في هذه المدينة حالياً"
   - اذكر له الفروع المتاحة كبديل
3. إذا سأل عن فرع موجود، أعطه اسم الحي والرابط مباشرة
4. لا تبدأ الإجابة بـ "الجواب:" أو "الإجابة هي" - ادخل في الموضوع مباشرة
5. راقب تاريخ المحادثة: لا تكرر الشروط المستوفاة، أعط الخطوة التالية
6. عند السؤال عن الأسعار أو الرغبة في التسجيل: أرسل الرقم الموحد 920012673 والرقم 0554194677 للواتساب

=== البيانات الثابتة (GLOBAL_FACTS) ===
{GLOBAL_FACTS}

=== المعلومات المسترجعة (Context) ===
{knowledge}

=== تاريخ المحادثة (History) ===
{formatted_history_text}

User: {message}
Assistant:
"""

    return rag_prompt, search_query, good_docs, limited_history


async def generate_response_stream(
    message: str, history: List[Tuple[str, str]], session_id: str, db: Session
):
    start_time = time.time()  # 1. شغل العداد

    rag_prompt, search_query, docs, _ = prepare_rag_context(message, history)

    full_answer = ""
    first_token_time = None

    if not rag_prompt:
        err_msg = "عذراً، قاعدة البيانات غير جاهزة."
        yield err_msg
        full_answer = err_msg
        # في حالة الخطأ نحسب الوقت الكلي ونعتبره TTFT
        response_time_to_log = time.time() - start_time

    else:
        try:
            async for chunk in llm.astream(rag_prompt):
                if chunk.content:
                    # 2. اللحظة الحاسمة: هل هذه أول قطعة تصل؟
                    if first_token_time is None:
                        # نعم! أوقف العداد فوراً واحفظ الوقت (وهذا هو TTFT)
                        first_token_time = time.time() - start_time

                    full_answer += chunk.content
                    yield chunk.content

            # calculate TTFT time
            response_time_to_log = (
                first_token_time
                if first_token_time is not None
                else (time.time() - start_time)
            )

        except Exception as e:
            yield f"Error: {str(e)}"
            response_time_to_log = time.time() - start_time  # زمن الخطأ

    # 4. الحفظ الموحد والوحيد في قاعدة البيانات
    try:
        new_log = models.ChatLog(
            session_id=session_id,
            user_query=message,
            bot_answer=full_answer,
            response_time=response_time_to_log,  # <--- تم حفظ القيمة الموحدة (TTFT أو الكلي)
            timestamp=datetime.now(),
        )
        db.add(new_log)
        db.commit()
        print(f"--- [LOG] Response Time Saved: {response_time_to_log:.2f}s ---")
    except Exception as e:
        print(f"--- [ERROR] DB Save failed: {e} ---")


# 1. الصفحة الرئيسية (للطلاب)
@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    # التحقق من وضع الصيانة
    if MAINTENANCE_MODE:
        return templates.TemplateResponse("user_maintenance.html", {"request": request})
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# 2. الـ Chat API
@app.post("/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    if MAINTENANCE_MODE:

        async def msg():
            yield "عذراً، النظام يخضع للتحديث حالياً. يرجى تحديث الصفحة."

        return StreamingResponse(msg(), media_type="text/plain")

    return StreamingResponse(
        generate_response_stream(
            request.message, request.history, request.session_id, db
        ),
        media_type="text/plain",
    )


# 3. لوحة التحكم - الصفحة الرئيسية (Maintenance & Control)
@app.get("/admin/maintenance", response_class=HTMLResponse)
def maintenance_page(request: Request, username: str = Depends(get_current_admin)):
    stats = get_chroma_stats()
    return templates.TemplateResponse(
        "maintenance.html",
        {"request": request, "is_maintenance": MAINTENANCE_MODE, "db_stats": stats},
    )


# 4. زر التحكم اليدوي في الصيانة (On/Off)
@app.post("/admin/toggle-maintenance")
async def toggle_maintenance(
    request: Request, username: str = Depends(get_current_admin)
):
    global MAINTENANCE_MODE
    form_data = await request.form()
    state = form_data.get("state")

    if state == "on":
        MAINTENANCE_MODE = True
    elif state == "off":
        MAINTENANCE_MODE = False

    # إعادة توجيه لنفس الصفحة لتحديث الحالة
    stats = get_chroma_stats()
    return templates.TemplateResponse(
        "maintenance.html",
        {"request": request, "is_maintenance": MAINTENANCE_MODE, "db_stats": stats},
    )


# 5. رفع قاعدة البيانات (Upload DB)
@app.post("/admin/upload-db")
async def upload_db(
    request: Request,
    file: UploadFile = File(...),
    username: str = Depends(get_current_admin),
):
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = True  # تفعيل الصيانة تلقائياً أثناء الرفع
    try:
        temp_zip = "temp.zip"
        with open(temp_zip, "wb") as b:
            shutil.copyfileobj(file.file, b)

        if os.path.exists(CHROMA_PATH):
            try:
                shutil.rmtree(CHROMA_PATH)
            except:
                pass

        # Ensure the parent directory exists
        CHROMA_PATH.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(temp_zip, "r") as z:
            # Extract to the CHROMA_PATH directory
            z.extractall(CHROMA_PATH.parent)

        os.remove(temp_zip)
        reload_vector_store()

        stats = get_chroma_stats()
        return templates.TemplateResponse(
            "maintenance.html",
            {
                "request": request,
                "is_maintenance": False,  # إيقاف الصيانة بعد النجاح
                "db_stats": stats,
                "message": "تم تحديث قاعدة البيانات بنجاح!",
            },
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        MAINTENANCE_MODE = False


# 6. لوحة الإحصائيات (KPI)
@app.get("/admin/kpi", response_class=HTMLResponse)
def kpi_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    # 1. جلب آخر 50 سجل للعرض في الجدول
    logs = (
        db.query(models.ChatLog)
        .order_by(models.ChatLog.timestamp.desc())
        .limit(50)
        .all()
    )

    grouped_sessions = {}
    for log in logs:
        sid = log.session_id or "Anonymous"  # لو مفيش آيدي نعتبره مجهول
        if sid not in grouped_sessions:
            grouped_sessions[sid] = []
        grouped_sessions[sid].append(log)

    # 2. جلب العدد الكلي للمحادثات
    total_chats = db.query(models.ChatLog).count()

    # --- الحسابات الجديدة ---
    avg_speed_all = 0  # متوسط الكل
    avg_speed_last_10 = 0  # متوسط آخر 10

    if total_chats > 0:
        # أ) حساب المتوسط الكلي (لجميع البيانات في الجدول)
        # ملاحظة: لجلب متوسط الكل بدقة يفضل استخدام دالة SQL func.avg لكن للتبسيط سنحسبها بايثون
        all_logs = db.query(
            models.ChatLog.response_time
        ).all()  # نجلب فقط عمود الوقت للتخفيف
        all_times = [r[0] for r in all_logs if r[0] is not None]
        if all_times:
            avg_speed_all = sum(all_times) / len(all_times)

        # ب) حساب متوسط آخر 10 محادثات فقط
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
            "avg_speed_all": round(avg_speed_all, 2),  # الرقم الأول
            "avg_speed_last_10": round(avg_speed_last_10, 2),  # الرقم الثاني
            "now": datetime.now(),
        },
    )


# 7. تفاصيل محادثة واحدة (عرض التقرير الفردي)
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
    return templates.TemplateResponse(
        "chat_details.html", {"request": request, "log": log}
    )


# 8. تحميل البيانات (CSV/Excel)
@app.get("/admin/export-csv")
def export_logs_csv(
    db: Session = Depends(get_db), username: str = Depends(get_current_admin)
):
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).all()

    output = io.StringIO()
    output.write("\ufeff")  # دعم اللغة العربية في Excel
    writer = csv.writer(output)
    writer.writerow(
        ["ID", "Date", "Time", "User Question", "Bot Answer", "Response Time (s)"]
    )

    for log in logs:
        writer.writerow(
            [
                log.id,
                log.timestamp.strftime("%Y-%m-%d"),
                log.timestamp.strftime("%H:%M:%S"),
                log.user_query,
                log.bot_answer,
                f"{log.response_time:.2f}",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chat_logs_report.csv"},
    )


# 9. التقرير الشامل (عرض أو تحميل)
@app.get(
    "/admin/full-report"
)  # أزلنا response_class هنا لنتمكن من التحكم في النوع يدوياً
def full_report_page(
    request: Request,
    download: bool = False,  # متغير جديد للتحكم
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).all()

    context = {"request": request, "logs": logs, "generated_at": datetime.now()}

    # إذا طلب المستخدم التنزيل (download=True)
    if download:
        # نقوم بتحويل القالب إلى نص HTML كامل
        html_content = templates.get_template("full_report.html").render(context)

        # نرسله كملف للتحميل
        return HTMLResponse(
            content=html_content,
            headers={
                "Content-Disposition": f"attachment; filename=full_report_{datetime.now().strftime('%Y-%m-%d')}.html"
            },
        )

    # العرض العادي (في المتصفح)
    return templates.TemplateResponse("full_report.html", context)


# ---10 endpoint جديد لحذف سجل واحد ---
@app.delete("/admin/kpi/delete/{log_id}")
def delete_chat_log(
    log_id: int,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    # البحث عن السجل
    log = db.query(models.ChatLog).filter(models.ChatLog.id == log_id).first()

    if not log:
        raise HTTPException(status_code=404, detail="السجل غير موجود")

    # الحذف
    db.delete(log)
    db.commit()

    return {"status": "success", "message": f"تم حذف السجل رقم {log_id}"}


# 11. API داخلي للمعلومات
@app.get("/admin/db-info")
def db_info_endpoint(username: str = Depends(get_current_admin)):
    return {"maintenance_mode": MAINTENANCE_MODE, "db_stats": get_chroma_stats()}


# --- 11. Endpoint جديد لحذف جلسة كاملة ---
@app.delete("/admin/kpi/delete-session/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_admin),
):
    # مسح جميع الرسائل التي تحمل نفس session_id
    rows_deleted = (
        db.query(models.ChatLog)
        .filter(models.ChatLog.session_id == session_id)
        .delete()
    )
    db.commit()

    if rows_deleted == 0:
        raise HTTPException(status_code=404, detail="لم يتم العثور على الجلسة")

    return {
        "status": "success",
        "message": f"تم حذف الجلسة {session_id} و {rows_deleted} رسالة تابعة لها",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
