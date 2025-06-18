import telebot
import requests
import os
from dotenv import load_dotenv
from database import (init_db, save_to_diary, get_diary_entries, get_dates_with_entries,
                      get_daily_summary, get_today_summary, delete_diary_entry,
                      translate_to_ru, translate_to_en)
from datetime import datetime, timedelta
import calendar

# --- Конфигурация --- #
load_dotenv()
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

# API Keys
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
LOGMEAL_API_KEY = os.getenv('LOGMEAL_API_KEY')
LOGMEAL_ENDPOINT = "https://api.logmeal.com/v2/image/segmentation/complete"
LOGMEAL_HEADERS = {'Authorization': 'Bearer ' + LOGMEAL_API_KEY}

NUTRITIONIX_APP_ID = os.getenv('NUTRITIONIX_APP_ID')
NUTRITIONIX_APP_KEY = os.getenv('NUTRITIONIX_APP_KEY')
NUTRITIONIX_ENDPOINT = "https://trackapi.nutritionix.com/v2/natural/nutrients"

# Глобальный словарь для временных данных
user_food_data = {}

# Инициализация БД
init_db()

def create_main_keyboard():
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)

    row1 = [
        telebot.types.KeyboardButton("🍽 Потреблено сегодня"),
        telebot.types.KeyboardButton("📜 Дневник"),
        telebot.types.KeyboardButton("✍️ Ввести вручную")
    ]

    row2 = [
        telebot.types.KeyboardButton("🧑‍🍳 Что приготовить?"),
        telebot.types.KeyboardButton("❓ Помощь")
    ]

    keyboard.add(*row1)
    keyboard.add(*row2)

    return keyboard


def analyze_photo_with_logmeal(file_path):
    """Распознает еду на фото через Logmeal API с проверкой вероятности"""
    try:
        with open(file_path, 'rb') as image_file:
            response = requests.post(
                LOGMEAL_ENDPOINT,
                files={'image': image_file},
                headers=LOGMEAL_HEADERS
            )
        data = response.json()

        recognition_result = data['segmentation_results'][0]['recognition_results'][0]
        food_name = recognition_result['name']
        prob = recognition_result.get('prob', 1.0)

        return {
            'food_name': food_name,
            'prob': float(prob)
        }
    except Exception as e:
        return {'error': str(e)}


def get_nutritionix_data(food_name):
    """Получает данные о КБЖУ из Nutritionix"""
    headers = {
        'x-app-id': NUTRITIONIX_APP_ID,
        'x-app-key': NUTRITIONIX_APP_KEY,
        'Content-Type': 'application/json'
    }
    payload = {'query': food_name}

    response = requests.post(NUTRITIONIX_ENDPOINT, json=payload, headers=headers)
    if response.status_code != 200:
        return None

    food = response.json()['foods'][0]
    return {
        'calories': food.get('nf_calories', 0),
        'protein': food.get('nf_protein', 0),
        'fat': food.get('nf_total_fat', 0),
        'carbs': food.get('nf_total_carbohydrate', 0),
        'serving_weight': food.get('serving_weight_grams', 100)
    }


def calculate_nutrition(portion_grams, nutrition_data):
    """Пересчет КБЖУ с учетом исходного веса порции"""
    if not nutrition_data or 'serving_weight' not in nutrition_data:
        return None

    base_weight = nutrition_data.get('serving_weight', 100)
    coefficient = portion_grams / base_weight

    return {
        'calories': round(nutrition_data['calories'] * coefficient, 1),
        'protein': round(nutrition_data['protein'] * coefficient, 1),
        'fat': round(nutrition_data['fat'] * coefficient, 1),
        'carbs': round(nutrition_data['carbs'] * coefficient, 1)
    }


def format_nutrition_response(food_name, nutrition_data, portion_grams):
    """Форматирует ответ с КБЖУ"""
    return (
        f"🍏 {translate_to_ru(food_name)}\n"
        f"⚖️ Порция: {portion_grams}г\n\n"
        f"Энергетическая ценность:\n"
        f"🔥 {nutrition_data['calories']} ккал\n"
        f"🥩 {nutrition_data['protein']}г белков\n"
        f"🥑 {nutrition_data['fat']}г жиров\n"
        f"🍞 {nutrition_data['carbs']}г углеводов"
    )


