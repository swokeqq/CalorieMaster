import telebot
import requests
import os
from dotenv import load_dotenv
from database import init_db, save_to_diary, get_diary_entries, translate  # Импорт из database.py

# --- Конфигурация --- #
load_dotenv()
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

# API Keys
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


# --- Вспомогательные функции --- #

def analyze_photo_with_logmeal(file_path):
    """Распознает еду на фото через Logmeal API"""
    try:
        with open(file_path, 'rb') as image_file:
            response = requests.post(
                LOGMEAL_ENDPOINT,
                files={'image': image_file},
                headers=LOGMEAL_HEADERS
            )
        data = response.json()
        return {'food_name': data['segmentation_results'][0]['recognition_results'][0]['name']}
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
        # 'serving_weight': food.get('serving_weight_grams', 100)
        'serving_weight': food['serving_weight_grams']
    }


def calculate_nutrition(portion_grams, nutrition_data):
    """Пересчет КБЖУ с учетом исходного веса порции"""
    if not nutrition_data or 'serving_weight' not in nutrition_data:
        return None

    # Если вес порции не указан, считаем что 100г
    base_weight = nutrition_data.get('serving_weight', 100)

    # Коэффициент для пересчета
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
        f"🍏 {translate(food_name)}\n"
        f"⚖️ Порция: {portion_grams}г\n\n"
        f"Энергетическая ценность:\n"
        f"🔥 {nutrition_data['calories']} ккал\n"
        f"🥩 {nutrition_data['protein']}г белков\n"
        f"🥑 {nutrition_data['fat']}г жиров\n"
        f"🍞 {nutrition_data['carbs']}г углеводов"
    )


# --- Обработчики команд --- #
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "📌 Отправьте фото еды для анализа или /diary для просмотра дневника")


@bot.message_handler(commands=['diary'])
def show_diary(message):
    entries = get_diary_entries(message.chat.id)
    if not entries:
        bot.reply_to(message, "🍽 Дневник пуст. Отправьте фото еды чтобы начать!")
        return

    response = ["📅 Ваш дневник питания:"]
    for entry in entries[:10]:  # Показываем последние 10 записей
        response.append(
            f"\n{entry[2]} | {entry[3]} ({entry[4]}г)\n"
            f"🔥 {entry[5]} ккал | 🥩 {entry[6]}г белков"
        )

    bot.reply_to(message, "\n".join(response))


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

        food_name = logmeal_data['food_name']
        nutrition_data = get_nutritionix_data(food_name)

        if not nutrition_data:
            raise Exception("Не удалось получить данные о питательности")

        # Сохраняем данные для следующего шага
        user_food_data[message.chat.id] = {
            'food_name': food_name,
            'nutrition_per_100g': nutrition_data,
            'photo_id': message.photo[-1].file_id
        }

        # Запрашиваем вес порции
        bot.reply_to(message, f"🍴 Распознано: {translate(food_name)}\n"
                              "📝 Введите вес порции в граммах:")

        # Регистрируем обработчик следующего сообщения
        bot.register_next_step_handler(message, process_portion_size)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")


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

        # Сохранение в БД
        save_to_diary(
            chat_id=chat_id,
            food_name=food_info['food_name'],
            portion_grams=portion_grams,
            nutrition_data=calculate_nutrition(portion_grams, food_info['nutrition_per_100g']),
            photo_id=food_info['photo_id']
        )

        bot.answer_callback_query(call.id, "✅ Сохранено в дневник!")
        bot.send_message(chat_id, "🍽 Запись добавлена в дневник (/diary)")

    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")


# --- Запуск --- #
if __name__ == '__main__':
    print("🟢 Бот запущен")
    bot.infinity_polling()