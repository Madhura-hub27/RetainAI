from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import certifi
import hashlib
from datetime import datetime

load_dotenv()

app = FastAPI(title="Employee Feedback Intelligence Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

mongo_uri = os.getenv("MONGO_URI")
if mongo_uri and mongo_uri.startswith("mongodb+srv://"):
    mongo_client = MongoClient(mongo_uri, tlsCAFile=certifi.where())
else:
    mongo_client = MongoClient(mongo_uri)
db = mongo_client[os.getenv("DATABASE_NAME", "retainiq_db")]
feedback_collection = db["feedback"]
users_collection = db["users"]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


class FeedbackInput(BaseModel):
    employee_name: str
    department: str
    feedback_text: str
    anonymous: bool = False


class UserAuth(BaseModel):
    username: str
    password: str


class ChatQuery(BaseModel):
    question: str


def analyze_feedback_locally(feedback_text: str):
    text_lower = feedback_text.lower()
    
    # Simple smart keyword analysis
    negative_words = ["overtime", "stress", "tired", "bad", "poor", "issue", "problem", "leave", "resign", "unhappy", "workload", "mental"]
    positive_words = ["good", "great", "excellent", "happy", "love", "thanks", "helpful", "awesome", "fantastic"]
    
    neg_count = sum(1 for w in negative_words if w in text_lower)
    pos_count = sum(1 for w in positive_words if w in text_lower)
    
    if neg_count > pos_count:
        sentiment = "Negative"
        risk_score = min(75 + (neg_count * 5), 95)
    elif pos_count > neg_count:
        sentiment = "Positive"
        risk_score = 10
    else:
        sentiment = "Neutral"
        risk_score = 40

    # Category matching
    if any(w in text_lower for w in ["salary", "pay", "money", "bonus"]):
        category = "Salary"
    elif any(w in text_lower for w in ["manager", "boss", "management", "lead"]):
        category = "Management"
    elif any(w in text_lower for w in ["workload", "hours", "overtime", "balance", "time"]):
        category = "Work-Life Balance"
    elif any(w in text_lower for w in ["grow", "career", "promotion", "learn"]):
        category = "Growth"
    else:
        category = "Other"

    return {
        "sentiment": sentiment,
        "category": category,
        "risk_score": risk_score,
        "summary": f"Feedback categorized under {category} with {sentiment.lower()} sentiment.",
        "recommended_action": f"HR should schedule a 1-on-1 discussion regarding {category.lower()} concerns."
    }


@app.get("/api")
def home():
    return {"message": "Employee Feedback Intelligence Agent is running"}


@app.post("/register")
def register(user: UserAuth):
    existing = users_collection.find_one({"username": user.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    users_collection.insert_one({
        "username": user.username,
        "password": hash_password(user.password),
        "created_at": datetime.utcnow().isoformat()
    })
    return {"success": True, "message": "Registered successfully"}


@app.post("/login")
def login(user: UserAuth):
    found = users_collection.find_one({"username": user.username})
    if not found or found["password"] != hash_password(user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"success": True, "message": "Login successful", "username": user.username}


@app.post("/submit-feedback")
def submit_feedback(feedback: FeedbackInput):
    try:
        analysis = analyze_feedback_locally(feedback.feedback_text)

        display_name = "Anonymous" if feedback.anonymous else feedback.employee_name

        record = {
            "employee_name": display_name,
            "is_anonymous": feedback.anonymous,
            "department": feedback.department,
            "feedback_text": feedback.feedback_text,
            "sentiment": analysis["sentiment"],
            "category": analysis["category"],
            "risk_score": analysis["risk_score"],
            "summary": analysis["summary"],
            "recommended_action": analysis["recommended_action"],
            "created_at": datetime.utcnow().isoformat(),
        }

        feedback_collection.insert_one(record)
        record["_id"] = str(record.get("_id", ""))

        return {"success": True, "analysis": analysis}

    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/all-feedback")
def get_all_feedback():
    records = list(feedback_collection.find({}, {"_id": 0}))
    return {"count": len(records), "feedback": records}


@app.get("/dashboard-stats")
def dashboard_stats():
    records = list(feedback_collection.find({}, {"_id": 0}))
    if not records:
        return {
            "total": 0,
            "avg_risk_score": 0,
            "sentiment_breakdown": {},
            "category_breakdown": {},
            "department_risk_breakdown": {},
            "risk_trend": [],
        }

    total = len(records)
    avg_risk = sum(r["risk_score"] for r in records) / total

    sentiment_breakdown = {}
    category_breakdown = {}
    department_scores = {}
    for r in records:
        sentiment_breakdown[r["sentiment"]] = sentiment_breakdown.get(r["sentiment"], 0) + 1
        category_breakdown[r["category"]] = category_breakdown.get(r["category"], 0) + 1
        department_scores.setdefault(r["department"], []).append(r["risk_score"])

    department_risk_breakdown = {
        dept: round(sum(scores) / len(scores), 1) for dept, scores in department_scores.items()
    }

    sorted_records = sorted(records, key=lambda r: r.get("created_at", ""))
    midpoint = len(sorted_records) // 2
    risk_trend = []
    if midpoint > 0:
        earlier_avg = sum(r["risk_score"] for r in sorted_records[:midpoint]) / midpoint
        recent_avg = sum(r["risk_score"] for r in sorted_records[midpoint:]) / (len(sorted_records) - midpoint)
        direction = "up" if recent_avg > earlier_avg + 2 else ("down" if recent_avg < earlier_avg - 2 else "flat")
        risk_trend = {
            "earlier_avg": round(earlier_avg, 1),
            "recent_avg": round(recent_avg, 1),
            "direction": direction,
        }

    return {
        "total": total,
        "avg_risk_score": round(avg_risk, 2),
        "sentiment_breakdown": sentiment_breakdown,
        "category_breakdown": category_breakdown,
        "department_risk_breakdown": department_risk_breakdown,
        "risk_trend": risk_trend,
    }


@app.post("/ask-agent")
def ask_agent(query: ChatQuery):
    try:
        records = list(feedback_collection.find({}, {"_id": 0}))
        total_count = len(records)
        negative_count = sum(1 for r in records if r["sentiment"] == "Negative")
        
        answer = f"Based on the {total_count} records available, there are {negative_count} high-risk cases reported. Employees have shared concerns that require management attention."
        return {"success": True, "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory="static", html=True), name="static")