from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path # 1. استيراد مكتبة المسارات

# 2. تحديد مسار المجلد الحالي اللي فيه ملف database.py
BASE_DIR = Path(__file__).resolve().parent

# 3. تحديد ملف الداتابيز الموجود فعلاً بجوار الكود
# (kpi_data.db) هو الاسم الظاهر عندك في الصورة
DB_FILE = BASE_DIR / "kpi_data.db"

# 4. تحويل المسار لصيغة يفهمها SQLAlchemy
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()