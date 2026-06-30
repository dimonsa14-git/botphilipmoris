import asyncio
import random
import sqlite3
import re
import os
import subprocess
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

TOKEN = "8954746188:AAFEYN0LGfjz0LyZ9fLpfjZt8EIu_EUpSj0"

FILE_NAME = "numbers.txt"
DB_NAME = "numbers.db"

# -----------------------
# GIT АВТОПУШ
# -----------------------

GIT_TOKEN = os.getenv("GITHUB_TOKEN")
GIT_REPO = os.getenv("GITHUB_REPO")          # например: "username/reponame"
GIT_USER_NAME = os.getenv("GITHUB_USERNAME", "railway-bot")
GIT_USER_EMAIL = os.getenv("GIT_USER_EMAIL", "railway-bot@example.com")
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")


def run(cmd):
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    )


def git_init_if_needed():
    """Настраивает git и remote с токеном при каждом старте контейнера."""
    if not GIT_TOKEN or not GIT_REPO:
        print("⚠️ GIT_TOKEN/GIT_REPO не заданы — автопуш отключён")
        return

    remote_url = f"https://{GIT_TOKEN}@github.com/{GIT_REPO}.git"

    if not os.path.exists(".git"):
        run("git init")
        run(f'git remote add origin {remote_url}')
        run(f'git config user.name "{GIT_USER_NAME}"')
        run(f'git config user.email "{GIT_USER_EMAIL}"')
        run(f"git fetch origin {GIT_BRANCH}")
        run(f"git checkout -t origin/{GIT_BRANCH}")
    else:
        # .git уже есть (скопирован вместе с репозиторием при сборке Dockerfile),
        # но remote там без токена — обязательно прописываем его заново
        run(f'git config user.name "{GIT_USER_NAME}"')
        run(f'git config user.email "{GIT_USER_EMAIL}"')
        check = run("git remote get-url origin")
        if check.returncode != 0:
            run(f'git remote add origin {remote_url}')
        else:
            run(f'git remote set-url origin {remote_url}')

    print("🔧 Git настроен, remote установлен")


def git_pull_latest():
    """Принудительно приводит локальные файлы к последней версии из GitHub."""
    if not GIT_TOKEN or not GIT_REPO:
        return
    fetch_result = run(f"git fetch origin {GIT_BRANCH}")
    print("ℹ️ git fetch:", (fetch_result.stdout + fetch_result.stderr).strip())

    reset_result = run(f"git reset --hard origin/{GIT_BRANCH}")
    print("ℹ️ git reset --hard:", (reset_result.stdout + reset_result.stderr).strip())

    ensure_writable_files()


def ensure_writable_files():
    """Гарантирует, что файлы данных доступны для записи (git может ставить readonly права)."""
    for f in [FILE_NAME, DB_NAME]:
        if os.path.exists(f):
            try:
                os.chmod(f, 0o666)
            except Exception as e:
                print(f"⚠️ Не удалось снять readonly с {f}:", e)


def git_push(message="update data"):
    """Коммитит и пушит numbers.txt и numbers.db в GitHub."""
    if not GIT_TOKEN or not GIT_REPO:
        print("⚠️ git_push пропущен: GIT_TOKEN/GIT_REPO не заданы")
        return

    add_result = run(f"git add {FILE_NAME} {DB_NAME}")
    if add_result.returncode != 0:
        print("❌ Ошибка git add:", add_result.stderr)

    result = run(f'git commit -m "{message}"')
    print("ℹ️ git commit:", (result.stdout + result.stderr).strip())

    # если нечего коммитить — git commit вернёт ошибку, это нормально
    if "nothing to commit" in result.stdout + result.stderr:
        print("ℹ️ Нечего коммитить, пуш не требуется")
        return

    push_result = run(f"git push origin {GIT_BRANCH}")
    if push_result.returncode != 0:
        print("❌ Ошибка git push:", push_result.stderr)
    else:
        print("✅ Изменения запушены в GitHub")


# -----------------------
# БАЗА ДАННЫХ
# -----------------------

conn = None
cursor = None


def init_db():
    """Подключается к БД. Обязательно вызывать ПОСЛЕ git pull, иначе соединение
    будет держать устаревший файловый дескриптор от файла, который git заменит."""
    global conn, cursor
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_numbers (
        user_id INTEGER,
        phone TEXT,
        month TEXT
    )
    """)
    conn.commit()
    print("🗄️ БД подключена")


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

    # Пушим обновлённую БД в GitHub
    git_push(f"used number by {user_id}")

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
        r"0(39|50|63|66|67|68|73|91|92|93|94|95|96|97|98|99|75|77)\d{7}",
        phone
    ):
        await message.answer(
            "❌ Неверный формат номера.\n\n"
            "Пример:\n"
            "0681234567"
        )
        return

    waiting_users.remove(user_id)

    if save_number(phone):
        await message.answer(
            f"✅ Номер добавлен:\n{phone}"
        )
        # Пушим обновлённый список номеров в GitHub
        git_push(f"added number {phone}")
    else:
        await message.answer(
            "❌ Такой номер уже существует."
        )

# -----------------------
# ЗАПУСК
# -----------------------

async def main():
    git_init_if_needed()
    ensure_writable_files()
    git_pull_latest()
    ensure_writable_files()
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
