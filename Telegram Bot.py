import telebot
import requests
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()
# Инициализация бота
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

LOGMEAL_API_KEY = os.getenv('LOGMEAL_API_KEY')
ENDPOINT = "https://api.logmeal.com/v2/image/segmentation/complete"
headers = {'Authorization': 'Bearer ' + LOGMEAL_API_KEY}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Отправь мне фото блюда, и я скажу, сколько в нем калорий.")

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

        # Отправляем фото в Logmeal API для анализа
        food_name = recognize_food(photo_path)

        # Удаляем временный файл
        os.remove(photo_path)

        # Отправляем результат пользователю
        bot.reply_to(message, f"На фото: {food_name}\nКалорийность: ??? ккал")# {calories} ккал")
 
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")

def recognize_food(file_path):
    try:
        valid_extensions = ['.jpg', '.jpeg', '.png']
        if not any(file_path.lower().endswith(ext) for ext in valid_extensions):
            return "Неподдерживаемый формат файла. Используйте JPG/PNG."
        response = requests.post(ENDPOINT, files={'image': open(file_path, 'rb')}, headers=headers).json()
        return get_name(response)

    except Exception as e: return f"Произошла ошибка: {str(e)}"

def get_name(data):
    try:
        recognition_results = data['segmentation_results'][0]['recognition_results']
        result = max(recognition_results, key=lambda x: x['prob'])
        return (result['name'])

    except KeyError:  return "Не удалось распознать блюдо на фото"

# Запуск бота

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling(none_stop=True)