import datetime
import re
import os
import smtplib
import random
from email.mime.text import MIMEText
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, cast, Date, desc, text
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt
from dotenv import load_dotenv

# Import from our modules
from .database import engine, get_db, Base
from .models import User, BudgetConfig, Transaction, SavingsGoal, Notification, Sweep, FriendLedger, ChatMessage
from .ml_engine import FinanceAI
# Import the template function
from .email_templates import get_otp_email_html

load_dotenv()

# Create Tables
Base.metadata.create_all(bind=engine)

# --- AUTO MIGRATION FOR POSTGRES ---
def run_migrations():
    try:
        with engine.connect() as connection:
            if "postgres" in str(engine.url) or "postgresql" in str(engine.url):
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_secret VARCHAR;"))
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_expiry TIMESTAMP;"))
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;"))
                connection.commit()
                print("Database schema updated successfully.")
    except Exception as e:
        print(f"Migration skipped or failed (Safe to ignore if not using Postgres): {e}")

# CONFIGURATION
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey_change_me_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 3000
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# EMAIL CONFIGURATION
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

# --- SCHEMAS ---
class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str
    recaptcha_token: str

class UserLogin(BaseModel):
    email: str
    password: str
    recaptcha_token: str

class LoginVerifyRequest(BaseModel):
    email: str
    otp: str

class TransactionCreate(BaseModel):
    description: str
    amount: float
    type: str
    category: str
    date: Optional[str] = None

class BudgetSetup(BaseModel):
    monthly_income: float
    target_savings: float
    ai_mode: bool = False

class MagicImport(BaseModel):
    text: str

class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str

class ResendOTPRequest(BaseModel):
    email: str
    reason: str = "generic"

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

class DebtCreate(BaseModel):
    friend_name: str
    type: str
    amount: float
    description: Optional[str] = None
    date: Optional[str] = None

class DebtUpdate(BaseModel):
    amount: float
    status: str

class ChatLogRequest(BaseModel):
    role: str
    content: str

# --- UTILS ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def send_email(to_email: str, subject: str, body: str, subtype: str = "html"):
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"SMTP not configured. Email to {to_email} suppressed.")
        return False
    
    try:
        msg = MIMEText(body, subtype)
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def generate_otp():
    return str(random.randint(100000, 999999))

def check_overspending(user_id: int, db: Session):
    config = db.query(BudgetConfig).filter(BudgetConfig.user_id == user_id).first()
    if not config or not config.is_configured:
        return
    
    now = datetime.datetime.now()
    today = now.date()
    
    expenses_month = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, 
        Transaction.type == "Expense",
        extract('month', Transaction.date) == now.month,
        extract('year', Transaction.date) == now.year
    ).scalar() or 0
    
    threshold_month = config.monthly_income * 0.8
    if expenses_month > threshold_month:
        exists = db.query(Notification).filter(
            Notification.user_id == user_id, 
            Notification.title == "Monthly Spending Alert",
            cast(Notification.created_at, Date) == today
        ).first()
        
        if not exists:
            pct = int((expenses_month / config.monthly_income) * 100)
            alert = Notification(
                user_id=user_id, 
                title="Monthly Spending Alert", 
                message=f"You've used over 80% ({pct}%) of your monthly income."
            )
            db.add(alert)

    if config.monthly_income > 0:
        daily_limit = (config.monthly_income - config.target_savings) / 30.0
        if daily_limit > 0:
            expenses_today = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id, 
                Transaction.type == "Expense",
                Transaction.category != "Savings", 
                cast(Transaction.date, Date) == today
            ).scalar() or 0
            
            sweeps_today = db.query(func.sum(Sweep.amount)).filter(
                Sweep.user_id == user_id, cast(Sweep.date, Date) == today
            ).scalar() or 0
            
            used_today = expenses_today + sweeps_today

            if used_today > daily_limit:
                 exists_daily = db.query(Notification).filter(
                    Notification.user_id == user_id, 
                    Notification.title == "Daily Limit Exceeded",
                    cast(Notification.created_at, Date) == today
                ).first()
                 
                 if not exists_daily:
                     alert = Notification(
                        user_id=user_id,
                        title="Daily Limit Exceeded",
                        message=f"You've spent ₹{int(used_today)} today, exceeding your daily limit of ₹{int(daily_limit)}."
                     )
                     db.add(alert)
    db.commit()

