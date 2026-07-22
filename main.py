from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymongo import MongoClient
from groq import Groq
from dotenv import load_dotenv
import os
import json
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

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client[os.getenv("DATABASE_NAME")]
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


def analyze_feedback_with_ai(feedback_text: str):
    prompt = f"""You are an HR analytics assistant. Analyze the following employee feedback.

Feedback: "{feedback_text}"

Return ONLY a valid JSON object (no extra text, no markdown) with these exact keys:
{{
  "sentiment": "Positive" or "Negative" or "Neutral",
  "category": one of ["Workload", "Management", "Salary", "Work-Life Balance", "Growth", "Other"],
  "risk_score": a number from 0 to 100 (0 = no risk of employee dissatisfaction, 100 = very high risk),
  "summary": "one short sentence summarizing the key concern or praise",
  "recommended_action": "one short, specific, actionable recommendation for the HR manager to address this feedback (e.g. 'Schedule a 1:1 to discuss workload distribution')"
}}
"""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    result_text = response.choices[0].message.content.strip()
    result_text = result_text.replace("```json", "").replace("```", "").strip()
    return json.loads(result_text)


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
        analysis = analyze_feedback_with_ai(feedback.feedback_text)

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

    # Simple trend signal: compare avg risk of the most recent half of
    # submissions vs the earlier half, so the dashboard can flag whether
    # things are getting better or worse over time.
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

        context_data = json.dumps(records[-30:], indent=2) if records else "No feedback data available yet."

        prompt = f"""You are RetainIQ, an HR analytics assistant agent. You have access to employee feedback data below.

Feedback Data:
{context_data}

HR Manager's Question: "{query.question}"

Answer the question clearly and concisely based ONLY on the data provided above. If the data doesn't contain enough information to answer, say so honestly. Keep your answer short (2-4 sentences), professional, and actionable for an HR manager.
"""
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        answer = response.choices[0].message.content.strip()
        return {"success": True, "answer": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory="static", html=True), name="static")