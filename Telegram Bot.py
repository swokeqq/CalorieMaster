import telebot
import requests
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()
# Инициализация бота
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

LOGMEAL_API_KEY = os.getenv('LOGMEAL_API_KEY')
LOGMEAL_ENDPOINT = "https://api.logmeal.com/v2/image/segmentation/complete"
LOGMEAL_HEADERS = {'Authorization': 'Bearer ' + LOGMEAL_API_KEY}

# Nutritionix API credentials
NUTRITIONIX_APP_ID = os.getenv('NUTRITIONIX_APP_ID')
NUTRITIONIX_APP_KEY = os.getenv('NUTRITIONIX_APP_KEY')
NUTRITIONIX_ENDPOINT = "https://trackapi.nutritionix.com/v2/natural/nutrients"


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Отправь мне фото блюда, и я рассчитаю его калорийность и БЖУ на 100 грамм.")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        # Получаем информацию о фото
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Сохраняем фото временно
        photo_path = f"temp_photo_{message.chat.id}.jpg"
        with open(photo_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        # Анализируем фото в Logmeal API
        logmeal_response = analyze_photo_with_logmeal(photo_path)
        os.remove(photo_path)  # Удаляем временный файл

        if not logmeal_response or 'error' in logmeal_response:
            error_msg = logmeal_response.get('error', 'Не удалось проанализировать фото')
            bot.reply_to(message, error_msg)
            return

        food_name = logmeal_response['food_name']

        # Получаем данные о питательной ценности из Nutritionix
        nutrition_data = get_nutritionix_data(food_name)

        if not nutrition_data:
            bot.reply_to(message, f"На фото: {food_name}\nНе удалось получить данные о питательной ценности.")
            return

        # Рассчитываем КБЖУ на 100 грамм
        calculated_nutrition = calculate_nutrition_per_100g(nutrition_data)

        # Формируем ответ
        response_text = format_nutrition_response(food_name, calculated_nutrition)

        # Отправляем результат пользователю
        bot.reply_to(message, response_text)

    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")


def analyze_photo_with_logmeal(file_path):
    """Анализирует фото блюда через Logmeal API и возвращает название"""
    try:
        valid_extensions = ['.jpg', '.jpeg', '.png']
        if not any(file_path.lower().endswith(ext) for ext in valid_extensions):
            return {'error': "Неподдерживаемый формат файла. Используйте JPG/PNG."}

        # Отправляем фото в Logmeal API
        with open(file_path, 'rb') as image_file:
            response = requests.post(
                LOGMEAL_ENDPOINT,
                files={'image': image_file},
                headers=LOGMEAL_HEADERS
            )

        if response.status_code != 200:
            return {'error': f"Ошибка API Logmeal: {response.status_code}"}

        data = response.json()

        # Получаем название блюда
        try:
            recognition_results = data['segmentation_results'][0]['recognition_results']
            best_match = max(recognition_results, key=lambda x: x['prob'])
            return {'food_name': best_match['name']}
        except (KeyError, IndexError):
            return {'error': "Не удалось распознать блюдо на фото"}

    except Exception as e:
        return {'error': f"Ошибка при анализе фото: {str(e)}"}


def get_nutritionix_data(food_name):
    """Получаем данные о питательной ценности из Nutritionix API"""
    try:
        headers = {
            'x-app-id': NUTRITIONIX_APP_ID,
            'x-app-key': NUTRITIONIX_APP_KEY,
            'Content-Type': 'application/json'
        }

        payload = {
            'query': food_name,
            'timezone': 'US/Eastern'
        }

        response = requests.post(NUTRITIONIX_ENDPOINT, json=payload, headers=headers)
        data = response.json()

        if response.status_code == 200 and 'foods' in data and len(data['foods']) > 0:
            food = data['foods'][0]
            return {
                'calories': food.get('nf_calories', 0),
                'protein': food.get('nf_protein', 0),
                'fat': food.get('nf_total_fat', 0),
                'carbs': food.get('nf_total_carbohydrate', 0),
                'serving_weight': food.get('serving_weight_grams', 100)  # Вес порции в граммах
            }
        return None

    except Exception as e:
        print(f"Ошибка при запросе к Nutritionix: {str(e)}")
        return None


def calculate_nutrition_per_100g(nutrition_data):
    """Рассчитывает КБЖУ на 100 грамм блюда"""
    try:
        serving_weight = nutrition_data.get('serving_weight', 100)

        # Коэффициент для пересчета на 100 грамм
        if serving_weight == 0:  # Защита от деления на 0
            serving_weight = 100
        coefficient = 100 / serving_weight

        return {
            'calories': round(nutrition_data['calories'] * coefficient, 1),
            'protein': round(nutrition_data['protein'] * coefficient, 1),
            'fat': round(nutrition_data['fat'] * coefficient, 1),
            'carbs': round(nutrition_data['carbs'] * coefficient, 1)
        }
    except Exception as e:
        print(f"Ошибка при расчете КБЖУ: {str(e)}")
        return None


def format_nutrition_response(food_name, nutrition_data):
    """Форматирует данные о питательной ценности в читаемое сообщение"""
    if not nutrition_data:
        return f"На фото: {food_name}\nНе удалось рассчитать питательную ценность."

    response_lines = [
        f"На фото: {food_name}",
        "",
        "Пищевая ценность на 100 г:",
        f"Калории: {nutrition_data['calories']} ккал",
        f"Белки: {nutrition_data['protein']} г",
        f"Жиры: {nutrition_data['fat']} г",
        f"Углеводы: {nutrition_data['carbs']} г",
        "",
        "Данные приблизительные и могут отличаться от фактических."
    ]

    return "\n".join(response_lines)


if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling(none_stop=True)