# --- INTELLIGENT CHAT HELPERS ---
def get_user_context(user_id: int, db: Session):
    now = datetime.datetime.now()
    config = db.query(BudgetConfig).filter(BudgetConfig.user_id == user_id).first()
    monthly_income = config.monthly_income if config else 0
    target_savings = config.target_savings if config else 0
    
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        extract('month', Transaction.date) == now.month,
        extract('year', Transaction.date) == now.year
    ).all()
    
    total_expense = sum(t.amount for t in txs if t.type == "Expense")
    total_income = sum(t.amount for t in txs if t.type == "Income")
    
    categories = {}
    for t in txs:
        if t.type == "Expense":
            cat = t.category.lower()
            categories[cat] = categories.get(cat, 0) + t.amount
            
    top_category = "None"
    top_cat_amount = 0
    if categories:
        top_category = max(categories, key=categories.get)
        top_cat_amount = categories[top_category]
    
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).all()
    total_saved_goals = sum(g.current_amount for g in goals)
    
    ledger_entries = db.query(FriendLedger).filter(
        FriendLedger.user_id == user_id, 
        FriendLedger.status != "SETTLED"
    ).all()

    friend_debts = {}
    total_lent = 0
    total_borrowed = 0

    for entry in ledger_entries:
        name = entry.friend_name.lower()
        if name not in friend_debts:
            friend_debts[name] = {"owes_me": 0, "i_owe": 0}
        
        if entry.type == "FRIEND_OWES_ME":
            friend_debts[name]["owes_me"] += entry.amount
            total_lent += entry.amount
        else:
            friend_debts[name]["i_owe"] += entry.amount
            total_borrowed += entry.amount

    return {
        "monthly_income": monthly_income,
        "target_savings": target_savings,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": total_income - total_expense,
        "categories": categories, 
        "top_category": top_category,
        "top_cat_amount": top_cat_amount,
        "active_goals": len(goals),
        "total_saved_goals": total_saved_goals,
        "money_lent": total_lent,
        "money_borrowed": total_borrowed,
        "remaining_budget": monthly_income - total_expense,
        "friend_debts": friend_debts
    }

def generate_smart_response(message: str, ctx: dict) -> str:
    return "I'm transitioning to a new brain. Please use the new endpoint."


app = FastAPI()

# Setup CORS
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
origins = [
    "http://localhost:3000",
    frontend_url,
]
if frontend_url.endswith("/"):
    origins.append(frontend_url[:-1])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event to run migrations (Avoids import-time blocking on Render)
@app.on_event("startup")
def startup_event():
    run_migrations()

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "ok", "message": "CashBuddy API is running"}

