from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from database import Base
from datetime import datetime


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_query = Column(String, index=True)
    bot_answer = Column(Text)
    response_time = Column(Float)
    category = Column(String, nullable=True)
    is_unanswered = Column(Boolean, default=False)
    topic = Column(String, nullable=True, index=True)




class Lead(Base):
    """
    Automatically recorded when the user enters their data in the chat popup.
    Everything starts with pending=True until approved from the trackdashboard.
    """
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)            # Linked to chat session
    phone_number = Column(String)                      # Mobile number
    
    # New fields added for the frontend dropdowns
    is_registered = Column(String, nullable=True)      # Expected: 'yes' or 'no'
    city = Column(String, nullable=True)               # Expected: 'Riyadh', 'Jeddah', etc.
    
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Automated analysis fields
    question_count = Column(Integer, default=0)        # Number of questions in the session
    asked_about_price = Column(Boolean, default=False)       # Asked about price?
    asked_about_registration = Column(Boolean, default=False)# Asked about registration?

    # Lead status (hot/warm/cold) - calculated automatically
    lead_status = Column(String, default="cold")       # hot / warm / cold

    # Approval system - controlled by admin
    is_approved = Column(Boolean, default=False)       # False = pending, True = visible to sales
    approved_at = Column(DateTime, nullable=True)      # Approval time
    admin_note = Column(Text, nullable=True)           # Personal note on the lead
    session_summary = Column(String, nullable=True)

class WeeklyNote(Base):
    """
    الملاحظة الأسبوعية اللي أنت بتكتبها من الـ trackdashboard.
    المبيعات بيشوفوها في أعلى الـ dashboard.
    """
    __tablename__ = "weekly_notes"

    id = Column(Integer, primary_key=True, index=True)
    week_number = Column(Integer)                     # رقم الأسبوع
    year = Column(Integer)
    content = Column(Text)                            # نص الملاحظة
    is_published = Column(Boolean, default=False)     # أنت بتقرر امتى تنشرها
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)


class DashboardSection(Base):
    """
    التحكم في إيه اللي يظهر في الـ dashboard.
    كل section عنده مفتاح تشغيل/إيقاف أنت بتتحكم فيه.
    """
    __tablename__ = "dashboard_sections"

    id = Column(Integer, primary_key=True, index=True)
    section_key = Column(String, unique=True)         # مثال: "peak_hours", "unanswered_questions"
    section_name = Column(String)                     # الاسم بالعربي للعرض
    is_visible = Column(Boolean, default=False)       # مخفي افتراضياً حتى أنت تفعّله
    last_updated = Column(DateTime, default=datetime.utcnow)


class DashboardUser(Base):
    """
    يوزرات الـ dashboard — أنت بتعملهم من الـ trackdashboard.
    role: 'admin' = أنت | 'sales' = تيم المبيعات
    """
    __tablename__ = "dashboard_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="sales")            # admin / sales
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

class ReportRequest(Base):
    """
    Created when sales team clicks 'request report' in the dashboard.
    Shows as a notification in trackdashboard until admin marks it as seen.
    """
    __tablename__ = "report_requests"

    id = Column(Integer, primary_key=True, index=True)
    requested_by = Column(String)                      # username of sales user
    report_type = Column(String)                       # "leads", "questions", "peak_hours"
    week_number = Column(Integer)
    year = Column(Integer)
    note = Column(Text, nullable=True)                 # optional message from sales
    is_seen = Column(Boolean, default=False)           # False = unread notification
    created_at = Column(DateTime, default=datetime.utcnow)
    seen_at = Column(DateTime, nullable=True)

class UploadedReport(Base):
    """
    Stores HTML reports uploaded by admin from trackdashboard.
    report_type: 'questions' / 'peak_hours' / etc.
    """
    __tablename__ = "uploaded_reports"

    id          = Column(Integer, primary_key=True, index=True)
    report_type = Column(String, index=True)
    filename    = Column(String)
    html_content = Column(Text)
    week_number = Column(Integer)
    year        = Column(Integer)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    request_id = Column(Integer, nullable=True)
    report_period = Column(String, nullable=True)  
    period_label  = Column(String, nullable=True)
class QuestionCategory(Base):
    __tablename__ = "question_categories"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String)           
    description = Column(Text)           
    is_visible  = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)