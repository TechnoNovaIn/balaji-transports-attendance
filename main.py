import os
from app import app, ensure_db_schema

if __name__ == "__main__":
    ensure_db_schema()
    port = int(os.environ.get("PORT", "5000"))
    is_debug = os.environ.get("FLASK_DEBUG") == "1"
    is_production = os.environ.get("FLASK_ENV", "production").lower() == "production"
    if is_production and not is_debug:
        try:
            from waitress import serve
            serve(app, host="0.0.0.0", port=port)
        except ImportError:
            app.logger.warning(
                "Waitress is not installed; falling back to Flask development server. "
                "Use Gunicorn (Procfile) or Waitress in production."
            )
            app.run(host="0.0.0.0", port=port, debug=False)
    else:
        app.run(host="0.0.0.0", port=port, debug=is_debug)