@app.post("/auth/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        if not db_user.is_verified:
            otp = generate_otp()
            db_user.otp_secret = otp
            db_user.otp_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
            db_user.hashed_password = pwd_context.hash(user.password)
            db_user.full_name = user.full_name
            db.commit()
            
            html_content = get_otp_email_html(otp, user.full_name)
            send_email(user.email, "Verify your CashBuddy Account", html_content)
            
            return {"message": "Account exists but not verified. New OTP sent."}
            
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pw = pwd_context.hash(user.password)
    otp = generate_otp()
    expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    
    new_user = User(
        email=user.email, 
        full_name=user.full_name, 
        hashed_password=hashed_pw, 
        otp_secret=otp, 
        otp_expiry=expiry,
        is_verified=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    db.add(BudgetConfig(user_id=new_user.id))
    db.commit()

    html_content = get_otp_email_html(otp, user.full_name)
    send_email(user.email, "Verify your CashBuddy Account", html_content)
    return {"message": "User created. Verify OTP sent to email."}

@app.post("/auth/verify-otp")
def verify_otp(payload: VerifyOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    if user.is_verified:
        return {"message": "User already verified"}

    if not user.otp_secret or user.otp_secret != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if user.otp_expiry and datetime.datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP expired")

    user.is_verified = True
    user.otp_secret = None
    user.otp_expiry = None
    db.commit()
    return {"message": "Account verified successfully"}

@app.post("/auth/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not pwd_context.verify(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not db_user.is_verified:
        raise HTTPException(status_code=403, detail="Account not verified. Please check your email.")

    otp = generate_otp()
    db_user.otp_secret = otp
    db_user.otp_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    db.commit()
    
    html_content = get_otp_email_html(otp, db_user.full_name)
    send_email(db_user.email, "Login Verification Code", html_content)

    return {"message": "Credentials valid. OTP sent.", "require_otp": True}

@app.post("/auth/login/verify")
def verify_login_otp(payload: LoginVerifyRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
         raise HTTPException(status_code=401, detail="Invalid credentials")
         
    if not user.otp_secret or user.otp_secret != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    if user.otp_expiry and datetime.datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP expired")
    
    user.otp_secret = None
    user.otp_expiry = None
    db.commit()

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "full_name": user.full_name}}

@app.post("/auth/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    otp = generate_otp()
    user.otp_secret = otp
    user.otp_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    db.commit()

    html_content = get_otp_email_html(otp, user.full_name)
    send_email(user.email, "Reset Password - CashBuddy", html_content)
    return {"message": "OTP sent to email"}

@app.post("/auth/resend-otp")
def resend_otp(req: ResendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        return {"message": "If email exists, OTP sent."}
    
    otp = generate_otp()
    user.otp_secret = otp
    user.otp_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    db.commit()
    
    html_content = get_otp_email_html(otp, user.full_name)
    send_email(user.email, "CashBuddy - New OTP Request", html_content)
    return {"message": "OTP sent successfully"}

@app.post("/auth/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or user.otp_secret != req.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if user.otp_expiry and datetime.datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP expired")

    user.hashed_password = pwd_context.hash(req.new_password)
    user.otp_secret = None
    user.otp_expiry = None
    db.commit()
    return {"message": "Password reset successful"}

@app.get("/dashboard/stats")
def get_stats(user_id: int, db: Session = Depends(get_db)):
    # Run lazy checks
    check_overspending(user_id, db)

    now = datetime.datetime.now()
    income = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type == "Income",
        extract('month', Transaction.date) == now.month, extract('year', Transaction.date) == now.year
    ).scalar() or 0
    
    expense = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, 
        Transaction.type == "Expense",
        Transaction.category != "Savings",  
        extract('month', Transaction.date) == now.month, 
        extract('year', Transaction.date) == now.year
    ).scalar() or 0
    
    all_inc = db.query(func.sum(Transaction.amount)).filter(Transaction.user_id == user_id, Transaction.type == "Income").scalar() or 0
    all_exp = db.query(func.sum(Transaction.amount)).filter(Transaction.user_id == user_id, Transaction.type == "Expense").scalar() or 0
    balance = all_inc - all_exp
    
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).all()
    total_target = sum(g.target_amount for g in goals)
    total_saved = sum(g.current_amount for g in goals)
    progress = (total_saved / total_target * 100) if total_target > 0 else 0

    return {"income": income, "expenses": expense, "balance": balance, "savings_progress": progress}

@app.get("/dashboard/trend")
def get_trend(user_id: int, period: str = "month", db: Session = Depends(get_db)):
    results = []
    now = datetime.datetime.now()
    
    if period == 'week':
        for i in range(6, -1, -1):
            date = now - datetime.timedelta(days=i)
            amt = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id, 
                Transaction.type == "Expense",
                cast(Transaction.date, Date) == date.date()
            ).scalar() or 0
            results.append({"name": date.strftime("%a"), "amount": amt, "full_date": date.strftime("%Y-%m-%d")})
            
    elif period == 'year':
        for i in range(11, -1, -1):
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            
            amt = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id, Transaction.type == "Expense",
                extract('month', Transaction.date) == m, 
                extract('year', Transaction.date) == y
            ).scalar() or 0
            month_name = datetime.date(y, m, 1).strftime("%b")
            results.append({"name": month_name, "amount": amt})

    else: 
        for i in range(29, -1, -1):
            date = now - datetime.timedelta(days=i)
            amt = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id, 
                Transaction.type == "Expense",
                cast(Transaction.date, Date) == date.date()
            ).scalar() or 0
            results.append({"name": date.strftime("%d"), "amount": amt})

    return results

