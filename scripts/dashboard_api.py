import http.server, socketserver, json, sqlite3

DB_PATH = "/home/apexdev/apex-work/runtime/kernel.sqlite3"

class DashboardAPI(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/stats':
            # در اینجا از دیتابیس واقعی می‌خوانیم
            # (چون فعلا دیتابیس ایجنت‌ها را برای تست خالی است، داده‌های نمونه برمی‌گردانیم)
            data = {
                "agents": [
                    {"id": "A-1", "name": "Strategic", "status": "ACTIVE", "last_action": "Analyzed market trends", "articles_read": 0},
                    {"id": "A-2", "name": "Research", "status": "ACTIVE", "last_action": "Searched PubMed for AI", "articles_read": 14},
                    {"id": "A-5", "name": "Career", "status": "IDLE", "last_action": "Scanned LinkedIn (mock)", "articles_read": 0},
                    {"id": "A-8", "name": "Finance", "status": "IDLE", "last_action": "Calculated ESPP scenario", "articles_read": 0}
                ],
                "system": {"budget_used": "$0.05", "uptime": "2 hours"}
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    print("Dashboard API running on port 8083")
    socketserver.TCPServer(("", 8083), DashboardAPI).serve_forever()
