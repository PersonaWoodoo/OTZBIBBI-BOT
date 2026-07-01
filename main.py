# ============================================
# 📁 bot.py - ГОТОВЫЙ КОД С ВАШИМ ТОКЕНОМ
# ============================================

import asyncio
import sqlite3
import random
import string
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import logging

# ========== КОНФИГ ==========
BOT_TOKEN = "8910370046:AAFftfaASfcEn4iUhRU6HSAt2ruYLOshMT4"  # ВАШ ТОКЕН
BOT_USERNAME = "Client_voice_bot"  # ВАШ USERNAME
ADMIN_IDS = [8478884644]  # Ваш ID
CHANNEL_ID = "@ваш_канал"  # Замените на ваш канал

GET_TO_STARS = {
    50000: {"name": "🐻 Мишка", "stars": 15},
    150000: {"name": "🎁 Подарок 25⭐", "stars": 25},
    300000: {"name": "🎁 Подарок 50⭐", "stars": 50},
    600000: {"name": "🎁 Подарок 100⭐", "stars": 100},
}

DB_NAME = "bot.db"

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(level=logging.INFO)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 5000,
            ref_code TEXT UNIQUE,
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            username TEXT,
            theme TEXT,
            count INTEGER,
            review_type TEXT,
            example_text TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            user_id INTEGER,
            review_text TEXT,
            created_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            request_id TEXT UNIQUE,
            stars_amount INTEGER,
            get_amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            get_amount INTEGER,
            stars_amount INTEGER,
            gift_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_get INTEGER DEFAULT 5000,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            bonus_get INTEGER,
            uses_limit INTEGER,
            used_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER,
            user_id INTEGER,
            created_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def db_execute(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    result = cur.fetchall()
    conn.close()
    return result

def get_user(user_id):
    result = db_execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result[0] if result else None

def create_user(user_id, username, ref_code=None):
    existing = get_user(user_id)
    if existing:
        return existing
    
    ref_code_new = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    referred_by = None
    if ref_code:
        referrer = db_execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
        if referrer:
            referred_by = referrer[0][0]
    
    db_execute("""
        INSERT INTO users (user_id, username, ref_code, referred_by, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, ref_code_new, referred_by, datetime.now().isoformat()))
    
    if referred_by:
        db_execute("""
            UPDATE users SET balance = balance + 5000 WHERE user_id = ?
        """, (referred_by,))
        db_execute("""
            INSERT INTO referrals (referrer_id, referred_id, created_at)
            VALUES (?, ?, ?)
        """, (referred_by, user_id, datetime.now().isoformat()))
        
        asyncio.create_task(bot.send_message(
            referred_by,
            f"🎉 Новый реферал @{username}!\n💰 +5000 GET на баланс!"
        ))
    
    return get_user(user_id)

def add_balance(user_id, amount):
    db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

def subtract_balance(user_id, amount):
    user = get_user(user_id)
    if user and user[2] >= amount:
        db_execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        return True
    return False

def generate_request_id():
    return f"REQ-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=6))}"

# ========== КЛАВИАТУРЫ ==========
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать задание")],
            [KeyboardButton(text="📋 Задания для выполнения")],
            [KeyboardButton(text="💰 Мой баланс"), KeyboardButton(text="👥 Рефералы")],
            [KeyboardButton(text="💎 Пополнить GET"), KeyboardButton(text="🎁 Обменять GET")],
            [KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

def admin_keyboard():
    buttons = [
        [KeyboardButton(text="👥 Пользователи")],
        [KeyboardButton(text="💳 Заявки на пополнение")],
        [KeyboardButton(text="💸 Заявки на вывод")],
        [KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="🔨 Управление балансом")],
        [KeyboardButton(text="🚫 Баны")],
        [KeyboardButton(text="🎟 Создать промокод")],
        [KeyboardButton(text="➕ Добавить канал в подписку")],
        [KeyboardButton(text="⬅️ Выйти из админки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )

def task_actions_keyboard(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать отзыв", callback_data=f"do_task_{task_id}")],
        [InlineKeyboardButton(text="🔙 Назад к заданиям", callback_data="back_to_tasks")]
    ])

def gift_selection_keyboard():
    buttons = []
    for get_amount, info in GET_TO_STARS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{info['name']} ({get_amount} GET)",
            callback_data=f"gift_{get_amount}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== СОСТОЯНИЯ ==========
class CreateTaskStates(StatesGroup):
    username = State()
    theme = State()
    count = State()
    review_type = State()
    example = State()
    confirm = State()

class DepositStates(StatesGroup):
    amount = State()
    confirm = State()

class WithdrawStates(StatesGroup):
    gift = State()
    confirm = State()

class AdminStates(StatesGroup):
    broadcast = State()
    ban_user = State()
    unban_user = State()
    add_balance = State()
    remove_balance = State()
    promo_code = State()
    promo_bonus = State()
    promo_limit = State()
    channel_add = State()

class ReviewStates(StatesGroup):
    writing = State()

# ========== ПРОВЕРКА ПОДПИСКИ ==========
async def check_subscription(user_id):
    if not CHANNEL_ID or CHANNEL_ID == "@ваш_канал":
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ========== ХЕНДЛЕРЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    args = message.text.split()
    ref_code = args[1] if len(args) > 1 else None
    
    user = create_user(user_id, username, ref_code)
    
    if user and user[4] == 1:
        await message.answer("🚫 Вы забанены!")
        return
    
    if not await check_subscription(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]
        ])
        await message.answer(
            f"👋 Привет, {username}!\n\n"
            f"📢 Подпишись на канал, чтобы пользоваться ботом: {CHANNEL_ID}",
            reply_markup=keyboard
        )
        return
    
    await message.answer(
        f"👋 Привет, {username}!\n\n"
        f"📝 Выберите раздел ниже для продолжения:\n\n"
        f"💰 Баланс: {user[2]} GET",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена! Можете пользоваться ботом.")
        await cmd_start(callback.message, FSMContext())
    else:
        await callback.answer("❌ Вы еще не подписались!", show_alert=True)

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if message.from_user.id in ADMIN_IDS:
        await message.answer("🔙 Возврат в админ-панель", reply_markup=admin_keyboard())
    else:
        await message.answer("🔙 Главное меню", reply_markup=main_keyboard())

@dp.message(F.text == "📝 Создать задание")
async def create_task_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[4] == 1:
        await message.answer("🚫 Доступ запрещен")
        return
    
    if user[2] < 5000:
        await message.answer(
            f"❌ Недостаточно средств!\n"
            f"Создание задания стоит 5000 GET\n"
            f"Ваш баланс: {user[2]} GET\n\n"
            f"Пополните баланс в разделе 💎 Пополнить GET"
        )
        return
    
    await message.answer(
        "📝 Создание нового задания\n\n"
        "Укажите @username для отзыва (только с @):",
        reply_markup=back_keyboard()
    )
    await state.set_state(CreateTaskStates.username)

@dp.message(CreateTaskStates.username)
async def create_task_username(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    username = message.text.strip()
    if not username.startswith("@"):
        await message.answer("❌ Username должен начинаться с @\nПопробуйте снова:")
        return
    
    await state.update_data(username=username)
    await message.answer(
        "Укажите тематику для отзыва:\n"
        "(18+ и скам-контент не принимаются)",
        reply_markup=back_keyboard()
    )
    await state.set_state(CreateTaskStates.theme)

@dp.message(CreateTaskStates.theme)
async def create_task_theme(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    theme = message.text.strip()
    forbidden = ["18+", "скам", "мошенник", "обман", "порно", "секс", "наркотики"]
    if any(word in theme.lower() for word in forbidden):
        await message.answer("❌ Запрещенная тематика! Пожалуйста, укажите другую тему:")
        return
    
    await state.update_data(theme=theme)
    await message.answer(
        "Укажите количество отзывов (цифра):",
        reply_markup=back_keyboard()
    )
    await state.set_state(CreateTaskStates.count)

@dp.message(CreateTaskStates.count)
async def create_task_count(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    try:
        count = int(message.text.strip())
        if count <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное число:")
        return
    
    await state.update_data(count=count)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👍 Положительный")],
            [KeyboardButton(text="👎 Негативный")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите тип отзыва:", reply_markup=keyboard)
    await state.set_state(CreateTaskStates.review_type)

@dp.message(CreateTaskStates.review_type)
async def create_task_type(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    if message.text not in ["👍 Положительный", "👎 Негативный"]:
        await message.answer("❌ Выберите один из вариантов:")
        return
    
    review_type = "positive" if "Положительный" in message.text else "negative"
    await state.update_data(review_type=review_type)
    await message.answer(
        "📝 Напишите пример отзыва (образец):",
        reply_markup=back_keyboard()
    )
    await state.set_state(CreateTaskStates.example)

@dp.message(CreateTaskStates.example)
async def create_task_example(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    example = message.text.strip()
    await state.update_data(example=example)
    
    data = await state.get_data()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подтвердить")],
            [KeyboardButton(text="❌ Отменить")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"📋 Проверьте данные:\n\n"
        f"👤 Username: {data['username']}\n"
        f"📂 Тема: {data['theme']}\n"
        f"🔢 Количество: {data['count']}\n"
        f"📊 Тип: {'Положительный' if data['review_type'] == 'positive' else 'Негативный'}\n"
        f"📝 Пример: {data['example'][:100]}...\n\n"
        f"💰 Стоимость: 5000 GET\n\n"
        f"Подтвердить создание?",
        reply_markup=keyboard
    )
    await state.set_state(CreateTaskStates.confirm)

@dp.message(CreateTaskStates.confirm)
async def create_task_confirm(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    if message.text == "❌ Отменить":
        await state.clear()
        await message.answer("❌ Создание отменено", reply_markup=main_keyboard())
        return
    
    if message.text != "✅ Подтвердить":
        await message.answer("❌ Нажмите 'Подтвердить' или 'Отменить'")
        return
    
    data = await state.get_data()
    user_id = message.from_user.id
    
    if not subtract_balance(user_id, 5000):
        await message.answer("❌ Ошибка: недостаточно средств")
        await state.clear()
        return
    
    db_execute("""
        INSERT INTO tasks (creator_id, username, theme, count, review_type, example_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, data['username'], data['theme'], data['count'], 
          data['review_type'], data['example'], datetime.now().isoformat()))
    
    task_id = db_execute("SELECT last_insert_rowid()")[0][0]
    
    await state.clear()
    await message.answer(
        f"✅ Задание #{task_id} создано!\n\n"
        f"👤 Username: {data['username']}\n"
        f"📂 Тема: {data['theme']}\n"
        f"🔢 Количество: {data['count']}\n"
        f"💰 Создание стоило: 5000 GET\n"
        f"Текущий баланс: {get_user(user_id)[2]} GET",
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "📋 Задания для выполнения")
async def show_tasks(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[4] == 1:
        await message.answer("🚫 Доступ запрещен")
        return
    
    tasks = db_execute("""
        SELECT id, username, theme, count, review_type, example_text, creator_id 
        FROM tasks WHERE status = 'active'
    """)
    
    if not tasks:
        await message.answer("📭 Активных заданий нет", reply_markup=main_keyboard())
        return
    
    text = "📋 Доступные задания:\n\n"
    for task in tasks:
        task_id, username, theme, count, review_type, example, creator_id = task
        text += (
            f"🆔 Задание #{task_id}\n"
            f"👤 Для: {username}\n"
            f"📂 Тема: {theme}\n"
            f"📊 Тип: {'Положительный' if review_type == 'positive' else 'Негативный'}\n"
            f"📝 Пример: {example[:50]}...\n"
            f"📌 Осталось: {count}\n"
            f"💰 Награда: 5000 GET\n"
            f"{'='*20}\n\n"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Задание #{task[0]}", callback_data=f"task_{task[0]}")] 
        for task in tasks[:10]
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    await message.answer(text[:4000], reply_markup=keyboard)

@dp.callback_query(F.data.startswith("task_"))
async def view_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    
    if not task:
        await callback.answer("❌ Задание не найдено")
        return
    
    task = task[0]
    text = (
        f"📋 Задание #{task[0]}\n\n"
        f"👤 Для: {task[2]}\n"
        f"📂 Тема: {task[3]}\n"
        f"📊 Тип: {'Положительный' if task[5] == 'positive' else 'Негативный'}\n"
        f"📝 Пример отзыва:\n{task[6]}\n\n"
        f"💰 Награда: 5000 GET"
    )
    
    await callback.message.edit_text(text, reply_markup=task_actions_keyboard(task_id))

@dp.callback_query(F.data.startswith("do_task_"))
async def do_task(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    user = get_user(user_id)
    if not user or user[4] == 1:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    existing = db_execute("""
        SELECT * FROM task_completions WHERE task_id = ? AND user_id = ?
    """, (task_id, user_id))
    if existing:
        await callback.answer("❌ Вы уже выполнили это задание", show_alert=True)
        return
    
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        await callback.answer("❌ Задание не найдено")
        return
    
    task = task[0]
    
    if task[1] == user_id:
        await callback.answer("❌ Вы не можете выполнить свое задание", show_alert=True)
        return
    
    await state.update_data(task_id=task_id, task_data=task)
    await callback.message.edit_text(
        f"✍️ Напишите текст отзыва для задания #{task_id}\n\n"
        f"📝 Пример:\n{task[6]}\n\n"
        f"Напишите свой отзыв в чат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_tasks")]
        ])
    )
    await state.set_state(ReviewStates.writing)

