from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    otp_secret = Column(String, nullable=True)
    otp_expiry = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)
    
    budget_config = relationship("BudgetConfig", back_populates="user", uselist=False)
    transactions = relationship("Transaction", back_populates="user")
    savings_goals = relationship("SavingsGoal", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    friend_ledger = relationship("FriendLedger", back_populates="user")
    chat_history = relationship("ChatMessage", back_populates="user")

class BudgetConfig(Base):
    __tablename__ = "budget_configs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    monthly_income = Column(Float, default=0)
    target_savings = Column(Float, default=0)
    is_configured = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="budget_config")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    description = Column(String)
    amount = Column(Float)
    type = Column(String) # Income / Expense
    category = Column(String)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="transactions")

class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    target_amount = Column(Float)
    current_amount = Column(Float, default=0)
    
    user = relationship("User", back_populates="savings_goals")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    message = Column(String)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="notifications")

class Sweep(Base):
    __tablename__ = "sweeps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    date = Column(DateTime, default=datetime.datetime.utcnow)

class FriendLedger(Base):
    __tablename__ = "friend_ledger"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    friend_name = Column(String)
    type = Column(String) # "FRIEND_OWES_ME" or "I_OWE_FRIEND"
    amount = Column(Float) # The original amount or current outstanding
    description = Column(String, nullable=True)
    status = Column(String, default="UNPAID") # UNPAID, PARTIALLY_PAID, SETTLED
    date = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="friend_ledger")

class ChatMessage(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String) # 'user' or 'bot'
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="chat_history")
