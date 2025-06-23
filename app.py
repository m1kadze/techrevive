from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
import aiosqlite
import asyncio
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from io import BytesIO
import json
import re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Замените на безопасный ключ

# Конфигурация
DB_PATH = "database/techrevive.db"
SERVICE_CENTERS = [
    "Москва, ул. Тверская, д. 15",
    "Санкт-Петербург, Невский пр., д. 22",
    "Казань, ул. Баумана, д. 51",
    "Екатеринбург, ул. Ленина, д. 25",
    "Новосибирск, ул. Горская, д. 10",
]
AVAILABLE_HOURS = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

# Предопределённые типы устройств
DEVICE_TYPES = [
    "Телефон",
    "Компьютер",
    "Планшет",
    "Ноутбук",
    "Умные часы",
    "Наушники",
    "Игровая консоль",
    "Своё"
]

# Инициализация базы данных
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица сервисов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price INTEGER NOT NULL,
                symptoms TEXT NOT NULL,
                repair_time TEXT NOT NULL
            )
        ''')
        # Таблица запросов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                problem TEXT NOT NULL
            )
        ''')
        # Таблица записей на диагностику
        await db.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                service_center TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                device_type TEXT NOT NULL,
                device_brand TEXT NOT NULL,
                device_model TEXT NOT NULL,
                status TEXT DEFAULT 'confirmed'
            )
        ''')
        # Таблица завершенных записей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS completed_appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER,
                user_id INTEGER,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                service_center TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                device_type TEXT,
                device_brand TEXT,
                device_model TEXT,
                services_performed TEXT,
                pdf_data BLOB
            )
        ''')
        # Таблица брендов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS device_brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                device_type TEXT NOT NULL
            )
        ''')
        # Таблица моделей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS device_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_id INTEGER NOT NULL,
                name TEXT NOT NULL
            )
        ''')
        # Таблица администраторов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        ''')
        await db.commit()

# Запуск инициализации базы данных
loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(init_db())
except Exception as e:
    print(f"Ошибка инициализации базы данных: {e}")

# Проверка авторизации
def check_auth():
    return session.get('logged_in', False)

# Страница логина
@app.route('/admin/login', methods=['GET', 'POST'])
async def admin_login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM admins WHERE login = ? AND password = ?', (login, password))
            admin = await cursor.fetchone()
        if admin:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        return render_template('login.html', error="Неверный логин или пароль")
    return render_template('login.html')

# Выход из админ-панели
@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

# Админ-панель
@app.route('/admin', methods=['GET', 'POST'])
async def admin_panel():
    if not check_auth():
        return redirect(url_for('admin_login'))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT DISTINCT service_center FROM appointments")
        service_centers = [row['service_center'] for row in await cursor.fetchall()]
        status = request.args.get('status', '')
        service_center = request.args.get('service_center', '')
        date = request.args.get('date', '')
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'asc')
        query = "SELECT * FROM appointments WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if service_center:
            query += " AND service_center = ?"
            params.append(service_center)
        if date:
            query += " AND date = ?"
            params.append(date)
        query += f" ORDER BY {sort_by} {'ASC' if sort_order == 'asc' else 'DESC'}"
        cursor = await db.execute(query, params)
        appointments = await cursor.fetchall()
    return render_template('admin.html', appointments=appointments, service_centers=service_centers, 
                           status=status, service_center=service_center, date=date, 
                           sort_by=sort_by, sort_order=sort_order)

# Принять заявку
@app.route('/admin/accept/<int:appointment_id>')
async def accept_appointment(appointment_id):
    if not check_auth():
        return redirect(url_for('admin_login'))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE appointments SET status = 'accepted' WHERE id = ?", (appointment_id,))
        await db.commit()
    return redirect(url_for('admin_panel'))

# Отклонить заявку
@app.route('/admin/reject/<int:appointment_id>')
async def reject_appointment(appointment_id):
    if not check_auth():
        return redirect(url_for('admin_login'))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT name, service_center, date, time FROM appointments WHERE id = ?", (appointment_id,))
        appointment = await cursor.fetchone()
        await db.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        await db.commit()
    return redirect(url_for('admin_panel'))