@dp.message(ReviewStates.writing)
async def submit_review(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['task_id']
    task = data['task_data']
    review_text = message.text.strip()
    
    if len(review_text) < 10:
        await message.answer("❌ Отзыв слишком короткий (минимум 10 символов). Напишите еще раз:")
        return
    
    db_execute("""
        INSERT INTO task_completions (task_id, user_id, review_text, created_at)
        VALUES (?, ?, ?, ?)
    """, (task_id, message.from_user.id, review_text, datetime.now().isoformat()))
    
    db_execute("UPDATE tasks SET count = count - 1 WHERE id = ?", (task_id,))
    
    task_check = db_execute("SELECT count FROM tasks WHERE id = ?", (task_id,))
    if task_check and task_check[0][0] == 0:
        db_execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
    
    add_balance(message.from_user.id, 5000)
    
    creator_id = task[1]
    try:
        await bot.send_message(
            creator_id,
            f"📩 Новый отзыв для задания #{task_id}!\n\n"
            f"От: @{message.from_user.username or 'unknown'}\n"
            f"Текст:\n{review_text}"
        )
    except:
        pass
    
    await state.clear()
    await message.answer(
        f"✅ Отзыв для задания #{task_id} принят!\n"
        f"💰 +5000 GET на баланс\n"
        f"Текущий баланс: {get_user(message.from_user.id)[2]} GET",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "back_to_tasks")
async def back_to_tasks_callback(callback: CallbackQuery):
    await callback.message.delete()
    await show_tasks(callback.message)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.delete()
    user = get_user(callback.from_user.id)
    await callback.message.answer("Главное меню", reply_markup=main_keyboard())

@dp.message(F.text == "💰 Мой баланс")
async def show_balance(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    
    await message.answer(
        f"💰 Ваш баланс:\n"
        f"{user[2]} GET\n\n"
        f"1 ⭐ = 1000 GET\n"
        f"Минимальное пополнение: 15 ⭐"
    )

@dp.message(F.text == "👥 Рефералы")
async def show_referrals(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    refs = db_execute("SELECT referred_id FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
    count = len(refs)
    
    await message.answer(
        f"👥 Ваша реферальная система:\n\n"
        f"🔗 Ваш код: {user[3]}\n"
        f"👤 Приглашено: {count} чел.\n"
        f"💰 За каждого: +5000 GET\n\n"
        f"Ссылка для приглашения:\n"
        f"https://t.me/{BOT_USERNAME}?start={user[3]}"
    )

@dp.message(F.text == "💎 Пополнить GET")
async def deposit_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[4] == 1:
        return
    
    await message.answer(
        f"💎 Пополнение баланса GET\n\n"
        f"1 ⭐ = 1000 GET\n"
        f"Минимальное пополнение: 15 ⭐\n\n"
        f"Укажите сумму в ⭐ (от 15):",
        reply_markup=back_keyboard()
    )
    await state.set_state(DepositStates.amount)

@dp.message(DepositStates.amount)
async def deposit_amount(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await back_to_main(message, state)
        return
    
    try:
        stars = int(message.text.strip())
        if stars < 15:
            await message.answer("❌ Минимальное пополнение: 15 ⭐")
            return
    except:
        await message.answer("❌ Введите число:")
        return
    
    get_amount = stars * 1000
    request_id = generate_request_id()
    
    db_execute("""
        INSERT INTO deposit_requests (user_id, request_id, stars_amount, get_amount, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (message.from_user.id, request_id, stars, get_amount, datetime.now().isoformat()))
    
    await state.update_data(deposit_stars=stars, deposit_get=get_amount, deposit_req_id=request_id)
    
    await message.answer(
        f"📝 Заявка #{request_id} создана!\n\n"
        f"Сумма: {stars} ⭐ = {get_amount} GET\n\n"
        f"💳 Для оплаты переведите {stars} ⭐ админу:\n"
        f"👤 @debashev\n\n"
        f"⚠️ ВАЖНО: в комментарии к переводу укажите код:\n"
        f"`{request_id}`\n\n"
        f"📸 После перевода отправьте скриншот в этот чат.",
        reply_markup=back_keyboard()
    )
    await state.set_state(DepositStates.confirm)

@dp.message(DepositStates.confirm, F.photo)
async def deposit_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    request_id = data.get('deposit_req_id')
    
    if not request_id:
        await message.answer("❌ Ошибка, начните пополнение заново")
        await state.clear()
        return
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                message.photo[-1].file_id,
                caption=f"📩 Новая заявка на пополнение\n\n"
                       f"ID: {request_id}\n"
                       f"От: @{message.from_user.username or message.from_user.id}\n"
                       f"Сумма: {data.get('deposit_stars')} ⭐ = {data.get('deposit_get')} GET\n\n"
                       f"Для подтверждения нажмите:\n"
                       f"/confirm_deposit {request_id} {data.get('deposit_stars')} {data.get('deposit_get')} {message.from_user.id}"
            )
        except:
            pass
    
    await state.clear()
    await message.answer(
        f"✅ Заявка #{request_id} отправлена на проверку админу!\n"
        f"Ожидайте пополнения.",
        reply_markup=main_keyboard()
    )

@dp.message(DepositStates.confirm)
async def deposit_wrong(message: Message):
    await message.answer("❌ Отправьте скриншот с подтверждением оплаты")

@dp.message(F.text == "🎁 Обменять GET")
async def exchange_start(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[4] == 1:
        return
    
    text = "🎁 Обмен GET на подарки (Stars):\n\n"
    for get_amount, info in GET_TO_STARS.items():
        text += f"{info['name']}: {get_amount} GET = {info['stars']} ⭐\n"
    text += f"\n💰 Ваш баланс: {user[2]} GET"
    
    await message.answer(text, reply_markup=gift_selection_keyboard())

@dp.callback_query(F.data.startswith("gift_"))
async def exchange_gift(callback: CallbackQuery, state: FSMContext):
    get_amount = int(callback.data.split("_")[1])
    user = get_user(callback.from_user.id)
    
    if user[2] < get_amount:
        await callback.answer(f"❌ Недостаточно GET! Нужно: {get_amount}", show_alert=True)
        return
    
    info = GET_TO_STARS[get_amount]
    request_id = generate_request_id()
    
    db_execute("""
        INSERT INTO withdraw_requests (user_id, username, get_amount, stars_amount, gift_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (callback.from_user.id, callback.from_user.username or str(callback.from_user.id),
          get_amount, info['stars'], info['name'], datetime.now().isoformat()))
    
    subtract_balance(callback.from_user.id, get_amount)
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📩 Новая заявка на вывод\n\n"
                f"ID: {request_id}\n"
                f"От: @{callback.from_user.username or callback.from_user.id}\n"
                f"Подарок: {info['name']}\n"
                f"Сумма: {info['stars']} ⭐\n"
                f"Списано GET: {get_amount}\n\n"
                f"Для подтверждения нажмите:\n"
                f"/confirm_withdraw {request_id} {info['stars']} {callback.from_user.id}"
            )
        except:
            pass
    
    await callback.message.edit_text(
        f"✅ Заявка #{request_id} отправлена!\n\n"
        f"🎁 {info['name']}\n"
        f"💰 Списано: {get_amount} GET\n"
        f"⭐ Получите: {info['stars']} Stars\n\n"
        f"Ожидайте обработки админом.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    tasks = db_execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")[0][0]
    completed = db_execute("SELECT COUNT(*) FROM task_completions")[0][0]
    
    await message.answer(
        f"📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {users}\n"
        f"📋 Активных заданий: {tasks}\n"
        f"✅ Выполнено отзывов: {completed}\n"
        f"💰 Ваш баланс: {user[2]} GET"
    )

# ========== АДМИН-ПАНЕЛЬ ==========

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    await message.answer(
        "🛠 Админ-панель\n\n"
        "Выберите действие:",
        reply_markup=admin_keyboard()
    )

@dp.message(F.text == "⬅️ Выйти из админки")
async def exit_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выход из админ-панели", reply_markup=main_keyboard())

@dp.message(F.text == "📢 Рассылка")
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer(
        "📢 Введите текст для рассылки:\n\n"
        "Используйте /skip для отмены",
        reply_markup=back_keyboard()
    )
    await state.set_state(AdminStates.broadcast)

@dp.message(AdminStates.broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    users = db_execute("SELECT user_id FROM users WHERE is_banned = 0")
    success = 0
    
    await message.answer(f"📢 Начинаю рассылку для {len(users)} пользователей...")
    
    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await state.clear()
    await message.answer(f"✅ Рассылка завершена! Отправлено: {success}/{len(users)}")

@dp.message(F.text == "🚫 Баны")
async def ban_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔨 Забанить")],
            [KeyboardButton(text="🔓 Разбанить")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🚫 Управление банами:", reply_markup=keyboard)

@dp.message(F.text == "🔨 Забанить")
async def ban_user_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите ID или @username пользователя для бана:", reply_markup=back_keyboard())
    await state.set_state(AdminStates.ban_user)

@dp.message(AdminStates.ban_user)
async def ban_user_execute(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except:
        username = message.text.strip().replace("@", "")
        user = db_execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        user_id = user[0][0]
    
    db_execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    await state.clear()
    await message.answer(f"✅ Пользователь {user_id} забанен", reply_markup=admin_keyboard())

@dp.message(F.text == "🔓 Разбанить")
async def unban_user_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите ID или @username пользователя для разбана:", reply_markup=back_keyboard())
    await state.set_state(AdminStates.unban_user)

@dp.message(AdminStates.unban_user)
async def unban_user_execute(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except:
        username = message.text.strip().replace("@", "")
        user = db_execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        user_id = user[0][0]
    
    db_execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    await state.clear()
    await message.answer(f"✅ Пользователь {user_id} разбанен", reply_markup=admin_keyboard())

@dp.message(F.text == "🔨 Управление балансом")
async def balance_admin_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Выдать GET")],
            [KeyboardButton(text="➖ Забрать GET")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🔨 Управление балансом:", reply_markup=keyboard)

@dp.message(F.text == "➕ Выдать GET")
async def add_balance_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите ID пользователя и сумму через пробел:\nПример: 123456789 10000", reply_markup=back_keyboard())
    await state.set_state(AdminStates.add_balance)

@dp.message(AdminStates.add_balance)
async def add_balance_execute(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Введите ID и сумму через пробел")
        return
    
    try:
        user_id = int(parts[0])
        amount = int(parts[1])
    except:
        await message.answer("❌ Неверный формат")
        return
    
    add_balance(user_id, amount)
    await state.clear()
    await message.answer(f"✅ Пользователю {user_id} выдано {amount} GET", reply_markup=admin_keyboard())

@dp.message(F.text == "➖ Забрать GET")
async def remove_balance_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите ID пользователя и сумму через пробел:\nПример: 123456789 5000", reply_markup=back_keyboard())
    await state.set_state(AdminStates.remove_balance)

@dp.message(AdminStates.remove_balance)
async def remove_balance_execute(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Введите ID и сумму через пробел")
        return
    
    try:
        user_id = int(parts[0])
        amount = int(parts[1])
    except:
        await message.answer("❌ Неверный формат")
        return
    
    if subtract_balance(user_id, amount):
        await message.answer(f"✅ У пользователя {user_id} списано {amount} GET", reply_markup=admin_keyboard())
    else:
        await message.answer(f"❌ Недостаточно средств у пользователя", reply_markup=admin_keyboard())
    await state.clear()

@dp.message(F.text == "💳 Заявки на пополнение")
async def deposit_requests_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    requests = db_execute("""
        SELECT id, user_id, request_id, stars_amount, get_amount, status, created_at
        FROM deposit_requests WHERE status = 'pending'
    """)
    
    if not requests:
        await message.answer("📭 Нет активных заявок на пополнение")
        return
    
    for req in requests:
        text = (
            f"📩 Заявка #{req[2]}\n"
            f"👤 Пользователь: {req[1]}\n"
            f"⭐ Сумма: {req[3]} Stars\n"
            f"💰 GET: {req[4]}\n"
            f"📅 Создана: {req[6]}\n"
            f"Статус: ⏳ Ожидание"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_dep_{req[0]}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_dep_{req[0]}")]
        ])
        await message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("confirm_dep_"))
async def confirm_deposit(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    req = db_execute("SELECT * FROM deposit_requests WHERE id = ?", (req_id,))
    if not req:
        await callback.answer("❌ Заявка не найдена")
        return
    
    req = req[0]
    add_balance(req[1], req[4])
    db_execute("UPDATE deposit_requests SET status = 'completed' WHERE id = ?", (req_id,))
    
    await bot.send_message(req[1], f"✅ Ваш баланс пополнен на {req[4]} GET!")
    await callback.message.edit_text(f"✅ Заявка #{req[2]} подтверждена")
    await callback.answer("✅ Заявка подтверждена")

@dp.callback_query(F.data.startswith("reject_dep_"))
async def reject_deposit(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    db_execute("UPDATE deposit_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    await callback.message.edit_text("❌ Заявка отклонена")
    await callback.answer("❌ Заявка отклонена")

@dp.message(F.text == "💸 Заявки на вывод")
async def withdraw_requests_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    requests = db_execute("""
        SELECT id, user_id, username, get_amount, stars_amount, gift_name, status, created_at
        FROM withdraw_requests WHERE status = 'pending'
    """)
    
    if not requests:
        await message.answer("📭 Нет активных заявок на вывод")
        return
    
    for req in requests:
        text = (
            f"🎁 Заявка на вывод\n"
            f"👤 Пользователь: @{req[2]}\n"
            f"🎁 Подарок: {req[5]}\n"
            f"⭐ Stars: {req[4]}\n"
            f"💰 GET: {req[3]}\n"
            f"📅 Создана: {req[7]}\n"
            f"Статус: ⏳ Ожидание"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_wd_{req[0]}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_wd_{req[0]}")]
        ])
        await message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("confirm_wd_"))
async def confirm_withdraw(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    req = db_execute("SELECT * FROM withdraw_requests WHERE id = ?", (req_id,))
    if not req:
        await callback.answer("❌ Заявка не найдена")
        return
    
    req = req[0]
    db_execute("UPDATE withdraw_requests SET status = 'completed' WHERE id = ?", (req_id,))
    
    await bot.send_message(
        req[1], 
        f"✅ Ваша заявка на вывод подтверждена!\n"
        f"🎁 {req[5]} отправлен на ваш аккаунт."
    )
    await callback.message.edit_text(f"✅ Заявка #{req_id} подтверждена")
    await callback.answer("✅ Заявка подтверждена")

@dp.callback_query(F.data.startswith("reject_wd_"))
async def reject_withdraw(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    db_execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    
    req = db_execute("SELECT * FROM withdraw_requests WHERE id = ?", (req_id,))
    if req:
        add_balance(req[0][1], req[0][3])
        await bot.send_message(req[0][1], f"❌ Ваша заявка отклонена. GET возвращены на баланс.")
    
    await callback.message.edit_text("❌ Заявка отклонена")
    await callback.answer("❌ Заявка отклонена")

@dp.message(F.text == "🎟 Создать промокод")
async def create_promo_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer(
        "🎟 Создание промокода\n\n"
        "Введите код (например: PROMO2025):",
        reply_markup=back_keyboard()
    )
    await state.set_state(AdminStates.promo_code)

@dp.message(AdminStates.promo_code)
async def create_promo_code(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    code = message.text.strip().upper()
    if not code:
        await message.answer("❌ Код не может быть пустым")
        return
    
    await state.update_data(promo_code=code)
    await message.answer("Введите бонус в GET:")
    await state.set_state(AdminStates.promo_bonus)

@dp.message(AdminStates.promo_bonus)
async def create_promo_bonus(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        bonus = int(message.text.strip())
    except:
        await message.answer("❌ Введите число:")
        return
    
    await state.update_data(promo_bonus=bonus)
    await message.answer("Введите лимит использований (0 - безлимит):")
    await state.set_state(AdminStates.promo_limit)

@dp.message(AdminStates.promo_limit)
async def create_promo_limit(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        limit = int(message.text.strip())
    except:
        await message.answer("❌ Введите число:")
        return
    
    data = await state.get_data()
    db_execute("""
        INSERT INTO promo_codes (code, bonus_get, uses_limit, created_at)
        VALUES (?, ?, ?, ?)
    """, (data['promo_code'], data['promo_bonus'], limit, datetime.now().isoformat()))
    
    await state.clear()
    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"Код: {data['promo_code']}\n"
        f"Бонус: {data['promo_bonus']} GET\n"
        f"Лимит: {limit if limit > 0 else 'Безлимит'}",
        reply_markup=admin_keyboard()
    )

@dp.message(F.text == "➕ Добавить канал в подписку")
async def add_channel(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    global CHANNEL_ID
    await message.answer(
        "📢 Введите ID канала для обязательной подписки:\n"
        "Например: @my_channel\n"
        "Или введите /skip для отмены"
    )
    await state.set_state(AdminStates.channel_add)

@dp.message(AdminStates.channel_add)
async def add_channel_save(message: Message, state: FSMContext):
    if message.text == "/skip" or message.text == "🔙 Назад":
        await admin_panel(message)
        await state.clear()
        return
    
    global CHANNEL_ID
    CHANNEL_ID = message.text.strip()
    await state.clear()
    await message.answer(f"✅ Канал {CHANNEL_ID} добавлен в обязательную подписку", reply_markup=admin_keyboard())

@dp.message(F.text == "👥 Пользователи")
async def users_list(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    banned = db_execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")[0][0]
    total_balance = db_execute("SELECT SUM(balance) FROM users")[0][0]
    
    await message.answer(
        f"👥 Статистика пользователей:\n\n"
        f"Всего: {users}\n"
        f"Забанено: {banned}\n"
        f"Общий баланс GET: {total_balance if total_balance else 0}"
    )

# ========== ОБРАБОТЧИКИ КОМАНД АДМИНА ==========

@dp.message(Command("confirm_deposit"))
async def cmd_confirm_deposit(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    parts = message.text.split()
    if len(parts) != 5:
        await message.answer("❌ Использование: /confirm_deposit ID_заявки Stars GET UserID")
        return
    
    request_id = parts[1]
    stars = int(parts[2])
    get_amount = int(parts[3])
    user_id = int(parts[4])
    
    req = db_execute("SELECT * FROM deposit_requests WHERE request_id = ? AND status = 'pending'", (request_id,))
    if not req:
        await message.answer("❌ Заявка не найдена или уже обработана")
        return
    
    db_execute("UPDATE deposit_requests SET status = 'completed' WHERE request_id = ?", (request_id,))
    add_balance(user_id, get_amount)
    
    await bot.send_message(user_id, f"✅ Ваш баланс пополнен на {get_amount} GET!")
    await message.answer(f"✅ Заявка {request_id} подтверждена")

@dp.message(Command("confirm_withdraw"))
async def cmd_confirm_withdraw(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("❌ Использование: /confirm_withdraw ID_заявки Stars UserID")
        return
    
    request_id = parts[1]
    stars = int(parts[2])
    user_id = int(parts[3])
    
    req = db_execute("SELECT * FROM withdraw_requests WHERE id = ? AND status = 'pending'", (request_id,))
    if not req:
        await message.answer("❌ Заявка не найдена или уже обработана")
        return
    
    db_execute("UPDATE withdraw_requests SET status = 'completed' WHERE id = ?", (request_id,))
    
    gift_name = req[0][5]
    await bot.send_message(
        user_id,
        f"✅ Ваша заявка на вывод подтверждена!\n"
        f"🎁 {gift_name} отправлен на ваш аккаунт."
    )
    await message.answer(f"✅ Заявка {request_id} подтверждена")

# ========== ОБРАБОТЧИК ПРОМОКОДОВ ==========

@dp.message(Command("promo"))
async def use_promo(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[4] == 1:
        await message.answer("🚫 Доступ запрещен")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /promo КОД")
        return
    
    code = args[1].upper()
    
    promo = db_execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
    if not promo:
        await message.answer("❌ Промокод не найден")
        return
    
    promo = promo[0]
    
    # Проверяем, не использовал ли уже
    used = db_execute("SELECT * FROM promo_uses WHERE promo_id = ? AND user_id = ?", (promo[0], message.from_user.id))
    if used:
        await message.answer("❌ Вы уже использовали этот промокод")
        return
    
    # Проверяем лимит
    if promo[3] > 0 and promo[4] >= promo[3]:
        await message.answer("❌ Промокод достиг лимита использований")
        return
    
    # Начисляем бонус
    add_balance(message.from_user.id, promo[2])
    db_execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", (promo[0],))
    db_execute("INSERT INTO promo_uses (promo_id, user_id, created_at) VALUES (?, ?, ?)", 
               (promo[0], message.from_user.id, datetime.now().isoformat()))
    
    await message.answer(f"✅ Промокод активирован! +{promo[2]} GET на баланс!")

# ========== ЗАПУСК ==========

async def main():
    init_db()
    logging.info("🚀 Бот запущен!")
    logging.info(f"📱 Бот: @{BOT_USERNAME}")
    logging.info(f"👑 Админ: {ADMIN_IDS[0]}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