@app.get("/categories/breakdown")
def get_breakdown(user_id: int, db: Session = Depends(get_db)):
    now = datetime.datetime.now()
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.type == "Expense", extract('month', Transaction.date) == now.month
    ).all()
    data = {}
    for t in txs:
        if t.category not in data: data[t.category] = {"name": t.category, "value": 0, "count": 0}
        data[t.category]["value"] += t.amount
        data[t.category]["count"] += 1
    return list(data.values())

@app.get("/transactions")
def get_transactions(user_id: int, search: str = "", category: str = "", db: Session = Depends(get_db)):
    query = db.query(Transaction).filter(Transaction.user_id == user_id)
    if search: query = query.filter(Transaction.description.contains(search))
    if category: query = query.filter(Transaction.category == category)
    return query.order_by(Transaction.date.desc()).all()

@app.delete("/transactions/{id}")
def delete_transaction(id: int, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == id).first()
    if tx:
        db.delete(tx)
        db.commit()
    return {"message": "Deleted"}

@app.post("/transactions")
def create_transaction(user_id: int, tx: TransactionCreate, db: Session = Depends(get_db)):
    date_obj = datetime.datetime.now()
    if tx.date:
        try:
            cleaned_date = tx.date.replace('Z', '')
            if 'T' in cleaned_date:
                date_obj = datetime.datetime.fromisoformat(cleaned_date)
            else:
                date_obj = datetime.datetime.strptime(cleaned_date, "%Y-%m-%d")
        except Exception as e:
            print(f"Date parse error: {e}, using current time")
            date_obj = datetime.datetime.now()
            
    new_tx = Transaction(
        user_id=user_id, description=tx.description, amount=tx.amount, 
        type=tx.type, category=tx.category, date=date_obj
    )
    db.add(new_tx)
    db.commit()
    check_overspending(user_id, db)
    return {"message": "Added"}

@app.post("/transactions/import")
def magic_import(user_id: int, data: MagicImport, dry_run: bool = False, db: Session = Depends(get_db)):
    parsed_data = FinanceAI.parse_sms(data.text)
    
    if dry_run:
        return parsed_data

    new_tx = Transaction(
        user_id=user_id, description=parsed_data['description'], amount=parsed_data['amount'],
        type=parsed_data['type'], category=parsed_data['category'], date=datetime.datetime.now()
    )
    db.add(new_tx)
    db.commit()
    check_overspending(user_id, db)
    return {"message": "Imported", "parsed": parsed_data}

@app.get("/savings")
def get_savings(user_id: int, db: Session = Depends(get_db)):
    return db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).order_by(SavingsGoal.id).all()

@app.post("/savings")
def create_savings(goal: dict, db: Session = Depends(get_db)):
    new_goal = SavingsGoal(user_id=goal['user_id'], name=goal['name'], target_amount=goal['target_amount'], current_amount=0)
    db.add(new_goal)
    db.commit()
    return {"message": "Created"}

@app.delete("/savings/{id}")
def delete_savings(id: int, db: Session = Depends(get_db)):
    goal = db.query(SavingsGoal).filter(SavingsGoal.id == id).first()
    if goal:
        db.delete(goal)
        db.commit()
    return {"message": "Deleted"}

