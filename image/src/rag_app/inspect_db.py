from database import SessionLocal
from models import UploadedReport, ReportRequest

def inspect_data():
    db = SessionLocal()
    try:
        print("--- [ Uploaded Reports ] ---")
        reports = db.query(UploadedReport).filter(UploadedReport.report_type == 'peak_hours').all()
        if not reports:
            print("لا توجد تقارير مرفوعة حالياً.")
        for r in reports:
            # استخدمت getattr هنا لتجنب الخطأ لو كان هناك حقل ناقص في الموديل
            print(f"ID: {r.id} | Week: {getattr(r, 'week_number', 'N/A')} | Year: {r.year} | Label: {getattr(r, 'period_label', 'N/A')}")

        print("\n--- [ Report Requests ] ---")
        reqs = db.query(ReportRequest).all()
        if not reqs:
            print("لا توجد طلبات تقارير حالياً.")
        for r in reqs:
            print(f"REQ ID: {r.id} | Week: {r.week_number} | Year: {r.year} | Type: {r.report_type}")
            
    except Exception as e:
        print(f"حدث خطأ أثناء فحص البيانات: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inspect_data()