import sqlite3
from fastapi import FastAPI, HTTPException, Security, Depends, Query
from fastapi.security import APIKeyHeader

app = FastAPI(
    title="VeriStream Engine",
    description="Verified Proof-of-Watch Rating and Social Engine with API Key Protection",
    version="1.1"
)

# ---------------------------------------------------------
# API KEY AUTHENTICATION SETUP
# ---------------------------------------------------------
# Define the secret key streaming partners must send in their request header
API_KEY_NAME = "X-API-Key"
VALID_API_KEY = "veristream_secret_key_2026"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verify_api_key(api_key: str = Security(api_key_header)):
    """Validates incoming API keys. Rejects unauthorized calls with HTTP 401."""
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API Key."
        )
    return api_key

# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("veristream.db")
    cursor = conn.cursor()
    
    # Table for watch history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            user_id TEXT,
            episode_id TEXT,
            minutes_watched REAL,
            PRIMARY KEY (user_id, episode_id)
        )
    """)
    
    # Table for verified ratings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id TEXT,
            episode_id TEXT,
            score INTEGER,
            review_text TEXT,
            PRIMARY KEY (user_id, episode_id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# PUBLIC ENDPOINTS
# ---------------------------------------------------------

@app.get("/")
def home():
    """Public health check endpoint."""
    return {
        "system": "VeriStream Engine Online",
        "status": "Ready",
        "database": "Connected",
        "security": "API Key Enforced"
    }


# ---------------------------------------------------------
# PROTECTED ENGINE ENDPOINTS (Requires X-API-Key)
# ---------------------------------------------------------

@app.post("/log-watch-time", dependencies=[Depends(verify_api_key)])
def log_watch_time(user_id: str, episode_id: str, minutes: float):
    """Logs or increments watch time for a user on a specific episode."""
    conn = sqlite3.connect("veristream.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO watch_history (user_id, episode_id, minutes_watched)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, episode_id) DO UPDATE SET
        minutes_watched = minutes_watched + excluded.minutes_watched
    """, (user_id, episode_id, minutes))
    
    conn.commit()
    conn.close()
    
    return {"status": "Success", "message": f"Logged {minutes} minutes for user '{user_id}' on episode '{episode_id}'."}


@app.get("/check-watch-time", dependencies=[Depends(verify_api_key)])
def check_watch_time(user_id: str, episode_id: str):
    """Checks if a user has hit the 16.0-minute threshold to unlock rating features."""
    conn = sqlite3.connect("veristream.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT minutes_watched FROM watch_history 
        WHERE user_id = ? AND episode_id = ?
    """, (user_id, episode_id))
    
    result = cursor.fetchone()
    conn.close()
    
    minutes_watched = result[0] if result else 0.0
    
    if minutes_watched >= 16.0:
        return {
            "user_id": user_id,
            "episode_id": episode_id,
            "total_minutes_watched": minutes_watched,
            "verified": True,
            "rating_status": "UNLOCKED",
            "message": "Access granted. You may now rate this episode."
        }
    else:
        minutes_left = 16.0 - minutes_watched
        return {
            "user_id": user_id,
            "episode_id": episode_id,
            "total_minutes_watched": minutes_watched,
            "verified": False,
            "rating_status": "LOCKED",
            "message": f"Please watch {minutes_left:.1f} more minutes to unlock ratings."
        }


@app.post("/submit-rating", dependencies=[Depends(verify_api_key)])
def submit_rating(
    user_id: str, 
    episode_id: str, 
    score: int = Query(..., ge=1, le=10, description="Rating scale from 1 to 10"), 
    review_text: str = ""
):
    """Gated endpoint: Enforces the 16-minute proof-of-watch rule before accepting ratings."""
    conn = sqlite3.connect("veristream.db")
    cursor = conn.cursor()
    
    # 1. Verify watch time from database
    cursor.execute("""
        SELECT minutes_watched FROM watch_history 
        WHERE user_id = ? AND episode_id = ?
    """, (user_id, episode_id))
    
    result = cursor.fetchone()
    minutes_watched = result[0] if result else 0.0
    
    # 2. Gatekeeper Check
    if minutes_watched < 16.0:
        conn.close()
        raise HTTPException(
            status_code=403, 
            detail=f"Access Denied: You have only watched {minutes_watched:.1f} minutes. Must hit 16.0 minutes to leave a review."
        )
    
    # 3. Save Rating if Verified
    cursor.execute("""
        INSERT INTO ratings (user_id, episode_id, score, review_text)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, episode_id) DO UPDATE SET
        score = excluded.score,
        review_text = excluded.review_text
    """, (user_id, episode_id, score, review_text))
    
    conn.commit()
    conn.close()
    
    return {
        "status": "Success",
        "verified_badge": True,
        "message": f"Verified rating of {score}/10 recorded for episode '{episode_id}'!"
    }


@app.get("/get-episode-stats", dependencies=[Depends(verify_api_key)])
def get_episode_stats(episode_id: str):
    """Calculates average rating score using only verified viewers."""
    conn = sqlite3.connect("veristream.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT AVG(score), COUNT(score) FROM ratings 
        WHERE episode_id = ?
    """, (episode_id,))
    
    avg_score, total_ratings = cursor.fetchone()
    conn.close()
    
    return {
        "episode_id": episode_id,
        "verified_average_score": round(avg_score, 2) if avg_score else "No ratings yet",
        "total_verified_reviews": total_ratings
    }
