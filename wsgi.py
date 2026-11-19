"""WSGI Production Entry Point for Balaji Transports Workforce Application.

This module exposes the Flask application instance 'app' for standard WSGI servers
such as Waitress (Windows / Linux / cross-platform) and Gunicorn (Linux / containerized).

Production Startup Examples:
  - Cross-platform / Windows:
      python wsgi.py
      waitress-serve --port=5000 wsgi:app
  - Linux / Container:
      gunicorn --workers=2 --threads=4 --bind=0.0.0.0:5000 wsgi:app
"""
import os
from app import app

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting production WSGI server (Waitress) on http://{host}:{port}")
    serve(app, host=host, port=port)
