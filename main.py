import sqlite3
import os
from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def init_db():
    conn = sqlite3.connect("flow_chat.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, status TEXT DEFAULT 'idle')")
    cursor.execute("CREATE TABLE IF NOT EXISTS messages (room_id TEXT, user TEXT, text TEXT)")
    # טבלת חדרים כוללת את הלוח (board) והתור הנוכחי (turn)
    cursor.execute("CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, u1 TEXT, u2 TEXT, board TEXT DEFAULT '.........', turn TEXT DEFAULT 'X')")
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

@app.post("/api/login")
async def login(data: dict = Body(...)):
    user = data.get('username')
    conn = sqlite3.connect("flow_chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (username, status) VALUES (?, 'idle')", (user,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/match/{username}")
async def find_match(username: str):
    conn = sqlite3.connect("flow_chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, u1, u2 FROM rooms WHERE u1 = ? OR u2 = ?", (username, username))
    room = cursor.fetchone()
    if room:
        partner = room[1] if room[2] == username else room[2]
        conn.close()
        return {"room_id": room[0], "partner": partner}

    cursor.execute("SELECT username FROM users WHERE status = 'idle' AND username != ? LIMIT 1", (username,))
    match = cursor.fetchone()
    if match:
        partner = match[0]
        room_id = f"room_{min(username, partner)}_{max(username, partner)}"
        cursor.execute("INSERT OR IGNORE INTO rooms (id, u1, u2) VALUES (?, ?, ?)", (room_id, username, partner))
        cursor.execute("UPDATE users SET status = 'busy' WHERE username IN (?, ?)", (username, partner))
        conn.commit()
        conn.close()
        return {"room_id": room_id, "partner": partner}
    conn.close()
    return {"status": "searching"}

# --- לוגיקת המשחק ---
@app.get("/api/game/{room_id}")
async def get_game(room_id: str):
    conn = sqlite3.connect("flow_chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT board, turn FROM rooms WHERE id = ?", (room_id,))
    res = cursor.fetchone()
    conn.close()
    return {"board": res[0], "turn": res[1]} if res else {"board": ".........", "turn": "X"}

@app.post("/api/game/{room_id}/move")
async def make_move(room_id: str, data: dict = Body(...)):
    conn = sqlite3.connect("flow_chat.db")
    cursor = conn.cursor()
    next_turn = "O" if data['char'] == "X" else "X"
    cursor.execute("UPDATE rooms SET board = ?, turn = ? WHERE id = ?", (data['board'], next_turn, room_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# --- צ'אט ---
@app.post("/api/chat/{room_id}")
async def send_msg(room_id: str, data: dict = Body(...)):
    conn = sqlite3.connect("flow_chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages VALUES (?, ?, ?)", (room_id, data['user'], data['text']))
    conn.commit()
    conn.close()
    return {"status": "sent"}

@app.get("/api/chat/{room_id}")
async def get_msgs(room_id: str):
    conn = sqlite3.connect("flow_chat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT user, text FROM messages WHERE room_id = ?", (room_id,))
    msgs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return msgs

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)