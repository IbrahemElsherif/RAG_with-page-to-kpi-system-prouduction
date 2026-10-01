# This file will serve as the 'brain' of the project, containing ChromaDB, the RAG engine, and background tasks
import os
import json
import time
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from sqlalchemy.orm import Session

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from chromadb.config import Settings

import models
from database import engine, SessionLocal

# AI Models & Vector Store Configuration
models.Base.metadata.create_all(bind=engine)
BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH_ENV = os.getenv("CHROMA_PATH")

if CHROMA_PATH_ENV:
    CHROMA_PATH = Path(CHROMA_PATH_ENV)
else:
    CHROMA_PATH = BASE_DIR / "data" / "chroma_db"

COLLECTION_NAME = "example_collection"

# Cost-control caps for background LLM classification tasks — keep these
# prompts flat-sized regardless of how much history the app accumulates.
RECENT_TOPICS_SCAN_ROWS = 200   # how many recent chat_logs rows to scan for topics
RECENT_TOPICS_LIMIT = 30        # max distinct topics sent to the topic classifier
INTENT_HISTORY_LIMIT = 15       # max recent user messages sent to intent detection

embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(temperature=0.1, model="gpt-4o-mini")
vector_store = None

# Global Facts for RAG
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


def _compute_lead_status(question_count: int, asked_price: bool, asked_reg: bool) -> str:
    if asked_price or asked_reg:
        return "hot"
    if question_count >= 5:
        return "warm"
    return "cold"

# Vector store helpers
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


def ingest_pdfs(pdf_bytes_list: List[bytes], filenames: List[str],
                chunk_size: int = 1000, chunk_overlap: int = 200) -> dict:
    global vector_store

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)

    if vector_store is None:
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings_model,
            persist_directory=str(CHROMA_PATH),
            client_settings=Settings(anonymized_telemetry=False),
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    total_pages = 0
    total_chunks = 0

    for pdf_bytes, filename in zip(pdf_bytes_list, filenames):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            loader = PyPDFLoader(tmp_path)
            pages = loader.load()
            total_pages += len(pages)

            for page in pages:
                page.metadata["source"] = filename

            chunks = splitter.split_documents(pages)
            total_chunks += len(chunks)
            vector_store.add_documents(chunks)
            print(f"--- [INGEST] {filename}: {len(pages)} pages → {len(chunks)} chunks ---")
        finally:
            os.unlink(tmp_path)

    return {
        "files": len(pdf_bytes_list),
        "pages": total_pages,
        "chunks": total_chunks,
        "total_documents": vector_store._collection.count(),
    }


# Initialize on import
load_vector_store()

# Background task: classify question category with GPT
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
        # Scan only the most recent rows and dedupe in Python, so this prompt
        # stays flat-sized regardless of how many topics have accumulated
        # over the app's lifetime (recent topics are what matter for clustering).
        recent_logs = (
            db.query(models.ChatLog.topic)
            .filter(models.ChatLog.topic != None)
            .order_by(models.ChatLog.timestamp.desc())
            .limit(RECENT_TOPICS_SCAN_ROWS)
            .all()
        )
        topics_list = []
        for (t,) in recent_logs:
            if t and t not in topics_list:
                topics_list.append(t)
            if len(topics_list) >= RECENT_TOPICS_LIMIT:
                break

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
        else: ### no set of categories the model define thems ###
            topic_prompt = f"""
                            Create a short Arabic topic name (max 4 words) for this question:
                            "{question}"

                            Return ONLY the topic name, nothing else.
                            """
        topic_response = await llm.ainvoke(topic_prompt)
        topic = topic_response.content.strip()

        # Save to DB 
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

        # 2. جلب آخر أسئلة العميل فقط في هذه الجلسة (بدون ردود البوت)
        # Capped to the most recent N messages so this prompt stays flat-sized
        # instead of growing (and re-billing) with total session length.
        recent_user_logs = (
            db.query(models.ChatLog.user_query)
            .filter(models.ChatLog.session_id == session_id)
            .order_by(models.ChatLog.timestamp.desc())
            .limit(INTENT_HISTORY_LIMIT)
            .all()
        )

        if not recent_user_logs:
            return

        # تجميع أسئلة العميل في نص واحد (بترتيب زمني تصاعدي)
        user_questions_text = "\n".join(
            [f"- {log[0]}" for log in reversed(recent_user_logs) if log[0]]
        )

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


# RAG Core Logic
async def prepare_rag_context(message: str, history: List[Tuple[str, str]]):
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
            rephrase_response = await llm.ainvoke(rephrase_prompt)
            search_query = rephrase_response.content.strip()
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
                3. For pricing or registration questions, share: unified number 920012673 and WhatsApp 0530287098.
                4. Be direct and concise.

                User: {message}
                Assistant:
                """


    return rag_prompt, search_query, good_docs, limited_history


async def generate_response_stream(
    message: str, history: List[Tuple[str, str]], session_id: str, db: Session
):
    start_time = time.time()

    rag_prompt, search_query, docs, _ = await prepare_rag_context(message, history)

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
            retrieved_context="\n\n".join(docs) if docs else None,
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        
        eval_data = {
            "log_type": "RAG_EVAL",
            "question": message,
            "context": docs,
            "answer": full_answer
        }

        print(json.dumps(eval_data, ensure_ascii=False), flush=True)
        print(f"--- [LOG] Response Time Saved: {response_time_to_log:.2f}s ---")
        asyncio.create_task(classify_question_background(new_log.id, message))
        asyncio.create_task(detect_intent_background(session_id, message))

    except Exception as e:
        print(f"--- [ERROR] DB Save failed: {e} ---")