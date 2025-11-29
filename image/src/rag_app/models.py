from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from database import Base
from datetime import datetime

class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow) # وقت السؤال
    user_query = Column(String, index=True)               # سؤال المستخدم
    bot_answer = Column(Text)                             # إجابة البوت الكاملة
    response_time = Column(Float)                         # الوقت المستغرق بالثواني
    
    # يمكنك إضافة حقول إضافية مستقبلاً مثل:
    # user_rating = Column(Integer) # تقييم المستخدم للإجابة