# Завершение заявки
@app.route('/admin/complete/<int:appointment_id>', methods=['GET', 'POST'])
async def complete_appointment(appointment_id):
    if not check_auth():
        return redirect(url_for('admin_login'))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
        appointment = await cursor.fetchone()
        cursor = await db.execute("SELECT * FROM services")
        services = await cursor.fetchall()
        cursor = await db.execute("SELECT DISTINCT device_type FROM device_brands")
        device_types = [row['device_type'] for row in await cursor.fetchall()] + ["Своё"]
    if request.method == 'POST':
        device_type = request.form.get('device_type')
        device_brand = request.form.get('device_brand') or request.form.get('custom_brand')
        device_model = request.form.get('device_model') or request.form.get('custom_model')
        services_performed = request.form.getlist('services') + [request.form.get('custom_service')] if request.form.get('custom_service') else []
        services_performed_json = json.dumps(services_performed)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph("TechRevive: Отчет о ремонте", styles['Title']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"ID записи: {appointment_id}", styles['Normal']))
        story.append(Paragraph(f"Имя клиента: {appointment['name']}", styles['Normal']))
        story.append(Paragraph(f"Телефон: {appointment['phone']}", styles['Normal']))
        story.append(Paragraph(f"Сервисный центр: {appointment['service_center']}", styles['Normal']))
        story.append(Paragraph(f"Дата: {appointment['date']}", styles['Normal']))
        story.append(Paragraph(f"Время: {appointment['time']}", styles['Normal']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Тип устройства: {device_type}", styles['Normal']))
        story.append(Paragraph(f"Бренд: {device_brand}", styles['Normal']))
        story.append(Paragraph(f"Модель: {device_model}", styles['Normal']))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Выполненные работы:", styles['Heading2']))
        for service in services_performed:
            if service:
                story.append(Paragraph(f"- {service}", styles['Normal']))
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO completed_appointments (appointment_id, user_id, name, phone, service_center, date, time, 
                                                    device_type, device_brand, device_model, services_performed, pdf_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (appointment_id, appointment['user_id'], appointment['name'], appointment['phone'], 
                  appointment['service_center'], appointment['date'], appointment['time'], 
                  device_type, device_brand, device_model, services_performed_json, pdf_data))
            await db.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
            await db.commit()
        return redirect(url_for('admin_panel'))
    return render_template('complete_appointment.html', appointment=appointment, services=services, device_types=device_types)

# Получение доступных дат
@app.route('/get_available_dates')
def get_available_dates():
    dates = []
    today = datetime.now()
    for i in range(7):
        date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        dates.append(date)
    return jsonify(dates)

# Получение доступных временных слотов
@app.route('/get_available_times/<date>')
async def get_available_times(date):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT time FROM appointments WHERE date = ? AND status IN ('confirmed', 'accepted')", (date,))
        booked_times = [row['time'] for row in await cursor.fetchall()]
    available_times = [time for time in AVAILABLE_HOURS if time not in booked_times]
    return jsonify(available_times)

# Получение брендов для типа устройства
@app.route('/get_brands/<device_type>')
async def get_brands(device_type):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT name FROM device_brands WHERE device_type = ?", (device_type,))
        brands = [row['name'] for row in await cursor.fetchall()]
    return jsonify(brands + ["Своё"])

# Получение моделей для бренда
@app.route('/get_models/<brand>')
async def get_models(brand):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT name FROM device_models WHERE brand_id = (SELECT id FROM device_brands WHERE name = ? LIMIT 1)", (brand,))
        models = [row['name'] for row in await cursor.fetchall()]
    return jsonify(models)

# Запись на диагностику
@app.route('/book_appointment', methods=['POST'])
async def book_appointment():
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    service_center = data.get('service_center')
    date = data.get('date')
    time = data.get('time')
    device_type = data.get('device_type')
    device_brand = data.get('device_brand')
    device_model = data.get('device_model')

    if not all([name, phone, service_center, date, time, device_type, device_brand, device_model]):
        return jsonify({'status': 'error', 'message': 'Все поля обязательны'}), 400

    if not re.match(r'^\+?\d{10,15}$', phone):
        return jsonify({'status': 'error', 'message': 'Некорректный номер телефона'}), 400

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute('''
                INSERT INTO appointments (name, phone, service_center, date, time, device_type, device_brand, device_model, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
            ''', (name, phone, service_center, date, time, device_type, device_brand, device_model))
            await db.commit()
            appointment_id = cursor.lastrowid
        return jsonify({'status': 'success', 'message': 'Запись подтверждена', 'appointment_id': appointment_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Ошибка: {str(e)}'}), 500

# Просмотр завершенных записей
@app.route('/admin/view_completed')
async def view_completed():
    if not check_auth():
        return redirect(url_for('admin_login'))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM completed_appointments ORDER BY date, time")
        completed_appointments = await cursor.fetchall()
        completed_appointments = [
            {
                **appt,
                'services_performed': json.loads(appt['services_performed'])
            } for appt in completed_appointments
        ]
    return render_template('view_completed.html', completed_appointments=completed_appointments)

# Скачивание PDF
@app.route('/admin/download_pdf/<int:completed_id>')
async def download_pdf(completed_id):
    if not check_auth():
        return redirect(url_for('admin_login'))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT pdf_data FROM completed_appointments WHERE id = ?", (completed_id,))
        completed = await cursor.fetchone()
    if completed:
        buffer = BytesIO(completed['pdf_data'])
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f"report_{completed_id}.pdf")
    return "PDF не найден", 404

# Главная страница
@app.route('/')
def index():
    return render_template('index.html')

# Страница каталога
@app.route('/catalog', methods=['GET'])
async def catalog():
    symptoms = request.args.get('symptoms', '')
    min_price = request.args.get('min_price', 0, type=int)
    max_price = request.args.get('max_price', 10000, type=int)
    query = 'SELECT * FROM services WHERE price BETWEEN ? AND ?'
    params = [min_price, max_price]
    if symptoms:
        query += ' AND symptoms LIKE ?'
        params.append(f'%{symptoms}%')
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        services = await cursor.fetchall()
    return render_template('catalog.html', services=services, symptoms=symptoms, min_price=min_price, max_price=max_price, 
                           device_types=DEVICE_TYPES, service_centers=SERVICE_CENTERS)

# Страница FAQ
@app.route('/faq', methods=['GET', 'POST'])
async def faq():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        problem = request.form.get('problem')
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO requests (name, phone, problem) VALUES (?, ?, ?)
            ''', (name, phone, problem))
            await db.commit()
        return jsonify({'status': 'success', 'message': 'Заявка отправлена!'})
    return render_template('faq.html')

# Получение данных для модального окна
@app.route('/service/<int:service_id>')
async def get_service(service_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM services WHERE id = ?', (service_id,))
        service = await cursor.fetchone()
    if service:
        return jsonify({
            'id': service['id'],
            'name': service['name'],
            'price': service['price'],
            'symptoms': service['symptoms'].split(', '),
            'repair_time': service['repair_time']
        })
    return jsonify({'error': 'Service not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)