#!/usr/bin/env python3
"""
Simple HTTP server for Case Intel frontend
Serves the frontend and handles CORS for backend communication
"""

import http.server
import socketserver
import os
import json
from urllib.parse import urlparse

PORT = 8080

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        print(f"""
╔═══════════════════════════════════════════════════════════╗
║           Case Intel Frontend Server                      ║
╚═══════════════════════════════════════════════════════════╝

🚀 Server running at: http://localhost:{PORT}
📋 Open browser at:  http://localhost:{PORT}

Backend API expects: http://localhost:8000/api

Press Ctrl+C to stop the server
        """)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n✓ Server stopped")
