from database import SessionLocal
from models import DashboardUser
import hashlib

# ---------------------------------------------------------------------------
# Change these before running
# ---------------------------------------------------------------------------
ADMIN_USERNAME = "mohanad"
ADMIN_PASSWORD = "Elhonda123@#"
# ---------------------------------------------------------------------------

db = SessionLocal()

# Check if user already exists
existing = db.query(DashboardUser).filter(DashboardUser.username == ADMIN_USERNAME).first()
if existing:
    print(f"[!] User '{ADMIN_USERNAME}' already exists. Skipping.")
else:
    user = DashboardUser(
        username=ADMIN_USERNAME,
        hashed_password=hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
        role="admin",
        is_active=True
    )
    db.add(user)
    db.commit()
    print(f"[✓] Admin user '{ADMIN_USERNAME}' created successfully!")

db.close()