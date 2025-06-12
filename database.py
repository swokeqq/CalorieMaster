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


def save_to_diary(chat_id, food_name, portion_grams, nutrition_data, photo_id):
    """Сохраняет запись в дневник питания"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO diary (chat_id, date, food_name, portion_grams, calories, protein, fat, carbs, photo_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        chat_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        translate(food_name),
        portion_grams,
        nutrition_data['calories'],
        nutrition_data['protein'],
        nutrition_data['fat'],
        nutrition_data['carbs'],
        photo_id
    ))
    conn.commit()
    conn.close()


def get_diary_entries(chat_id, date=None):
    """Возвращает записи дневника за указанную дату (или все)"""
    conn = sqlite3.connect('food_diary.db')
    cursor = conn.cursor()

    if date:
        cursor.execute('''
        SELECT * FROM diary 
        WHERE chat_id = ? AND date LIKE ?
        ORDER BY date DESC
        ''', (chat_id, f"{date}%"))
    else:
        cursor.execute('''
        SELECT * FROM diary 
        WHERE chat_id = ? 
        ORDER BY date DESC
        ''', (chat_id,))

    entries = cursor.fetchall()
    conn.close()
    return entries

def translate(text, target_lang="ru"):
    """Перевод текста через Google Translate"""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_lang,
        "dt": "t",
        "q": text
    }
    response = requests.get(url, params=params)
    return response.json()[0][0][0] if response.status_code == 200 else text