@app.post("/savings/{id}/deposit")
def update_savings(id: int, user_id: int, payload: dict, db: Session = Depends(get_db)):
    goal = db.query(SavingsGoal).filter(SavingsGoal.id == id).first()
    if goal:
        amount = payload['amount']
        goal.current_amount += amount
        
        if amount > 0:
            tx = Transaction(
                user_id=user_id,
                description=f"Deposit to Goal: {goal.name}",
                amount=amount,
                type="Expense",
                category="Savings",
                date=datetime.datetime.now()
            )
            db.add(tx)
        elif amount < 0:
            tx = Transaction(
                user_id=user_id,
                description=f"Withdrawal from Goal: {goal.name}",
                amount=abs(amount),
                type="Income",
                category="Savings",
                date=datetime.datetime.now()
            )
            db.add(tx)

        db.commit()
    return {"message": "Updated"}

@app.get("/budget/config")
def get_budget_config(user_id: int, db: Session = Depends(get_db)):
    config = db.query(BudgetConfig).filter(BudgetConfig.user_id == user_id).first()
    if not config:
        config = BudgetConfig(user_id=user_id)
        db.add(config)
        db.commit()
    return config

@app.post("/budget/configure")
def set_budget(user_id: int, payload: BudgetSetup, db: Session = Depends(get_db)):
    # 1. Update/Create Budget Config
    config = db.query(BudgetConfig).filter(BudgetConfig.user_id == user_id).first()
    if not config:
        config = BudgetConfig(user_id=user_id)
        db.add(config)
    
    config.monthly_income = payload.monthly_income
    target_savings = (payload.monthly_income * 0.20) if payload.ai_mode else payload.target_savings
    config.target_savings = target_savings
    config.is_configured = True
    config.updated_at = datetime.datetime.utcnow()
    
    # 2. Immediate Savings Transfer Logic
    if target_savings > 0:
        now = datetime.datetime.now()
        start_of_month = datetime.datetime(now.year, now.month, 1)
        # Handle December edge case for next month calculation
        if now.month == 12:
            start_of_next_month = datetime.datetime(now.year + 1, 1, 1)
        else:
            start_of_next_month = datetime.datetime(now.year, now.month + 1, 1)

        # Get the first savings goal or create a default one
        goal = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).order_by(SavingsGoal.id).first()
        if not goal:
            goal = SavingsGoal(user_id=user_id, name="General Savings", target_amount=target_savings * 12, current_amount=0)
            db.add(goal)
            db.flush() # Ensure goal.id is available
        
        # Determine current_amount safe start
        if goal.current_amount is None:
            goal.current_amount = 0

        # Check if we already did an auto-save this month
        existing_tx = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.description == "Monthly Auto-Savings",
            Transaction.date >= start_of_month,
            Transaction.date < start_of_next_month
        ).first()

        if existing_tx:
            # Reverse the previous auto-save from the goal
            goal.current_amount -= existing_tx.amount
            # Remove the old transaction
            db.delete(existing_tx)
            # We don't commit yet, we do it all at once at the end
        
        # Add the new savings amount
        goal.current_amount += target_savings
        
        # Record the transaction
        new_tx = Transaction(
            user_id=user_id,
            description="Monthly Auto-Savings",
            amount=target_savings,
            type="Expense",
            category="Savings",
            date=now
        )
        db.add(new_tx)
    
    elif target_savings == 0:
        # If set to 0, check if we need to refund a previous deduction
        now = datetime.datetime.now()
        start_of_month = datetime.datetime(now.year, now.month, 1)
        if now.month == 12:
            start_of_next_month = datetime.datetime(now.year + 1, 1, 1)
        else:
            start_of_next_month = datetime.datetime(now.year, now.month + 1, 1)

        existing_tx = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.description == "Monthly Auto-Savings",
            Transaction.date >= start_of_month,
            Transaction.date < start_of_next_month
        ).first()
        
        if existing_tx:
             goal = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).order_by(SavingsGoal.id).first()
             if goal:
                 if goal.current_amount is None: goal.current_amount = 0
                 goal.current_amount -= existing_tx.amount
             db.delete(existing_tx)

    db.commit()
    db.refresh(config)
    
    return {"message": "Budget Configured & Savings Deducted", "config": config}

