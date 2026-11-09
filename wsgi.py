"""WSGI entry point for Gunicorn on Render.

Usage:
    gunicorn wsgi:app
"""
from app import app
