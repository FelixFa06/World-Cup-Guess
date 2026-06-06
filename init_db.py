"""Initialize database with tables and admin user."""
from app import create_app
from models import db, User
from config import Config
from sqlalchemy import text

app = create_app()

with app.app_context():
    db.create_all()
    print("Tables created.")

    # Migrate: add previous_rank column if missing
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN previous_rank INTEGER"))
        db.session.commit()
        print("Column previous_rank added to users table.")
    except Exception:
        print("Column previous_rank already exists (or migration skipped).")

    admin = User.query.filter_by(nickname=Config.ADMIN_NICKNAME).first()
    if not admin:
        admin = User(nickname=Config.ADMIN_NICKNAME, is_admin=True)
        admin.set_password(Config.ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        print(f"Admin user created: {Config.ADMIN_NICKNAME}")
    else:
        print(f"Admin user already exists: {Config.ADMIN_NICKNAME}")

    print("Database initialized successfully!")
