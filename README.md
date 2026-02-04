# 💰 CashBuddy – Backend

CashBuddy is an AI-powered personal finance management application that helps users track expenses, manage budgets, and improve savings.

This repository contains the **backend API** of CashBuddy, responsible for authentication, transaction management, budgeting logic, and AI-based categorization.

---

## 🚀 Features

- 🔐 User authentication (JWT-based login/register)
- 💳 Expense & income tracking APIs
- 📊 Budget management
- 🤖 ML-based transaction categorization
- 🔔 Notifications support (planned)
- 🗄️ PostgreSQL database integration
- 🌍 Deployment-ready configuration

---

## 🛠️ Tech Stack

- Python
- Flask
- PostgreSQL
- SQLAlchemy
- JWT Authentication
- scikit-learn (for ML features)
- REST API architecture

---

## 📂 Project Structure

```

cashbuddy-backend/
├── app.py
├── models/
├── routes/
├── services/
├── ml/
├── config.py
├── requirements.txt
└── .env

````

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the repository

```bash
git clone https://github.com/yourusername/cashbuddy-backend.git
cd cashbuddy-backend
````

---

### 2️⃣ Create virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows
```

---

### 3️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Setup environment variables

Create a `.env` file:

```
DATABASE_URL=your_postgresql_url
SECRET_KEY=your_secret_key
JWT_SECRET=your_jwt_secret
```

---

### 5️⃣ Run the server

```bash
python app.py
```

Server runs on:

```
http://localhost:5000
```

---

## 🗄️ Database

CashBuddy uses **PostgreSQL**.

Example connection string:

```
postgresql://username:password@localhost:5432/cashbuddy_db
```

---

## 🔗 API Endpoints (Sample)

### Auth

* POST `/register`
* POST `/login`

### Transactions

* GET `/transactions`
* POST `/transactions`
* DELETE `/transactions/<id>`

### Budget

* GET `/budget`
* POST `/budget`

---

## 🤖 ML Feature

CashBuddy uses a simple ML model to:

* Categorize expenses
* Provide smart budgeting insights

Model can be found in:

```
/ml/
```

---

## 🌍 Deployment

Backend can be deployed on:

* Render
* Railway
* AWS (EC2/Elastic Beanstalk)

Example Render deployment:

1. Connect GitHub repo
2. Add environment variables
3. Deploy as Web Service

---
