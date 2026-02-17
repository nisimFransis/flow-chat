import sqlite3
import os
import time
from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# פונקציה לעבודה נוחה עם DB
def get_db():
    conn = sqlite3.connect("flow_chat.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, status TEXT DEFAULT 'idle', last_seen REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS messages (room_id TEXT, user TEXT, text TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, u1 TEXT, u2 TEXT, board TEXT DEFAULT '.........', turn TEXT DEFAULT 'X', last_activity REAL)")
    conn.commit()
    conn.close()

init_db()

# --- פונקציית ניקוי חדרים ומשתמשים לא פעילים ---
def cleanup_old_data():
    conn = get_db()
    cursor = conn.cursor()
    ten_minutes_ago = time.time() - 600
    
    # מחיקת הודעות בחדרים שלא היו פעילים 10 דקות
    cursor.execute("DELETE FROM messages WHERE room_id IN (SELECT id FROM rooms WHERE last_activity < ?)", (ten_minutes_ago,))
    # מחיקת החדרים עצמם
    cursor.execute("DELETE FROM rooms WHERE last_activity < ?", (ten_minutes_ago,))
    # החזרת משתמשים ל-idle אם הם נעלמו
    cursor.execute("UPDATE users SET status = 'idle' WHERE last_seen < ?", (ten_minutes_ago,))
    
    conn.commit()
    conn.close()

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

@app.post("/api/login")
async def login(data: dict = Body(...)):
    cleanup_old_data() # מנקה נתונים ישנים בכל כניסה חדשה
    user = data.get('username')
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
    
    # עדכון זמן פעילות אחרון של המשתמש
    cursor.execute("UPDATE users SET last_seen = ? WHERE username = ?", (time.time(), username))
    
    # חיפוש חדר קיים
    cursor.execute("SELECT id, u1, u2 FROM rooms WHERE u1 = ? OR u2 = ?", (username, username))
    room = cursor.fetchone()
    if room:
        partner = room['u1'] if room['u2'] == username else room['u2']
        conn.close()
        return {"room_id": room['id'], "partner": partner}

    # חיפוש פרטנר פנוי
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

# --- לוגיקת המשחק ---
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
    cursor.execute("UPDATE rooms SET board