import sqlite3
from datetime import datetime
import requests

def init_db():
    """Инициализирует базу данных"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS diary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        date TEXT,
        food_name TEXT,
        portion_grams REAL,
        calories REAL,
        protein REAL,
        fat REAL,
        carbs REAL,
        photo_id TEXT
    )
    ''')
    conn.commit()
    conn.close()


def save_to_diary(chat_id, food_name, portion_grams, nutrition_data, photo_id=None):
    """Сохраняет запись в дневник питания (photo_id теперь необязательный)"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO diary (chat_id, date, food_name, portion_grams, calories, protein, fat, carbs, photo_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        chat_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        translate_to_ru(food_name),
        portion_grams,
        nutrition_data['calories'],
        nutrition_data['protein'],
        nutrition_data['fat'],
        nutrition_data['carbs'],
        photo_id  # Может быть None
    ))
    conn.commit()
    conn.close()


def get_dates_with_entries(chat_id):
    """Возвращает список дат, в которые есть записи"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT DISTINCT date(date) as entry_date 
    FROM diary 
    WHERE chat_id = ?
    ORDER BY entry_date DESC
    ''', (chat_id,))

    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def get_diary_entries(chat_id, date=None):
    """Возвращает записи дневника за указанную дату (или все)"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()

    if date:
        # Ищем записи за конкретную дату (без времени)
        cursor.execute('''
        SELECT * FROM diary 
        WHERE chat_id = ? AND date(date) = ?
        ORDER BY date DESC
        ''', (chat_id, date))
    else:
        cursor.execute('''
        SELECT * FROM diary 
        WHERE chat_id = ? 
        ORDER BY date DESC
        ''', (chat_id,))

    entries = cursor.fetchall()
    conn.close()
    return entries


def get_daily_summary(chat_id, date):
    """Возвращает суммарную статистику за указанный день"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT 
        SUM(calories) as total_calories,
        SUM(protein) as total_protein,
        SUM(fat) as total_fat,
        SUM(carbs) as total_carbs
    FROM diary 
    WHERE chat_id = ? AND date(date) = ?
    ''', (chat_id, date))

    summary = cursor.fetchone()
    conn.close()

    return {
        'calories': summary[0] or 0,
        'protein': summary[1] or 0,
        'fat': summary[2] or 0,
        'carbs': summary[3] or 0
    }


def get_today_summary(chat_id):
    """Возвращает суммарные КБЖУ за сегодня"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute('''
    SELECT 
        SUM(calories) as total_calories,
        SUM(protein) as total_protein,
        SUM(fat) as total_fat,
        SUM(carbs) as total_carbs
    FROM diary 
    WHERE chat_id = ? AND date(date) = ?
    ''', (chat_id, today))

    summary = cursor.fetchone()
    conn.close()

    return {
        'calories': summary[0] or 0,
        'protein': summary[1] or 0,
        'fat': summary[2] or 0,
        'carbs': summary[3] or 0
    }

def delete_diary_entry(entry_id, chat_id):
    """Удаляет запись из дневника по ID"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM diary WHERE id = ? AND chat_id = ?', (entry_id, chat_id))
    conn.commit()
    conn.close()


def translate_to_ru(text: str, target_lang: str = "ru") -> str:
    """
    Улучшенный перевод через Google Translate API
    """
    url = "https://translate.googleapis.com/translate_a/single"

    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_lang,
        "dt": "t",
        "q": text,
        "ie": "UTF-8",
        "oe": "UTF-8",
        "dj": "1"
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"API Error: {response.text}")

    try:
        result = response.json()
        if 'sentences' in result:
            return ' '.join(s['trans'] for s in result['sentences'])
        return text
    except:
        return text

def translate_to_en(text: str, target_lang: str = "en") -> str:
    url = "https://translate.googleapis.com/translate_a/single"

    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_lang,
        "dt": "t",
        "q": text,
        "ie": "UTF-8",
        "oe": "UTF-8",
        "dj": "1"
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"API Error: {response.text}")

    try:
        result = response.json()
        if 'sentences' in result:
            return ' '.join(s['trans'] for s in result['sentences'])
        return text
    except:
        return text