def generate_calendar(year, month, marked_days=None):
    """Генерирует календарь с жирным выделением дней с записями"""
    if marked_days is None:
        marked_days = []

    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]

    keyboard = []

    # Заголовок с месяцем и годом
    keyboard.append([
        telebot.types.InlineKeyboardButton(
            f"<< {month_name} {year} >>",
            callback_data="ignore"
        )
    ])

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([
        telebot.types.InlineKeyboardButton(day, callback_data="ignore")
        for day in week_days
    ])

    # Недели
    for week in cal:
        week_buttons = []
        for day in week:
            if day == 0:
                week_buttons.append(
                    telebot.types.InlineKeyboardButton(" ", callback_data="ignore")
                )
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                # Жирное выделение для дней с записями
                day_text = f"*{day}*" if date_str in marked_days else str(day)
                week_buttons.append(
                    telebot.types.InlineKeyboardButton(
                        day_text,
                        callback_data=f"day_{date_str}"
                    )
                )
        keyboard.append(week_buttons)

    # Кнопки навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    keyboard.append([
        telebot.types.InlineKeyboardButton(
            "◀️ Предыдущий месяц",
            callback_data=f"month_{prev_year}_{prev_month}"
        ),
        telebot.types.InlineKeyboardButton(
            "▶️ Следующий месяц",
            callback_data=f"month_{next_year}_{next_month}"
        )
    ])

    return telebot.types.InlineKeyboardMarkup(keyboard)