@app.get("/budget")
def get_budget_data(user_id: int, db: Session = Depends(get_db)):
    config = db.query(BudgetConfig).filter(BudgetConfig.user_id == user_id).first()
    if not config or not config.is_configured:
        return {"is_configured": False}

    monthly_budget = config.monthly_income - config.target_savings
    daily_limit = monthly_budget / 30.0
    
    today = datetime.datetime.now().date()
    
    expenses_today = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, 
        Transaction.type == "Expense",
        Transaction.category != "Savings", 
        cast(Transaction.date, Date) == today
    ).scalar() or 0
    
    sweeps_today = db.query(func.sum(Sweep.amount)).filter(
        Sweep.user_id == user_id, cast(Sweep.date, Date) == today
    ).scalar() or 0
    
    used_today_total = expenses_today + sweeps_today
    
    surplus = max(0, daily_limit - used_today_total)

    now = datetime.datetime.now()
    
    # Updated to include all Savings expenses (Auto-Savings + Sweeps + Manual Deposits)
    savings_this_month = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, 
        Transaction.category == "Savings",
        Transaction.type == "Expense",
        extract('month', Transaction.date) == now.month, 
        extract('year', Transaction.date) == now.year
    ).scalar() or 0
    
    sweeps = db.query(Sweep).filter(Sweep.user_id == user_id).order_by(Sweep.date.desc()).limit(10).all()
    
    cat_estimates = [
        {"category": "Food", "limit": monthly_budget * 0.3, "spent": 0},
        {"category": "Travel", "limit": monthly_budget * 0.15, "spent": 0},
        {"category": "Shopping", "limit": monthly_budget * 0.1, "spent": 0},
        {"category": "Utilities", "limit": monthly_budget * 0.1, "spent": 0},
    ]
    
    for cat in cat_estimates:
        spent = db.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == user_id, Transaction.type == "Expense",
            Transaction.category == cat["category"], extract('month', Transaction.date) == now.month
        ).scalar() or 0
        cat["spent"] = spent

    return {
        "is_configured": True,
        "monthly_income": config.monthly_income,
        "daily_limit": round(daily_limit, 2),
        "used_today": used_today_total,
        "surplus": round(surplus, 2),
        "savings_this_month": savings_this_month, 
        "sweeps": sweeps,
        "category_estimates": cat_estimates
    }

@app.post("/budget/sweep")
def sweep_budget(user_id: int, payload: dict, db: Session = Depends(get_db)):
    amount = payload.get('amount', 0)
    if amount <= 0: return {"error": "Nothing to sweep"}
    
    sweep = Sweep(user_id=user_id, amount=amount)
    
    goal = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).order_by(SavingsGoal.id).first()
    if goal:
        goal.current_amount += amount
    
    tx = Transaction(
        user_id=user_id,
        description="Daily Budget Sweep",
        amount=amount,
        type="Expense",
        category="Savings",
        date=datetime.datetime.now()
    )
    db.add(tx)
    db.add(sweep)
    db.commit()
    return {"message": "Swept"}

@app.post("/budget/sweep/undo")
def undo_sweep(user_id: int, db: Session = Depends(get_db)):
    today = datetime.datetime.now().date()
    
    last_sweep = db.query(Sweep).filter(
        Sweep.user_id == user_id,
        cast(Sweep.date, Date) == today
    ).order_by(desc(Sweep.id)).first()
    
    if not last_sweep:
        raise HTTPException(status_code=400, detail="No sweep found to undo for today")
    
    amount = last_sweep.amount
    
    goal = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).order_by(SavingsGoal.id).first()
    if goal:
        goal.current_amount -= amount
        if goal.current_amount < 0: goal.current_amount = 0

    tx = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.amount == amount,
        Transaction.description == "Daily Budget Sweep",
        cast(Transaction.date, Date) == today
    ).order_by(desc(Transaction.id)).first()
    
    if tx:
        db.delete(tx)
    
    db.delete(last_sweep)
    db.commit()
    return {"message": "Undo successful"}

