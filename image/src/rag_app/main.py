import uvicorn
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from mangum import Mangum
from pathlib import Path
from sqlalchemy.orm import Session
from pydantic import BaseModel
import asyncio
import time
from datetime import datetime
from typing import List, Tuple, Optional
import os
import shutil
import zipfile
import secrets
import csv
import io

# --- استيراد ملفات قاعدة البيانات (SQLite) ---
from database import engine, SessionLocal, get_db
import models

# إنشاء الجداول
models.Base.metadata.create_all(bind=engine)

# --- مكتبات RAG ---
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv



load_dotenv()

# Fix 1: Make BASE_DIR dynamic (This is already correct in your code, keep it)
BASE_DIR = Path(__file__).resolve().parent 

# Fix 2: Update TEMPLATES_DIR (This is also correct, keep it)
TEMPLATES_DIR = BASE_DIR / "templates"

# Fix 3: CRITICAL CHANGE - Fix CHROMA_PATH
# Old code: CHROMA_PATH = r"image\src\data\chroma_db"
# New code: Point to the chroma_db folder inside your app directory
CHROMA_PATH = BASE_DIR / "chroma_db"
COLLECTION_NAME = "example_collection" 
MAINTENANCE_MODE = False # المتغير المتحكم في حالة النظام
security = HTTPBasic()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

print("--- [INFO] Loading models... ---")
embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(temperature=0.1, model='gpt-4o-mini')
vector_store = None

# --- دوال تحميل قاعدة المعرفة ---
def load_vector_store():
    global vector_store
    if os.path.exists(CHROMA_PATH):
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings_model,
            persist_directory=str(CHROMA_PATH), 
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
        except: pass
    return {"status": "Not Loaded", "total_documents": 0}

# --- دوال الحماية (Admin Auth) ---
def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "admin123")
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
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="RAG API Final System")
handler = Mangum(app)  # Entry point for AWS Lambda.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace "*" with your website URL (e.g. "https://myschool.com")
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- منطق الذكاء (RAG Logic) ---

def prepare_rag_context(message: str, history: List[Tuple[str, str]]):
    if not vector_store:
        return None, message, [], history
        
    MEMORY_WINDOW_SIZE = 3
    limited_history = history[-MEMORY_WINDOW_SIZE:]
    
    # 1. تحويل الهيستوري إلى نص منسق (User/Assistant) ليفهمه الموديل
    formatted_history_text = ""
    if limited_history:
        formatted_history_text = "\n".join([f"User: {t[0]}\nAssistant: {t[1]}" for t in limited_history])

    search_query = message

    # 2. إعادة صياغة السؤال (هنا الحل السحري لمشكلتك)
    if history:
        # هذا البرومبت يطلب من الموديل فهم "نية" المستخدم وليس مجرد كلماته
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
            print(f"--- [DEBUG] Smart Search Query: {search_query} ---") # للتأكد في التيرمينال
        except: pass

    # 3. البحث
    results = vector_store.similarity_search_with_score(search_query, k=5)
    good_docs = [doc.page_content for doc, score in results if score < 1.5]
    knowledge = "\n\n".join(good_docs)
    
    # 4. برومبت الرد النهائي (تحسين التنسيق ومنع التكرار)
    rag_prompt = f"""
    أنت مساعد ذكي للمعهد السعودي المتخصص العالي للتدريب.
    انت تساعد زوار الموقع الإلكتروني الخاص بالمعهد السعودي المتخصص العالي للتدريب
    تعليمات للمساعد:
    1. هدفك هو مساعدة الطالب بناءً على "المعلومات المسترجعة" و "سياق المحادثة".
    2. لا تبدأ الإجابة بكلمات مثل "الجواب:" أو "الإجابة هي". ادخل في الموضوع مباشرة.
    3. راقب "تاريخ المحادثة": إذا كان المستخدم قد استوفى شرطاً ذكرته له سابقاً، لا تكرر الشرط، بل أعطه الخطوة التالية (مثل رابط التسجيل أو طريقة التقديم).
    
    المعلومات المسترجعة (Context):
    {knowledge}
    
    تاريخ المحادثة (History):
    {formatted_history_text}
    
    User: {message}
    Assistant:
    """
    
    # لاحظ أننا نرجع limited_history كما هي للكود، لكن استخدمنا formatted_history_text داخل البرومبت فقط
    return rag_prompt, search_query, good_docs, limited_history

