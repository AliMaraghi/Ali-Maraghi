import http.server, socketserver, json, sqlite3, time

DB_PATH = "/home/apexdev/apex-work/runtime/kernel.sqlite3"

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ['/api/telemetry', '/api/agent_telemetry']:
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT agent_id, name, domain, status, last_run_ts, schedule_seconds FROM agent_schedule ORDER BY agent_id")
                rows = c.fetchall()
                conn.close()
                now = time.time()
                agents = []
                for r in rows:
                    due_in = max(0, int(r[5] - (now - r[4]))) if r[4] > 0 else int(r[5])
                    agents.append({
                        "agent_id": r[0], "name": r[1], "domain": r[2],
                        "status": r[3], "due_in_seconds": due_in,
                        "last_run_at": r[4]
                    })
                payload = json.dumps({"agents": agents, "total": len(agents), "timestamp": now})
            except Exception as e:
                payload = json.dumps({"error": str(e)})
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', 'https://ui.apexcorelab.uk')
            self.end_headers()
            self.wfile.write(payload.encode())
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    print("Telemetry API on 127.0.0.1:8084")
    socketserver.TCPServer(("127.0.0.1", 8084), Handler).serve_forever()
