"""Web dashboard module for Text Watermark Studio.

Provides a browser-based UI using HTMX + Tailwind CSS (CDN, no build step)
with Jinja2 server-side rendering and SSE real-time stats.
"""

from .dashboard import mount_web_dashboard, router

__all__ = ["mount_web_dashboard", "router"]
