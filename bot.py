import asyncio
import random
import sqlite3
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

TOKEN = "8961143201:AAFdQ3OUoIIfoDZ8RHN_wRLTKLAjMyWndNM"

FILE_NAME = "numbers.txt"

# -----------------------
# БАЗА ДАННЫХ
# -----------------------

conn = sqlite3.connect("numbers.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_numbers (
    user_id INTEGER,
    phone TEXT,
    month TEXT
)
""")

conn.commit()

# -----------------------
# РАБОТА С НОМЕРАМИ
# -----------------------

def load_numbers():
    try:
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_number(phone):
    phone = phone.strip()

    numbers = load_numbers()

    if phone in numbers:
        return False

    with open(FILE_NAME, "a", encoding="utf-8") as f:
        if numbers:
            f.write("\n")
        f.write(phone)

    return True

# -----------------------
# БОТ
# -----------------------

bot = Bot(token=TOKEN)
dp = Dispatcher()

waiting_users = set()

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Дать номер")],
        [KeyboardButton(text="➕ Добавить номер")],
        [KeyboardButton(text="📊 Статистика")]
    ],
    resize_keyboard=True
)

# -----------------------
# START
# -----------------------

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "✅ Бот запущен",
        reply_markup=keyboard
    )
# -----------------------
# СТАТИСТИКА
# -----------------------

@dp.message(F.text == "📊 Статистика")
async def statistics(message: Message):

    user_id = message.from_user.id
    month = datetime.now().strftime("%Y-%m")

    all_numbers = load_numbers()
    total_numbers = len(all_numbers)

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM user_numbers
        WHERE user_id = ? AND month = ?
        """,
        (user_id, month)
    )

    used_count = cursor.fetchone()[0]

    remaining = max(0, total_numbers - used_count)

    await message.answer(
        f"📊 Твоя статистика\n\n"
        f"📚 Всего номеров в базе: {total_numbers}\n"
        f"✅ Ты уже использовал: {used_count}\n"
        f"🆕 Осталось новых номеров: {remaining}"
    )
# -----------------------
# ВЫДАЧА НОМЕРА
# -----------------------

@dp.message(F.text == "📱 Дать номер")
async def give_number(message: Message):

    user_id = message.from_user.id
    month = datetime.now().strftime("%Y-%m")

    all_numbers = load_numbers()

    if not all_numbers:
        await message.answer(
            "❌ В базе нет номеров."
        )
        return

    cursor.execute(
        "SELECT phone FROM user_numbers WHERE user_id=? AND month=?",
        (user_id, month)
    )

    used = [row[0] for row in cursor.fetchall()]

    available = [
        n for n in all_numbers
        if n not in used
    ]

    if not available:
        await message.answer(
            "❌ Ты уже использовал все номера в этом месяце."
        )
        return

    number = random.choice(available)

    cursor.execute(
        "INSERT INTO user_numbers VALUES (?, ?, ?)",
        (user_id, number, month)
    )

    conn.commit()

    await message.answer(
        f"📞 Номер:\n{number}"
    )

# -----------------------
# ДОБАВЛЕНИЕ НОМЕРА
# -----------------------

@dp.message(F.text == "➕ Добавить номер")
async def add_number_start(message: Message):

    waiting_users.add(message.from_user.id)

    await message.answer(
        "📥 Отправь номер.\n\n"
        "Пример:\n"
        "0681234567"
    )

# -----------------------
# ПОЛУЧЕНИЕ НОМЕРА
# -----------------------

@dp.message()
async def receive_number(message: Message):

    user_id = message.from_user.id

    if user_id not in waiting_users:
        return

    phone = message.text.strip()

    # Проверка украинского мобильного номера
    if not re.fullmatch(
        r"0(39|50|63|66|67|68|73|91|92|93|94|95|96|97|98|99)\d{7}",
        phone
    ):
        await message.answer(
            "❌ Неверный формат номера.\n\n"
            "Пример:\n"
            "0683178588"
        )
        return

    waiting_users.remove(user_id)

    if save_number(phone):
        await message.answer(
            f"✅ Номер добавлен:\n{phone}"
        )
    else:
        await message.answer(
            "❌ Такой номер уже существует."
        )

# -----------------------
# ЗАПУСК
# -----------------------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