@app.get("/notifications")
def get_notifs(user_id: int, db: Session = Depends(get_db)):
    return db.query(Notification).filter(Notification.user_id == user_id).order_by(Notification.created_at.desc()).all()

@app.put("/notifications/{id}/read")
def mark_notification_read(id: int, user_id: int, db: Session = Depends(get_db)):
    notif = db.query(Notification).filter(Notification.id == id, Notification.user_id == user_id).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"message": "Marked as read"}

@app.get("/chatbot/history")
def get_chat_history(user_id: int, db: Session = Depends(get_db)):
    history = db.query(ChatMessage).filter(ChatMessage.user_id == user_id).order_by(ChatMessage.timestamp.asc()).all()
    return history

@app.post("/chatbot/query")
def chatbot(user_id: int, payload: dict, db: Session = Depends(get_db)):
    user_msg = payload.get('message', '')
    
    db.add(ChatMessage(user_id=user_id, role='user', content=user_msg))
    db.commit()
    
    ctx = get_user_context(user_id, db)
    bot_response = generate_smart_response(user_msg, ctx)
    
    db.add(ChatMessage(user_id=user_id, role='bot', content=bot_response))
    db.commit()

    return {"response": bot_response}

@app.get("/chatbot/context")
def get_context(user_id: int, db: Session = Depends(get_db)):
    return get_user_context(user_id, db)

@app.post("/chatbot/log")
def log_chat(user_id: int, payload: ChatLogRequest, db: Session = Depends(get_db)):
    db.add(ChatMessage(user_id=user_id, role=payload.role, content=payload.content))
    db.commit()
    return {"status": "ok"}

@app.get("/debts")
def get_debts(user_id: int, db: Session = Depends(get_db)):
    lent = db.query(func.sum(FriendLedger.amount)).filter(
        FriendLedger.user_id == user_id, 
        FriendLedger.type == "FRIEND_OWES_ME",
        FriendLedger.status != "SETTLED"
    ).scalar() or 0
    
    borrowed = db.query(func.sum(FriendLedger.amount)).filter(
        FriendLedger.user_id == user_id, 
        FriendLedger.type == "I_OWE_FRIEND",
        FriendLedger.status != "SETTLED"
    ).scalar() or 0
    
    debts = db.query(FriendLedger).filter(FriendLedger.user_id == user_id).order_by(FriendLedger.date.desc()).all()
    
    return {"debts": debts, "total_lent": lent, "total_borrowed": borrowed, "net_balance": lent - borrowed}

@app.post("/debts")
def create_debt(user_id: int, payload: DebtCreate, db: Session = Depends(get_db)):
    date_obj = datetime.datetime.now()
    if payload.date:
         try:
            cleaned_date = payload.date.replace('Z', '')
            if 'T' in cleaned_date:
                date_obj = datetime.datetime.fromisoformat(cleaned_date)
            else:
                date_obj = datetime.datetime.strptime(cleaned_date, "%Y-%m-%d")
         except:
             pass

    new_debt = FriendLedger(
        user_id=user_id,
        friend_name=payload.friend_name,
        type=payload.type,
        amount=payload.amount,
        description=payload.description,
        date=date_obj,
        status="UNPAID"
    )
    db.add(new_debt)
    db.commit()
    return {"message": "Record added"}

@app.put("/debts/{id}")
def update_debt(id: int, user_id: int, payload: DebtUpdate, db: Session = Depends(get_db)):
    debt = db.query(FriendLedger).filter(FriendLedger.id == id, FriendLedger.user_id == user_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt record not found")
    
    debt.amount = payload.amount
    debt.status = payload.status
    db.commit()
    return {"message": "Updated"}

@app.delete("/debts/{id}")
def delete_debt(id: int, db: Session = Depends(get_db)):
    debt = db.query(FriendLedger).filter(FriendLedger.id == id).first()
    if debt:
        db.delete(debt)
        db.commit()
    return {"message": "Deleted"}

if __name__ == "__main__":
    import uvicorn
    # Use environment variable for PORT, default to 8000 for local dev
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)