def show_day_entries(chat_id, date_str):
    """Показывает записи за конкретный день с кнопками удаления"""
    entries = get_diary_entries(chat_id, date_str)
    summary = get_daily_summary(chat_id, date_str)

    if not entries:
        bot.send_message(chat_id, f"🍽 Нет записей за {date_str}")
        return

    # Формируем сообщение
    message = f"📅 Дневник питания за {date_str}:\n\n"

    for entry in entries:
        message += (
            f"⏰ {entry[2].split()[1][:5]} | {entry[3]}\n"
            f"⚖️ {entry[4]}г | 🔥 {entry[5]} ккал\n"
            f"🥩 {entry[6]}г белков | 🥑 {entry[7]}г жиров | 🍞 {entry[8]}г углеводов\n\n"
        )

    message += (
        f"📊 Итого за день:\n"
        f"🔥 {summary['calories']:.0f} ккал\n"
        f"🥩 {summary['protein']:.1f}г белков\n"
        f"🥑 {summary['fat']:.1f}г жиров\n"
        f"🍞 {summary['carbs']:.1f}г углеводов"
    )

    # Создаем кнопки удаления для каждой записи
    markup = telebot.types.InlineKeyboardMarkup()
    for entry in entries:
        markup.add(
            telebot.types.InlineKeyboardButton(
                f"❌ Удалить {entry[3][:15]}...",
                callback_data=f"delete_{entry[0]}"
            )
        )

    # Добавляем кнопку "Назад к календарю"
    markup.add(
        telebot.types.InlineKeyboardButton(
            "🔙 Назад к календарю",
            callback_data="back_to_calendar"
        )
    )

    bot.send_message(chat_id, message, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def handle_delete_entry(call):
    try:
        entry_id = int(call.data.split('_')[1])
        delete_diary_entry(entry_id, call.message.chat.id)

        # Обновляем сообщение
        bot.answer_callback_query(call.id, "✅ Запись удалена!")

        # Получаем дату из оригинального сообщения
        original_text = call.message.text
        date_str = original_text.split("за ")[1].split(":")[0].strip()

        # Показываем обновленный список записей
        show_day_entries(call.message.chat.id, date_str)

    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    keyboard = create_main_keyboard()
    bot.reply_to(message,
        "🍏 Добро пожаловать в Calorie Master!\n\n"
        "Вы можете:\n"
        "1. 📸 Отправить фото еды для анализа\n"
        "2. ✍️ Ввести продукт вручную\n"
        "3. 📅 Просматривать дневник питания\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


def generate_recipes_with_deepseek(ingredients):
    """Генерирует рецепты через DeepSeek API"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Сгенерируй 3 простых рецепта только из этих ингредиентов: {', '.join(ingredients)}.\n"
        "Для каждого рецепта укажи:\n"
        "1. Название (максимум 5 слов)\n"
        "2. Ингредиенты (только из списка выше)\n"
        "3. Время приготовления в минутах\n"
        "4. Краткую инструкцию (3 предложения)\n\n"
        "Формат вывода (без комментариев):\n"
        "1. Название\n"
        "• Ингредиенты: ...\n"
        "• Время: ... мин\n"
        "• Рецепт: ...\n\n"
    )

    response = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers=headers,
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
    )

    if response.status_code != 200:
        raise Exception(f"API Error: {response.text}")

    return response.json()["choices"][0]["message"]["content"]


@bot.message_handler(func=lambda message: message.text == "🧑‍🍳 Что приготовить?")
def ask_for_ingredients(message):
    bot.reply_to(message,
                 "📝 Перечислите продукты через запятую:\n"
                 "Пример: <i>яйца, молоко, мука, сыр</i>",
                 parse_mode="HTML"
                 )
    bot.register_next_step_handler(message, handle_ingredients_list)


def handle_ingredients_list(message):
    try:
        ingredients = [x.strip() for x in message.text.split(',') if x.strip()]

        if len(ingredients) < 2:
            raise ValueError("Нужно минимум 2 ингредиента")

        typing_msg = bot.send_message(message.chat.id, "🧠 Придумываю рецепты...")

        recipes = generate_recipes_with_deepseek(ingredients)

        response = f"🍳 <b>Рецепты из {', '.join(ingredients)}:</b>\n\n{recipes}"

        # Удаляем сообщение "типирования" и отправляем результат
        bot.delete_message(message.chat.id, typing_msg.message_id)
        bot.reply_to(message, response, parse_mode="HTML")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "📋 Меню")
def show_menu(message):
    keyboard = create_main_keyboard()
    bot.reply_to(message, "Главное меню:", reply_markup=keyboard)

@bot.message_handler(commands=['diary'])
def show_diary_menu(message):
    today = datetime.now()
    marked_dates = get_dates_with_entries(message.chat.id)

    markup = generate_calendar(today.year, today.month, marked_dates)

    bot.send_message(
        message.chat.id,
        "📅 Выберите дату для просмотра записей:",
        reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text == "🍽 Потреблено сегодня")
def show_today_summary(message):
    today_stats = get_today_summary(message.chat.id)

    if today_stats['calories'] == 0:
        bot.reply_to(message, "Сегодня еще нет записей в дневнике 🍽")
        return

    response = (
        "📊 <b>Съедено сегодня:</b>\n\n"
        f"🔥 <b>Калории:</b> {today_stats['calories']:.0f} ккал\n"
        f"🥩 <b>Белки:</b> {today_stats['protein']:.1f}г\n"
        f"🧈 <b>Жиры:</b> {today_stats['fat']:.1f}г\n"
        f"🍞 <b>Углеводы:</b> {today_stats['carbs']:.1f}г\n\n"
        "Чтобы добавить запись, отправьте фото еды 📸"
    )

    bot.reply_to(message, response, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text in ["❓ Помощь", "/help"])
def handle_help(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text in ["📜 Дневник", "/diary"])
def handle_diary(message):
    show_diary_menu(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('day_'))
def handle_day_selection(call):
    """Обрабатывает выбор дня в календаре"""
    date_str = call.data.split('_')[1]
    show_day_entries(call.message.chat.id, date_str)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('month_'))
def handle_month_change(call):
    _, year, month = call.data.split('_')
    year = int(year)
    month = int(month)
    marked_dates = get_dates_with_entries(call.message.chat.id)

    markup = generate_calendar(year, month, marked_dates)

    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == 'back_to_calendar')
def handle_back_to_calendar(call):
    today = datetime.now()
    marked_dates = get_dates_with_entries(call.message.chat.id)

    markup = generate_calendar(today.year, today.month, marked_dates)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📅 Выберите дату для просмотра записей:",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        # Скачивание фото
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Временное сохранение
        photo_path = f"temp_{message.chat.id}.jpg"
        with open(photo_path, 'wb') as f:
            f.write(downloaded_file)

        # Распознавание еды
        logmeal_data = analyze_photo_with_logmeal(photo_path)
        os.remove(photo_path)

        if 'error' in logmeal_data:
            raise Exception(logmeal_data['error'])

        # Проверяем вероятность распознавания
        if logmeal_data.get('prob', 1.0) < 0.5:  # Если prob < 50%
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row(
                telebot.types.KeyboardButton("📸 Сделать новое фото"),
                telebot.types.KeyboardButton("✍️ Ввести вручную")
            )

            bot.reply_to(message,
                         f"🤔 Я не уверен, что это ({translate_to_ru(logmeal_data['food_name'])})\n"
                         "Вероятность распознавания: {:.0f}%\n\n"
                         "Попробуйте сделать более четкое фото или введите название вручную:".format(
                             logmeal_data['prob'] * 100
                         ),
                         reply_markup=markup
                         )
            return

        food_name = logmeal_data['food_name']
        nutrition_data = get_nutritionix_data(food_name)

        if not nutrition_data:
            raise Exception("Не удалось получить данные о питательности")

        user_food_data[message.chat.id] = {
            'food_name': food_name,
            'nutrition_per_100g': nutrition_data,
            'photo_id': message.photo[-1].file_id
        }

        bot.reply_to(message,
                     f"🍴 Распознано: {translate_to_ru(food_name)} "
                     f"(уверенность: {logmeal_data['prob'] * 100:.0f}%)\n"
                     "📝 Введите вес порции в граммах:"
                     )

        # Регистрируем обработчик следующего сообщения
        bot.register_next_step_handler(message, process_portion_size)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "📸 Сделать новое фото")
def ask_for_new_photo(message):
    bot.reply_to(message, "📸 Пожалуйста, сделайте новое фото еды (лучше освещение, крупный план)")


@bot.message_handler(func=lambda message: message.text in ["✍️ Ввести вручную", "Ввести вручную"])
def ask_for_food_name(message):
    bot.reply_to(message,
                 "📝 Введите название продукта или блюда:\n"
                 "Пример: <i>банан, овсяная каша, куриная грудка</i>",
                 parse_mode="HTML"
                 )
    bot.register_next_step_handler(message, handle_manual_input)


def handle_manual_input(message):
    try:
        food_name = translate_to_en(message.text.strip())
        if not food_name:
            raise ValueError("Название не может быть пустым")

        nutrition_data = get_nutritionix_data(food_name)

        if not nutrition_data:
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("✍️ Уточнить запрос", "📋 Меню")

            bot.reply_to(message,
                         f"🔍 Не найдено данных для '{translate_to_ru(food_name)}'\n"
                         "Попробуйте уточнить название:",
                         reply_markup=markup
                         )
            bot.register_next_step_handler(message, handle_retry_input)
            return

        user_food_data[message.chat.id] = {
            'food_name': translate_to_ru(food_name),
            'nutrition_per_100g': nutrition_data
        }

        bot.reply_to(message,
                     f"🍴 Найдено: {translate_to_ru(food_name)}\n"
                     "📝 Введите вес порции в граммах:"
                     )
        bot.register_next_step_handler(message, process_portion_size)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")


def handle_retry_input(message):
    if message.text == "✍️ Уточнить запрос":
        ask_for_food_name(message)
    else:
        show_menu(message)

def process_portion_size(message):
    try:
        chat_id = message.chat.id
        portion_grams = float(message.text)

        if portion_grams <= 0:
            raise ValueError("Вес должен быть больше 0")

        # Получаем сохраненные данные
        food_info = user_food_data.get(chat_id)
        if not food_info:
            raise Exception("Сессия устарела")

        # Расчет КБЖУ
        nutrition = calculate_nutrition(portion_grams, food_info['nutrition_per_100g'])

        # Формируем ответ
        response = format_nutrition_response(
            food_info['food_name'],
            nutrition,
            portion_grams
        )

        # Кнопка сохранения
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            "💾 Сохранить",
            callback_data=f"save_{portion_grams}"
        ))

        bot.send_message(chat_id, response, reply_markup=markup)

    except ValueError:
        bot.reply_to(message, "🔢 Пожалуйста, введите число (например: 200)")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('save_'))
def handle_save(call):
    try:
        chat_id = call.message.chat.id
        portion_grams = float(call.data.split('_')[1])
        food_info = user_food_data.get(chat_id)

        if not food_info:
            bot.answer_callback_query(call.id, "❌ Сессия устарела")
            return

        save_to_diary(
            chat_id=chat_id,
            food_name=food_info['food_name'],
            portion_grams=portion_grams,
            nutrition_data=calculate_nutrition(portion_grams, food_info['nutrition_per_100g']),
            photo_id=food_info.get('photo_id')
        )

        bot.answer_callback_query(call.id, "✅ Сохранено в дневник!")
        bot.send_message(chat_id, "🍽 Запись добавлена в дневник (/diary)")

    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")


# --- Запуск --- #
if __name__ == '__main__':
    print("🟢 Бот запущен")
    bot.infinity_polling()