from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# اسم ملف قاعدة البيانات الذي سيتم إنشاؤه تلقائياً
SQLALCHEMY_DATABASE_URL = "sqlite:////tmp/kpi_data.db"

# إنشاء المحرك (Engine)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# إنشاء جلسة العمل (Session)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# الأساس للكلاسات (Models)
Base = declarative_base()

# دالة مساعدة للحصول على الاتصال بالداتا بيز (سنستخدمها في main.py)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()