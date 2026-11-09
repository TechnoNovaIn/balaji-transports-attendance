from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app, db

with app.app_context():
    db.create_all()
    print(f"Database initialized: {app.config['SQLALCHEMY_DATABASE_URI']}")
