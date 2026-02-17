import sqlite3
import os
import time
from fastapi import FastAPI, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

def get_db():
    conn = sqlite3.connect("flow_chat.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # יצירת טבלאות עם כל העמודות מההתחלה
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, 
            status TEXT DEFAULT 'idle', 
            last_seen REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            room_id TEXT, 
            user TEXT, 
            text TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY, 
            u1 TEXT, 
            u2 TEXT, 
            board TEXT DEFAULT '.........', 
            turn TEXT DEFAULT 'X', 
            last_activity REAL
        )
    """)
    conn.commit()
    conn.close()

# הרצה של היצירה מיד עם עליית השרת
init_db()

def cleanup_and_stats():
    try:
        conn = get_db()
        cursor = conn.cursor()
        now = time.time()
        
        # מחיקת ישנים (רק אם הטבלה קיימת)
        cursor.execute("DELETE FROM messages WHERE room_id IN (SELECT id FROM rooms WHERE last_activity < ?)", (now - 600,))
        cursor.execute("DELETE FROM rooms WHERE last_activity < ?", (now - 600,))
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE last_seen > ?", (now - 300,))
        res = cursor.fetchone()
        count = res[0] if res else 0
        
        conn.commit()
        conn.close()
        return count
    except:
        return 0

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

@app.get("/api/stats")
async def get_stats():
    count = cleanup_and_stats()
    return {"online_users": count}

@app.post("/api/login")
async def login(request: Request, data: dict = Body(...)):
    user = data.get('username')
    client_ip = request.client.host
    print(f"🚀 LOGIN: {user} from {client_ip}")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (username, status, last_seen) VALUES (?, 'idle', ?)", (user, time.time()))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/match/{username}")
async def find_match(username: str):
    conn = get_db()
    cursor = conn.cursor()
    
    # עדכון זמן נראה לאחרונה
    cursor.execute("UPDATE users SET last_seen = ? WHERE username = ?", (time.time(), username))
    
    cursor.execute("SELECT id, u1, u2 FROM rooms WHERE u1 = ? OR u2 = ?", (username, username))
    room = cursor.fetchone()
    if room:
        partner = room['u1'] if room['u2'] == username else room['u2']
        conn.close()
        return {"room_id": room['id'], "partner": partner}

    cursor.execute("SELECT username FROM users WHERE status = 'idle' AND username != ? LIMIT 1", (username,))
    match = cursor.fetchone()
    if match:
        partner = match['username']
        room_id = f"room_{min(username, partner)}_{max(username, partner)}"
        cursor.execute("INSERT OR IGNORE INTO rooms (id, u1, u2, last_activity) VALUES (?, ?, ?, ?)", 
                       (room_id, username, partner, time.time()))
        cursor.execute("UPDATE users SET status = 'busy' WHERE username IN (?, ?)", (username, partner))
        conn.commit()
        conn.close()
        return {"room_id": room_id, "partner": partner}
    
    conn.commit()
    conn.close()
    return {"status": "searching"}

@app.get("/api/game/{room_id}")
async def get_game(room_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT board, turn FROM rooms WHERE id = ?", (room_id,))
    res = cursor.fetchone()
    conn.close()
    return {"board": res['board'], "turn": res['turn']} if res else {"board": ".........", "turn": "X"}

@app.post("/api/game/{room_id}/move")
async def make_move(room_id: str, data: dict = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    next_turn = "O" if data['char'] == "X" else "X"
    cursor.execute("UPDATE rooms SET board = ?, turn = ?, last_activity = ? WHERE id = ?", 
                   (data['board'], next_turn, time.time(), room_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/api/chat/{room_id}")
async def send_msg(room_id: str, data: dict = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (room_id, user, text) VALUES (?, ?, ?)", (room_id, data['user'], data['text']))
    cursor.execute("UPDATE rooms SET last_activity = ? WHERE id = ?", (time.time(), room_id))
    conn.commit()
    conn.close()
    return {"status": "sent"}

@app.get("/api/chat/{room_id}")
async def get_msgs(room_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user, text FROM messages WHERE room_id = ?", (room_id,))
    msgs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return msgs

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)