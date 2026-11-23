import os
from app import app, ensure_db_schema

if __name__ == "__main__":
    ensure_db_schema()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
