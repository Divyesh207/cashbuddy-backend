# 💰 CashBuddy – Backend API

CashBuddy is an AI-powered personal finance platform that helps users track expenses, manage budgets, and gain smart financial insights.

This repository contains the **backend API** that powers CashBuddy, handling authentication, transactions, budgeting, and financial data management.

---

## 🚀 Features

- 🔐 User authentication system  
- 💳 Expense & income tracking  
- 📊 Budget management  
- 🗄️ Database integration for financial records  
- ⚡ Fast API performance  
- 🌍 Deployment-ready backend  

---

## 🛠️ Tech Stack

- Python  
- FastAPI  
- Uvicorn (ASGI server)  
- SQLite (current)  
- REST API architecture  

---

## 📂 Project Structure

```

cashbuddy-backend/
│
├── app/                # Main backend application
├── venv/               # Virtual environment (local)
├── .gitignore
├── cashbuddy.db        # SQLite database
├── requirements.txt    # Dependencies
├── runtime.txt         # Runtime config for deployment
└── README.md

````

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the repository

```bash
git clone https://github.com/Divyesh207/cashbuddy-backend.git
cd cashbuddy-backend
````

---

### 2️⃣ Create virtual environment

```bash
python -m venv venv
```

Activate:

**Windows**

```bash
venv\Scripts\activate
```

**Mac/Linux**

```bash
source venv/bin/activate
```

---

### 3️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Run the server

```bash
uvicorn app.main:app --reload
```

Server runs on:

```
http://127.0.0.1:8000
```

API Docs (auto-generated):

```
http://127.0.0.1:8000/docs
```

---

## 🗄️ Database

Currently uses **SQLite** (`cashbuddy.db`) for storing:

* Users
* Transactions
* Budget data

Can be upgraded to PostgreSQL for production.

---

## 🔗 Example API Routes

### Auth

* POST `/register`
* POST `/login`

### Transactions

* GET `/transactions`
* POST `/transactions`

### Budget

* GET `/budget`
* POST `/budget`

---

## 🌍 Deployment

Backend can be deployed on:

* Render
* Railway
* AWS
* VPS servers

Make sure to:

* Set environment variables
* Use production database
* Disable debug mode

---