async def generate_response_stream(message: str, history: List[Tuple[str, str]], db: Session):
    start_time = time.time() # 1. شغل العداد
    
    rag_prompt, search_query, docs, _ = prepare_rag_context(message, history)
    
    full_answer = ""
    first_token_time = None # متغير لحفظ زمن أول حرف
    
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
            
            # 3. نحدد زمن الرد للحفظ: TTFT إن وُجد، وإلا الزمن الكلي
            response_time_to_log = first_token_time if first_token_time is not None else (time.time() - start_time)

        except Exception as e:
            yield f"Error: {str(e)}"
            response_time_to_log = time.time() - start_time # زمن الخطأ
            
    # 4. الحفظ الموحد والوحيد في قاعدة البيانات
    try:
        new_log = models.ChatLog(
            user_query=message,
            bot_answer=full_answer,
            response_time=response_time_to_log, # <--- تم حفظ القيمة الموحدة (TTFT أو الكلي)
            timestamp=datetime.now()
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

# 2. الـ Chat API
@app.post("/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    if MAINTENANCE_MODE:
        async def msg(): yield "عذراً، النظام يخضع للتحديث حالياً. يرجى تحديث الصفحة."
        return StreamingResponse(msg(), media_type="text/plain")
        
    return StreamingResponse(
        generate_response_stream(request.message, request.history, db),
        media_type="text/plain"
    )

# 3. لوحة التحكم - الصفحة الرئيسية (Maintenance & Control)
@app.get("/admin/maintenance", response_class=HTMLResponse)
def maintenance_page(request: Request, username: str = Depends(get_current_admin)):
    stats = get_chroma_stats()
    return templates.TemplateResponse("maintenance.html", {
        "request": request,
        "is_maintenance": MAINTENANCE_MODE,
        "db_stats": stats
    })

# 4. زر التحكم اليدوي في الصيانة (On/Off)
@app.post("/admin/toggle-maintenance")
async def toggle_maintenance(request: Request, username: str = Depends(get_current_admin)):
    global MAINTENANCE_MODE
    form_data = await request.form()
    state = form_data.get("state")
    
    if state == "on":
        MAINTENANCE_MODE = True
    elif state == "off":
        MAINTENANCE_MODE = False
    
    # إعادة توجيه لنفس الصفحة لتحديث الحالة
    stats = get_chroma_stats()
    return templates.TemplateResponse("maintenance.html", {
        "request": request,
        "is_maintenance": MAINTENANCE_MODE,
        "db_stats": stats
    })

# 5. رفع قاعدة البيانات (Upload DB)
@app.post("/admin/upload-db")
async def upload_db(request: Request, file: UploadFile = File(...), username: str = Depends(get_current_admin)):
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = True # تفعيل الصيانة تلقائياً أثناء الرفع
    try:
        temp_zip = "temp.zip"
        with open(temp_zip, "wb") as b:
            shutil.copyfileobj(file.file, b)
            
        if os.path.exists(CHROMA_PATH):
            try: shutil.rmtree(CHROMA_PATH)
            except: pass
            
        with zipfile.ZipFile(temp_zip, 'r') as z:
            z.extractall(".")
            
        os.remove(temp_zip)
        reload_vector_store()
        
        stats = get_chroma_stats()
        return templates.TemplateResponse("maintenance.html", {
            "request": request, 
            "is_maintenance": False, # إيقاف الصيانة بعد النجاح
            "db_stats": stats,
            "message": "تم تحديث قاعدة البيانات بنجاح!"
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        MAINTENANCE_MODE = False

# 6. لوحة الإحصائيات (KPI)
@app.get("/admin/kpi", response_class=HTMLResponse)
def kpi_dashboard(request: Request, db: Session = Depends(get_db), username: str = Depends(get_current_admin)):
    # 1. جلب آخر 50 سجل للعرض في الجدول
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).limit(50).all()
    
    # 2. جلب العدد الكلي للمحادثات
    total_chats = db.query(models.ChatLog).count()
    
    # --- الحسابات الجديدة ---
    avg_speed_all = 0      # متوسط الكل
    avg_speed_last_10 = 0  # متوسط آخر 10
    
    if total_chats > 0:
        # أ) حساب المتوسط الكلي (لجميع البيانات في الجدول)
        # ملاحظة: لجلب متوسط الكل بدقة يفضل استخدام دالة SQL func.avg لكن للتبسيط سنحسبها بايثون
        all_logs = db.query(models.ChatLog.response_time).all() # نجلب فقط عمود الوقت للتخفيف
        all_times = [r[0] for r in all_logs if r[0] is not None]
        if all_times:
            avg_speed_all = sum(all_times) / len(all_times)

        # ب) حساب متوسط آخر 10 محادثات فقط
        last_10_logs = db.query(models.ChatLog.response_time).order_by(models.ChatLog.timestamp.desc()).limit(10).all()
        last_10_times = [r[0] for r in last_10_logs if r[0] is not None]
        if last_10_times:
            avg_speed_last_10 = sum(last_10_times) / len(last_10_times)

    return templates.TemplateResponse("kpi.html", {
        "request": request,
        "logs": logs,
        "total_chats": total_chats,
        "avg_speed_all": round(avg_speed_all, 2),       # الرقم الأول
        "avg_speed_last_10": round(avg_speed_last_10, 2), # الرقم الثاني
        "now": datetime.now()
    })

# 7. تفاصيل محادثة واحدة (عرض التقرير الفردي)
@app.get("/admin/kpi/{log_id}", response_class=HTMLResponse)
def view_chat_log(log_id: int, request: Request, db: Session = Depends(get_db), username: str = Depends(get_current_admin)):
    log = db.query(models.ChatLog).filter(models.ChatLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return templates.TemplateResponse("chat_details.html", {
        "request": request,
        "log": log
    })

# 8. تحميل البيانات (CSV/Excel)
@app.get("/admin/export-csv")
def export_logs_csv(db: Session = Depends(get_db), username: str = Depends(get_current_admin)):
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).all()
    
    output = io.StringIO()
    output.write('\ufeff') # دعم اللغة العربية في Excel
    writer = csv.writer(output)
    writer.writerow(["ID", "Date", "Time", "User Question", "Bot Answer", "Response Time (s)"])
    
    for log in logs:
        writer.writerow([
            log.id,
            log.timestamp.strftime('%Y-%m-%d'),
            log.timestamp.strftime('%H:%M:%S'),
            log.user_query,
            log.bot_answer,
            f"{log.response_time:.2f}"
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chat_logs_report.csv"}
    )


# 9. التقرير الشامل (عرض أو تحميل)
@app.get("/admin/full-report") # أزلنا response_class هنا لنتمكن من التحكم في النوع يدوياً
def full_report_page(
    request: Request, 
    download: bool = False, # متغير جديد للتحكم
    db: Session = Depends(get_db), 
    username: str = Depends(get_current_admin)
):
    logs = db.query(models.ChatLog).order_by(models.ChatLog.timestamp.desc()).all()
    
    context = {
        "request": request,
        "logs": logs,
        "generated_at": datetime.now()
    }

    # إذا طلب المستخدم التنزيل (download=True)
    if download:
        # نقوم بتحويل القالب إلى نص HTML كامل
        html_content = templates.get_template("full_report.html").render(context)
        
        # نرسله كملف للتحميل
        return HTMLResponse(
            content=html_content,
            headers={
                "Content-Disposition": f"attachment; filename=full_report_{datetime.now().strftime('%Y-%m-%d')}.html"
            }
        )

    # العرض العادي (في المتصفح)
    return templates.TemplateResponse("full_report.html", context)

# ---10 endpoint جديد لحذف سجل واحد ---
@app.delete("/admin/kpi/delete/{log_id}")
def delete_chat_log(log_id: int, db: Session = Depends(get_db), username: str = Depends(get_current_admin)):
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
    
    return {
        "maintenance_mode": MAINTENANCE_MODE,
        "db_stats": get_chroma_stats()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)