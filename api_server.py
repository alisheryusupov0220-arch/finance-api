#!/usr/bin/env python3
"""
API сервер для Telegram Mini App
Простой endpoint для создания отчёта
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import sys
import os

# Добавляем путь к database_v5.py
sys.path.append('/mnt/user-data/uploads')
from database_v5 import FinanceSystemV5

# Создаём FastAPI приложение
app = FastAPI(title="Finance API", version="1.0")

# CORS для работы из браузера
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача статических файлов (если есть папка static)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Путь к БД (будем создавать подключение для каждого запроса)
DB_PATH = 'finance_v5.db'

def get_db():
    """Получить подключение к БД (для каждого запроса новое)"""
    return FinanceSystemV5(DB_PATH)

# ========== МОДЕЛИ ДАННЫХ ==========

class PaymentEntry(BaseModel):
    """Платёж в отчёте"""
    method_id: int
    amount: float

class ExpenseEntry(BaseModel):
    """Расход в отчёте"""
    category_id: Optional[int] = None
    amount: float
    description: str

class IncomeEntry(BaseModel):
    """Приход в отчёте"""
    category_id: Optional[int] = None
    amount: float
    description: str

class CreateReportRequest(BaseModel):
    """Запрос на создание отчёта"""
    report_date: str  # YYYY-MM-DD
    location_id: int
    total_sales: float
    payments: List[PaymentEntry]
    expenses: Optional[List[ExpenseEntry]] = []
    incomes: Optional[List[IncomeEntry]] = []
    cash_actual: Optional[float] = 0
    created_by: Optional[str] = "telegram_user"

# ========== ENDPOINTS ==========

@app.get("/")
def root():
    """Проверка работы API"""
    return {"status": "ok", "message": "Finance API v1.0"}

@app.get("/api/locations")
def get_locations():
    """Получить список точек продаж"""
    try:
        db = get_db()
        locations = db.get_locations()
        return {"status": "ok", "data": locations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payment_methods")
def get_payment_methods():
    """Получить методы оплаты"""
    try:
        db = get_db()
        methods = db.get_payment_methods()
        return {"status": "ok", "data": methods}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/expense_categories")
def get_expense_categories():
    """Получить категории расходов"""
    try:
        db = get_db()
        categories = db.get_expense_categories()
        return {"status": "ok", "data": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/income_categories")
def get_income_categories():
    """Получить категории приходов"""
    try:
        db = get_db()
        categories = db.get_categories(category_type='income')
        return {"status": "ok", "data": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/create_report")
def create_report(request: CreateReportRequest):
    """
    ГЛАВНЫЙ ENDPOINT: Создать отчёт
    
    Принимает JSON с данными отчёта и сохраняет в БД
    """
    try:
        from datetime import datetime
        
        db = get_db()  # Новое подключение для этого запроса
        
        # Парсим дату
        report_date = datetime.strptime(request.report_date, '%Y-%m-%d').date()
        
        # Проверяем существует ли отчёт
        existing = db.get_daily_report(report_date, request.location_id)
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Отчёт за {request.report_date} уже существует"
            )
        
        # Создаём отчёт
        report_id = db.create_daily_report(
            report_date=report_date,
            location_id=request.location_id,
            total_sales=request.total_sales,
            created_by=request.created_by
        )
        
        # Добавляем платежи
        for payment in request.payments:
            if payment.amount > 0:
                # Получаем метод оплаты
                methods = db.get_payment_methods()
                method = next((m for m in methods if m['id'] == payment.method_id), None)
                
                if method:
                    db.add_report_payment(
                        report_id=report_id,
                        payment_method_id=payment.method_id,
                        account_id=method['default_account_id'],
                        amount=payment.amount
                    )
        
        # Добавляем расходы
        for expense in request.expenses:
            if expense.amount > 0:
                # Для расходов account_id = 1 (Касса по умолчанию)
                db.add_report_expense(
                    report_id=report_id,
                    account_id=1,
                    amount=expense.amount,
                    category_id=expense.category_id,
                    description=expense.description
                )
        
        # Добавляем приходы
        for income in request.incomes:
            if income.amount > 0:
                # Для приходов account_id = 1 (Касса по умолчанию)
                db.add_non_sales_income(
                    report_id=report_id,
                    account_id=1,
                    amount=income.amount,
                    category_id=income.category_id,
                    description=income.description
                )
        
        # Обновляем cash_actual если передан
        if request.cash_actual > 0:
            cursor = db.conn.cursor()
            cursor.execute('''
                UPDATE daily_reports 
                SET cash_actual = ?, status = 'closed'
                WHERE id = ?
            ''', (request.cash_actual, report_id))
            db.conn.commit()
        
        return {
            "status": "ok",
            "message": "Отчёт успешно создан",
            "report_id": report_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.get("/api/test_db")
def test_db():
    """Тест подключения к БД"""
    try:
        db = get_db()
        accounts = db.get_accounts()
        locations = db.get_locations()
        return {
            "status": "ok",
            "accounts": len(accounts),
            "locations": len(locations)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Порт из переменной окружения (для хостинга) или 8000
    port = int(os.environ.get("PORT", 8000))
    
    print("🚀 Запускаем API сервер...")
    print(f"📍 http://0.0.0.0:{port}")
    print("📚 Документация: http://localhost:8000/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
