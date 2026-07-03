import asyncio
import sqlite3
import random
import string
import logging
import re
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== КОНФИГ ==========
BOT_TOKEN = "8910370046:AAFftfaASfcEn4iUhRU6HSAt2ruYLOshMT4"
BOT_USERNAME = "Client_voice_bot"
ADMIN_IDS = [8478884644]
CHANNEL_ID = "@Client_Voice_NEWS"
SUPPORT_USERNAME = "debashev"

STAR_TO_GET = 1000
COST_PER_TASK = 5000

# Список матерных слов (можно расширять)
BAD_WORDS = [
    "хуй", "хуя", "хую", "хуем", "хуе", "хуё", "пизд", "пизда", "пиздец",
    "бля", "блять", "блядь", "еб", "еба", "ебу", "ебал", "ебать", "ебан",
    "гандон", "гнида", "говно", "дерьмо", "мудак", "мудила", "уебок",
    "пидор", "пидр", "сука", "сучка", "шлюха", "курва", "мент", "лох",
    "дебил", "даун", "тупой", "олень", "козел", "осел", "свин", "свинья",
    "залуп", "очко", "жопа", "жоп", "срать", "срал", "насрать", "засра",
    "подонок", "тварь", "петух", "петушара", "петуш"
]

DB_NAME = "bot.db"
logging.basicConfig(level=logging.INFO)
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
            language TEXT DEFAULT 'ru',
            balance INTEGER DEFAULT 5000,
            ref_code TEXT UNIQUE,
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0,
            device_id TEXT,
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
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            bonus_get INTEGER,
            start_date TEXT,
            end_date TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contest_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contest_id INTEGER,
            user_id INTEGER,
            completed_tasks INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stars_amount INTEGER,
            get_amount INTEGER,
            payment_id TEXT,
            status TEXT DEFAULT 'completed',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('channel_id', ?)", (CHANNEL_ID,))
    
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

def get_user_by_device(device_id):
    result = db_execute("SELECT * FROM users WHERE device_id = ?", (device_id,))
    return result[0] if result else None

def create_user(user_id, username, device_id, ref_code=None, language='ru'):
    existing = get_user(user_id)
    if existing:
        return existing
    
    if device_id:
        existing_device = get_user_by_device(device_id)
        if existing_device and existing_device[0] != user_id:
            return None
    
    ref_code_new = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    referred_by = None
    
    # Реферальная система — проверяем, кто пригласил (ref_code = user_id пригласившего)
    if ref_code:
        try:
            referrer_id = int(ref_code)
            referrer = get_user(referrer_id)
            if referrer:
                referred_by = referrer_id
        except:
            # Если ref_code не число, ищем по ref_code
            referrer = db_execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
            if referrer:
                referred_by = referrer[0][0]
    
    db_execute("""
        INSERT INTO users (user_id, username, language, balance, ref_code, referred_by, device_id, is_banned, is_verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, language, 5000, ref_code_new, referred_by, device_id, 0, 0, datetime.now().isoformat()))
    
    if referred_by:
        db_execute("UPDATE users SET balance = balance + 5000 WHERE user_id = ?", (referred_by,))
        db_execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                   (referred_by, user_id, datetime.now().isoformat()))
        asyncio.create_task(bot.send_message(referred_by, 
            f"🎉 Новый реферал @{username}!\n💰 +5000 GET на баланс!"))
    
    return get_user(user_id)

def add_balance(user_id, amount):
    db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

def subtract_balance(user_id, amount):
    user = get_user(user_id)
    if user and user[3] >= amount:
        db_execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        return True
    return False

def generate_request_id():
    return f"REQ-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=6))}"

def get_channel():
    result = db_execute("SELECT value FROM settings WHERE key = 'channel_id'")
    return result[0][0] if result else None

def set_channel(channel):
    db_execute("UPDATE settings SET value = ? WHERE key = 'channel_id'", (channel,))

def check_bad_words(text):
    """Проверка на мат"""
    text_lower = text.lower()
    for word in BAD_WORDS:
        if word in text_lower:
            return True
    return False

def check_theme_match(text, theme):
    """Проверка соответствия тематике"""
    text_lower = text.lower()
    theme_words = theme.lower().split()
    # Проверяем, что хотя бы 2 слова из темы есть в тексте
    match_count = 0
    for word in theme_words:
        if len(word) > 3 and word in text_lower:
            match_count += 1
    return match_count >= 2

# ========== ЯЗЫКИ ==========
LANGUAGES = {
    'ru': {
        'start': "👋 Привет, {username}!\n\n📝 Выберите раздел:\n💰 Баланс: {balance} GET",
        'banned': "🚫 Вы забанены!",
        'subscribe': "📢 Подпишись на канал: {channel}",
        'check_sub': "✅ Подписка подтверждена!",
        'not_sub': "❌ Вы не подписались!",
        'balance': "💰 Баланс: {balance} GET\n1⭐ = 1000 GET",
        'referrals': "👥 Рефералы: {count}\n🔗 Код: {code}\nСсылка: https://t.me/{bot}?start={code}",
        'stats': "📊 Статистика\n👥 {users}\n📋 {tasks}\n✅ {completed}\n💰 {balance} GET",
        'no_tasks': "📭 Нет активных заданий",
        'task_created': "✅ Задание #{task_id} создано!",
        'task_completed': "✅ Отзыв для #{task_id} принят!\n💰 +5000 GET\nБаланс: {balance} GET",
        'not_enough': "❌ Недостаточно средств! Нужно {cost} GET, у вас {balance} GET",
        'review_forward': "📩 Новый отзыв от: @{username}",
        'short_review': "❌ Минимум 15 символов",
        'bad_words': "❌ Обнаружены нецензурные слова! Перепишите отзыв:",
        'theme_mismatch': "❌ Отзыв не соответствует теме задания! Напишите про {theme}:",
        'no_username': "❌ Вы не указали @username в отзыве! Добавьте @username заказчика:",
        'deposit_confirm': "✅ Оплата {stars} ⭐ получена!\n💰 +{get} GET на баланс!",
        'deposit_manual': "💎 Пополнение от 15 ⭐:\nПереведите {stars} ⭐ админу @{support} с комментарием `{request_id}`\nОтправьте скриншот",
        'exchange': "🎁 Обмен GET:\n{text}\n💰 Баланс: {balance} GET",
        'exchange_done': "✅ Заявка {request_id} отправлена",
        'leaderboard': "🏆 Топ рефералов за неделю:\n{text}",
        'contests': "🎯 Активные конкурсы:\n{text}",
        'deposit_title': "Пополнение GET",
        'deposit_desc': "Покупка GET-коинов",
        'deposit_choose': "💎 Выберите сумму для пополнения:\n\n1⭐ = 1000 GET",
        'deposit_manual_btn': "15+ ⭐ (админ)",
        'back': "🔙 Назад",
        'task_create_step1': "📝 ШАГ 1: Укажите @username заказчика\n\nЭто тот человек, которому вы хотите собрать отзывы.\n\nПример: @debashev",
        'task_create_step2': "📝 ШАГ 2: Укажите тематику отзыва\n\nОпишите, о чём должен быть отзыв.\n\n📌 Важно: отзыв будет проверяться на соответствие теме!\n\nПример: криптокошелек, игра, магазин, услуги",
        'task_create_step3': "📝 ШАГ 3: Укажите количество отзывов\n\nСколько человек должно написать отзыв.\n\n💰 Стоимость: 5000 GET за 1 отзыв\n\n⚠️ С вашего баланса спишется {cost} GET за каждое задание",
        'task_create_step4': "📝 ШАГ 4: Выберите тип отзыва\n\n👍 Положительный — хвалят\n👎 Негативный — критикуют",
        'task_create_step5': "📝 ШАГ 5: Напишите пример отзыва\n\nЭто шаблон для исполнителей.\n\n💡 Совет: напишите красивый развёрнутый отзыв\n\nИсполнители будут использовать ваш пример как образец.",
        'task_create_confirm': "📋 ПРОВЕРЬТЕ ДАННЫЕ:\n\n👤 Заказчик: {username}\n📂 Тема: {theme}\n🔢 Количество: {count} шт.\n📊 Тип: {type}\n📝 Пример: {example}\n\n💰 Стоимость: {cost} GET\n💰 Ваш баланс: {balance} GET",
        'task_not_enough_balance': "❌ НЕДОСТАТОЧНО СРЕДСТВ!\n\nСоздание {count} заданий стоит {total_cost} GET\nВаш баланс: {balance} GET\n\nПополните баланс в разделе 💎 Пополнить GET",
        'review_step1': "✍️ НАПИШИТЕ ОТЗЫВ\n\n📌 ТРЕБОВАНИЯ:\n1. Отзыв должен быть по теме: {theme}\n2. Обязательно укажите @{username} в тексте\n3. Минимум 15 символов\n4. Без мата\n\n📝 Пример:\n{example}\n\nНапишите свой отзыв:",
        'review_bad_username': "❌ В отзыве не найден @{username}!\n\nДобавьте @{username} в текст отзыва.",
    },
    'en': {
        'start': "👋 Hello, {username}!\n\n📝 Select a section:\n💰 Balance: {balance} GET",
        'banned': "🚫 You are banned!",
        'subscribe': "📢 Subscribe to channel: {channel}",
        'check_sub': "✅ Subscription confirmed!",
        'not_sub': "❌ You are not subscribed!",
        'balance': "💰 Balance: {balance} GET\n1⭐ = 1000 GET",
        'referrals': "👥 Referrals: {count}\n🔗 Code: {code}\nLink: https://t.me/{bot}?start={code}",
        'stats': "📊 Statistics\n👥 {users}\n📋 {tasks}\n✅ {completed}\n💰 {balance} GET",
        'no_tasks': "📭 No active tasks",
        'task_created': "✅ Task #{task_id} created!",
        'task_completed': "✅ Review for #{task_id} accepted!\n💰 +5000 GET\nBalance: {balance} GET",
        'not_enough': "❌ Insufficient funds! Need {cost} GET, you have {balance} GET",
        'review_forward': "📩 New review from: @{username}",
        'short_review': "❌ Minimum 15 characters",
        'bad_words': "❌ Bad words detected! Rewrite the review:",
        'theme_mismatch': "❌ Review does not match the theme! Write about {theme}:",
        'no_username': "❌ You didn't specify @username in the review! Add @username of the customer:",
        'deposit_confirm': "✅ Payment of {stars} ⭐ received!\n💰 +{get} GET to balance!",
        'deposit_manual': "💎 Deposit from 15 ⭐:\nSend {stars} ⭐ to admin @{support} with comment `{request_id}`\nSend screenshot",
        'exchange': "🎁 Exchange GET:\n{text}\n💰 Balance: {balance} GET",
        'exchange_done': "✅ Request {request_id} sent",
        'leaderboard': "🏆 Top referrers for the week:\n{text}",
        'contests': "🎯 Active contests:\n{text}",
        'deposit_title': "Deposit GET",
        'deposit_desc': "Buy GET coins",
        'deposit_choose': "💎 Select deposit amount:\n\n1⭐ = 1000 GET",
        'deposit_manual_btn': "15+ ⭐ (admin)",
        'back': "🔙 Back",
        'task_create_step1': "📝 STEP 1: Enter @username of the customer\n\nThis is the person you want to collect reviews for.\n\nExample: @debashev",
        'task_create_step2': "📝 STEP 2: Enter the theme of the review\n\nDescribe what the review should be about.\n\n📌 Important: the review will be checked for theme match!\n\nExample: crypto wallet, game, store, services",
        'task_create_step3': "📝 STEP 3: Enter the number of reviews\n\nHow many people should write a review.\n\n💰 Cost: 5000 GET per 1 review\n\n⚠️ {cost} GET will be deducted from your balance for each task",
        'task_create_step4': "📝 STEP 4: Select review type\n\n👍 Positive — praise\n👎 Negative — criticize",
        'task_create_step5': "📝 STEP 5: Write an example review\n\nThis is a template for performers.\n\n💡 Tip: write a beautiful detailed review",
        'task_create_confirm': "📋 CHECK THE DATA:\n\n👤 Customer: {username}\n📂 Theme: {theme}\n🔢 Quantity: {count} pcs.\n📊 Type: {type}\n📝 Example: {example}\n\n💰 Cost: {cost} GET\n💰 Your balance: {balance} GET",
        'task_not_enough_balance': "❌ INSUFFICIENT FUNDS!\n\nCreating {count} tasks costs {total_cost} GET\nYour balance: {balance} GET\n\nTop up your balance in 💎 Deposit GET",
        'review_step1': "✍️ WRITE A REVIEW\n\n📌 REQUIREMENTS:\n1. Review must be on topic: {theme}\n2. Be sure to include @{username} in the text\n3. Minimum 15 characters\n4. No swearing\n\n📝 Example:\n{example}\n\nWrite your review:",
        'review_bad_username': "❌ @{username} not found in the review!\n\nAdd @{username} to the review text.",
    }
}

def get_text(lang, key, **kwargs):
    text = LANGUAGES.get(lang, LANGUAGES['ru']).get(key, key)
    return text.format(**kwargs) if kwargs else text

# ========== КЛАВИАТУРЫ ==========
def main_keyboard(lang='ru'):
    if lang == 'ru':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📝 Создать задание")],
            [KeyboardButton(text="📋 Задания для выполнения")],
            [KeyboardButton(text="💰 Мой баланс"), KeyboardButton(text="👥 Рефералы")],
            [KeyboardButton(text="💎 Пополнить GET"), KeyboardButton(text="🎁 Обменять GET")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🏆 Топ рефералов")],
            [KeyboardButton(text="🎯 Конкурсы")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📝 Create task")],
            [KeyboardButton(text="📋 Tasks to do")],
            [KeyboardButton(text="💰 My balance"), KeyboardButton(text="👥 Referrals")],
            [KeyboardButton(text="💎 Deposit GET"), KeyboardButton(text="🎁 Exchange GET")],
            [KeyboardButton(text="📊 Statistics"), KeyboardButton(text="🏆 Top referrers")],
            [KeyboardButton(text="🎯 Contests")]
        ], resize_keyboard=True)

def admin_keyboard(lang='ru'):
    if lang == 'ru':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="💳 Заявки на пополнение")],
            [KeyboardButton(text="💸 Заявки на вывод")],
            [KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="🔨 Управление балансом")],
            [KeyboardButton(text="🚫 Баны")],
            [KeyboardButton(text="🎟 Создать промокод")],
            [KeyboardButton(text="🏆 Топ рефералов")],
            [KeyboardButton(text="🎯 Конкурсы")],
            [KeyboardButton(text="📢 Управление каналом")],
            [KeyboardButton(text="🗑 Сбросить БД")],
            [KeyboardButton(text="⬅️ Выйти из админки")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="👥 Users")],
            [KeyboardButton(text="💳 Deposit requests")],
            [KeyboardButton(text="💸 Withdraw requests")],
            [KeyboardButton(text="📢 Broadcast")],
            [KeyboardButton(text="🔨 Balance management")],
            [KeyboardButton(text="🚫 Bans")],
            [KeyboardButton(text="🎟 Create promo")],
            [KeyboardButton(text="🏆 Top referrers")],
            [KeyboardButton(text="🎯 Contests")],
            [KeyboardButton(text="📢 Channel management")],
            [KeyboardButton(text="🗑 Reset DB")],
            [KeyboardButton(text="⬅️ Exit admin")]
        ], resize_keyboard=True)

def back_keyboard(lang='ru'):
    text = get_text(lang, 'back')
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=text)]], resize_keyboard=True)

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")]
    ])

def task_actions_keyboard(task_id, lang='ru'):
    write_text = "✍️ Написать отзыв" if lang == 'ru' else "✍️ Write review"
    back_text = get_text(lang, 'back')
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=write_text, callback_data=f"do_task_{task_id}")],
        [InlineKeyboardButton(text=back_text, callback_data="back_to_tasks")]
    ])

def gift_selection_keyboard(lang='ru'):
    buttons = []
    for get_amount, info in GET_TO_STARS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{info['name']} ({get_amount} GET)",
            callback_data=f"gift_{get_amount}"
        )])
    back_text = get_text(lang, 'back')
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def deposit_keyboard(lang='ru'):
    buttons = []
    for stars in [1, 2, 5, 10]:
        get_amount = stars * 1000
        buttons.append([InlineKeyboardButton(
            text=f"{stars} ⭐ = {get_amount} GET",
            callback_data=f"deposit_{stars}"
        )])
    manual_text = get_text(lang, 'deposit_manual_btn')
    buttons.append([InlineKeyboardButton(text=manual_text, callback_data="deposit_manual")])
    back_text = get_text(lang, 'back')
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_main")])
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
    channel_delete = State()
    contest_name = State()
    contest_desc = State()
    contest_bonus = State()
    contest_start = State()
    contest_end = State()
    leaderboard_bonus = State()
    reset_db_confirm = State()

class ReviewStates(StatesGroup):
    writing = State()

class LanguageStates(StatesGroup):
    selecting = State()

# ========== ПРОВЕРКИ ==========
async def check_subscription(user_id):
    if user_id in ADMIN_IDS:
        return True
    
    channel = get_channel()
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ========== ХЕНДЛЕРЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    user = get_user(user_id)
    if not user:
        await message.answer(
            "🌍 Выберите язык / Select language:",
            reply_markup=language_keyboard()
        )
        await state.set_state(LanguageStates.selecting)
        return
    
    if user[6] == 1:
        await message.answer(get_text(user[2], 'banned'))
        return
    
    if not await check_subscription(user_id):
        channel = get_channel()
        if channel:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{channel[1:]}")],
                [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]
            ])
            await message.answer(
                get_text(user[2], 'subscribe', channel=channel),
                reply_markup=keyboard
            )
            return
    
    await message.answer(
        get_text(user[2], 'start', username=message.from_user.username or str(user_id), balance=user[3]),
        reply_markup=main_keyboard(user[2])
    )

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    username = callback.from_user.username or str(user_id)
    
    args = callback.message.text.split()
    ref_code = args[1] if len(args) > 1 else None
    
    device_id = str(callback.from_user.id)
    user = create_user(user_id, username, device_id, ref_code, lang)
    if not user:
        await callback.answer("❌ Твинк обнаружен! / Twin detected!", show_alert=True)
        return
    
    await state.clear()
    
    if not await check_subscription(user_id):
        channel = get_channel()
        if channel:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{channel[1:]}")],
                [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]
            ])
            await callback.message.edit_text(
                get_text(lang, 'subscribe', channel=channel),
                reply_markup=keyboard
            )
            return
    
    await callback.message.edit_text(
        get_text(lang, 'start', username=username, balance=user[3]),
        reply_markup=main_keyboard(lang)
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    if not user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if await check_subscription(user_id):
        await callback.message.edit_text(
            get_text(user[2], 'check_sub')
        )
        await cmd_start(callback.message, FSMContext())
    else:
        await callback.answer(get_text(user[2], 'not_sub'), show_alert=True)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

@dp.message(F.text.in_(["🔙 Назад", "🔙 Back"]))
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Ошибка")
        return
    
    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            "🔙 Админ-панель" if user[2] == 'ru' else "🔙 Admin panel",
            reply_markup=admin_keyboard(user[2])
        )
    else:
        await message.answer(
            "🔙 Главное меню" if user[2] == 'ru' else "🔙 Main menu",
            reply_markup=main_keyboard(user[2])
        )

# ========== ПОПОЛНЕНИЕ ЧЕРЕЗ STARS ==========
@dp.message(F.text.in_(["💎 Пополнить GET", "💎 Deposit GET"]))
async def deposit_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    await message.answer(
        get_text(lang, 'deposit_choose'),
        reply_markup=deposit_keyboard(lang)
    )

@dp.callback_query(F.data.startswith("deposit_"))
async def process_deposit(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user or user[6] == 1:
        await callback.answer("❌ Ошибка")
        return
    
    lang = user[2]
    data = callback.data.split("_")
    
    if data[1] == "manual":
        await callback.message.delete()
        request_id = generate_request_id()
        db_execute("""
            INSERT INTO deposit_requests (user_id, request_id, stars_amount, get_amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (callback.from_user.id, request_id, 15, 15000, 'pending', datetime.now().isoformat()))
        
        await callback.message.answer(
            get_text(lang, 'deposit_manual', stars="15+", support=SUPPORT_USERNAME, request_id=request_id),
            reply_markup=back_keyboard(lang)
        )
        await callback.answer()
        return
    
    stars = int(data[1])
    get_amount = stars * STAR_TO_GET
    
    prices = [LabeledPrice(label="GET Coins", amount=stars * 100)]
    
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=get_text(lang, 'deposit_title'),
        description=f"{get_text(lang, 'deposit_desc')}: {stars}⭐ = {get_amount} GET",
        payload=f"deposit_{stars}_{callback.from_user.id}_{datetime.now().timestamp()}",
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="deposit",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, 'back'), callback_data="back_to_main")]
        ])
    )
    
    await callback.answer("💳 Счёт создан!")

@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout: PreCheckoutQuery):
    await pre_checkout.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    
    stars_amount = payment.total_amount // 100
    get_amount = stars_amount * STAR_TO_GET
    
    add_balance(user_id, get_amount)
    
    db_execute("""
        INSERT INTO payments (user_id, stars_amount, get_amount, payment_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, stars_amount, get_amount, payment.telegram_payment_charge_id, 'completed', datetime.now().isoformat()))
    
    user = get_user(user_id)
    lang = user[2] if user else 'ru'
    
    await message.answer(
        get_text(lang, 'deposit_confirm', stars=stars_amount, get=get_amount),
        reply_markup=main_keyboard(lang)
    )

# ========== ОБМЕН GET ==========
@dp.message(F.text.in_(["🎁 Обменять GET", "🎁 Exchange GET"]))
async def exchange_start(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    text = ""
    for get_amount, info in GET_TO_STARS.items():
        text += f"{info['name']}: {get_amount} GET = {info['stars']} ⭐\n"
    
    await message.answer(
        get_text(lang, 'exchange', text=text, balance=user[3]),
        reply_markup=gift_selection_keyboard(lang)
    )

@dp.callback_query(F.data.startswith("gift_"))
async def exchange_gift(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка")
        return
    
    lang = user[2]
    get_amount = int(callback.data.split("_")[1])
    
    if user[3] < get_amount:
        await callback.answer(f"❌ Нужно {get_amount} GET" if lang == 'ru' else f"❌ Need {get_amount} GET", show_alert=True)
        return
    
    info = GET_TO_STARS[get_amount]
    request_id = generate_request_id()
    
    db_execute("""
        INSERT INTO withdraw_requests (user_id, username, get_amount, stars_amount, gift_name, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (callback.from_user.id, callback.from_user.username or str(callback.from_user.id),
          get_amount, info['stars'], info['name'], 'pending', datetime.now().isoformat()))
    
    subtract_balance(callback.from_user.id, get_amount)
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, 
                f"📩 Заявка на вывод {request_id}\nОт @{callback.from_user.username}\n{info['name']} ({info['stars']}⭐)\nСписано {get_amount} GET")
        except:
            pass
    
    await callback.message.edit_text(
        get_text(lang, 'exchange_done', request_id=request_id),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, 'back'), callback_data="back_to_main")]
        ])
    )

# ========== СОЗДАНИЕ ЗАДАНИЯ (С ПОДРОБНЫМ ОПИСАНИЕМ) ==========
@dp.message(F.text.in_(["📝 Создать задание", "📝 Create task"]))
async def create_task_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    
    await message.answer(
        get_text(lang, 'task_create_step1'),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.username)

@dp.message(CreateTaskStates.username)
async def create_task_username(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    username = message.text.strip()
    if not username.startswith("@"):
        await message.answer("❌ Начинайте с @!" if lang == 'ru' else "❌ Start with @!")
        return
    
    await state.update_data(username=username)
    await message.answer(
        get_text(lang, 'task_create_step2'),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.theme)

@dp.message(CreateTaskStates.theme)
async def create_task_theme(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    theme = message.text.strip()
    forbidden = ["18+", "скам", "scam", "мошенник", "обман", "порно", "секс", "наркотики"]
    if any(w in theme.lower() for w in forbidden):
        await message.answer("❌ Запрещённая тема!" if lang == 'ru' else "❌ Forbidden theme!")
        return
    
    if len(theme) < 5:
        await message.answer("❌ Тема слишком короткая! Минимум 5 символов." if lang == 'ru' else "❌ Theme is too short! Minimum 5 characters.")
        return
    
    await state.update_data(theme=theme)
    await message.answer(
        get_text(lang, 'task_create_step3', cost=COST_PER_TASK),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.count)

@dp.message(CreateTaskStates.count)
async def create_task_count(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    try:
        count = int(message.text.strip())
        if count <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное число!" if lang == 'ru' else "❌ Enter a positive number!")
        return
    
    # Проверка баланса
    total_cost = count * COST_PER_TASK
    if user[3] < total_cost:
        await message.answer(
            get_text(lang, 'task_not_enough_balance', 
                     count=count, 
                     total_cost=total_cost, 
                     balance=user[3])
        )
        return
    
    await state.update_data(count=count)
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👍 Положительный" if lang == 'ru' else "👍 Positive")],
        [KeyboardButton(text="👎 Негативный" if lang == 'ru' else "👎 Negative")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        get_text(lang, 'task_create_step4'),
        reply_markup=keyboard
    )
    await state.set_state(CreateTaskStates.review_type)

@dp.message(CreateTaskStates.review_type)
async def create_task_type(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    if message.text not in ["👍 Положительный", "👎 Негативный", "👍 Positive", "👎 Negative"]:
        await message.answer("❌ Выберите из кнопок!" if lang == 'ru' else "❌ Choose from buttons!")
        return
    
    review_type = "positive" if "Положительный" in message.text or "Positive" in message.text else "negative"
    await state.update_data(review_type=review_type)
    
    await message.answer(
        get_text(lang, 'task_create_step5'),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.example)

@dp.message(CreateTaskStates.example)
async def create_task_example(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    example = message.text.strip()
    if len(example) < 20:
        await message.answer("❌ Пример слишком короткий! Минимум 20 символов." if lang == 'ru' else "❌ Example is too short! Minimum 20 characters.")
        return
    
    await state.update_data(example=example)
    data = await state.get_data()
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Подтвердить" if lang == 'ru' else "✅ Confirm")],
        [KeyboardButton(text="❌ Отменить" if lang == 'ru' else "❌ Cancel")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    type_text = "Положительный" if data['review_type'] == 'positive' else "Негативный"
    if lang == 'en':
        type_text = "Positive" if data['review_type'] == 'positive' else "Negative"
    
    total_cost = data['count'] * COST_PER_TASK
    
    await message.answer(
        get_text(lang, 'task_create_confirm',
                 username=data['username'],
                 theme=data['theme'],
                 count=data['count'],
                 type=type_text,
                 example=data['example'][:100] + "...",
                 cost=total_cost,
                 balance=user[3]),
        reply_markup=keyboard
    )
    await state.set_state(CreateTaskStates.confirm)

@dp.message(CreateTaskStates.confirm)
async def create_task_confirm(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    if message.text in ["❌ Отменить", "❌ Cancel"]:
        await state.clear()
        await message.answer("❌ Отменено" if lang == 'ru' else "❌ Cancelled", reply_markup=main_keyboard(lang))
        return
    
    if message.text not in ["✅ Подтвердить", "✅ Confirm"]:
        return
    
    data = await state.get_data()
    user_id = message.from_user.id
    
    total_cost = data['count'] * COST_PER_TASK
    
    # Списываем деньги
    if not subtract_balance(user_id, total_cost):
        await message.answer("❌ Ошибка! Недостаточно средств." if lang == 'ru' else "❌ Error! Insufficient funds.")
        await state.clear()
        return
    
    # Создаём задания
    created = 0
    for i in range(data['count']):
        db_execute("""
            INSERT INTO tasks (creator_id, username, theme, count, review_type, example_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, data['username'], data['theme'], 1, 
              data['review_type'], data['example'], datetime.now().isoformat()))
        created += 1
    
    await state.clear()
    user = get_user(user_id)
    await message.answer(
        f"✅ Создано {created} заданий!\n\n"
        f"💰 Списанo: {total_cost} GET\n"
        f"💰 Текущий баланс: {user[3]} GET",
        reply_markup=main_keyboard(lang)
    )

# ========== ВЫПОЛНЕНИЕ ЗАДАНИЙ ==========
@dp.message(F.text.in_(["📋 Задания для выполнения", "📋 Tasks to do"]))
async def show_tasks(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    tasks = db_execute("SELECT id, username, theme, count FROM tasks WHERE status = 'active'")
    
    if not tasks:
        await message.answer(get_text(lang, 'no_tasks'), reply_markup=main_keyboard(lang))
        return
    
    text = "📋 Доступные задания:\n\n" if lang == 'ru' else "📋 Available tasks:\n\n"
    for t in tasks:
        text += f"🆔 #{t[0]}\n👤 {t[1]}\n📂 {t[2]}\n📌 Осталось: {t[3]}\n💰 5000 GET\n{'='*20}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Задание #{t[0]}" if lang == 'ru' else f"Task #{t[0]}", callback_data=f"task_{t[0]}")]
        for t in tasks[:10]
    ] + [[InlineKeyboardButton(text=get_text(lang, 'back'), callback_data="back_to_main")]])
    
    await message.answer(text[:4000], reply_markup=keyboard)

@dp.callback_query(F.data.startswith("task_"))
async def view_task(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка")
        return
    
    lang = user[2]
    task_id = int(callback.data.split("_")[1])
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    
    if not task:
        await callback.answer("❌ Нет задания" if lang == 'ru' else "❌ No task")
        return
    
    task = task[0]
    type_text = "Положительный" if task[5] == 'positive' else "Негативный"
    if lang == 'en':
        type_text = "Positive" if task[5] == 'positive' else "Negative"
    
    text = f"📋 Задание #{task[0]}\n👤 {task[2]}\n📂 {task[3]}\n📊 {type_text}\n📝 {task[6]}\n💰 5000 GET"
    await callback.message.edit_text(text, reply_markup=task_actions_keyboard(task_id, lang))

@dp.callback_query(F.data.startswith("do_task_"))
async def do_task(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user or user[6] == 1:
        await callback.answer("🚫 Доступ запрещён" if user and user[2] == 'ru' else "🚫 Access denied")
        return
    
    lang = user[2]
    task_id = int(callback.data.split("_")[2])
    
    # Проверка на повторное выполнение
    existing = db_execute("SELECT * FROM task_completions WHERE task_id = ? AND user_id = ?", (task_id, callback.from_user.id))
    if existing:
        await callback.answer("❌ Вы уже выполнили это задание!" if lang == 'ru' else "❌ Already completed!", show_alert=True)
        return
    
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        await callback.answer("❌ Нет задания" if lang == 'ru' else "❌ No task")
        return
    
    task = task[0]
    if task[1] == callback.from_user.id:
        await callback.answer("❌ Своё нельзя!" if lang == 'ru' else "❌ Can't do your own!", show_alert=True)
        return
    
    await state.update_data(task_id=task_id, task_data=task)
    
    await callback.message.edit_text(
        get_text(lang, 'review_step1',
                 theme=task[3],
                 username=task[2].replace("@", ""),
                 example=task[6]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена" if lang == 'ru' else "🔙 Cancel", callback_data="back_to_tasks")]
        ])
    )
    await state.set_state(ReviewStates.writing)

@dp.message(ReviewStates.writing)
async def submit_review(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    data = await state.get_data()
    task_id = data['task_id']
    task = data['task_data']
    review_text = message.text.strip()
    
    # Проверка длины
    if len(review_text) < 15:
        await message.answer(get_text(lang, 'short_review'))
        return
    
    # Проверка на мат
    if check_bad_words(review_text):
        await message.answer(get_text(lang, 'bad_words'))
        return
    
    # Проверка на наличие @username заказчика
    username = task[2]  # @username заказчика
    if username.lower() not in review_text.lower():
        await message.answer(get_text(lang, 'no_username', username=username.replace("@", "")))
        return
    
    # Проверка соответствия тематике
    if not check_theme_match(review_text, task[3]):
        await message.answer(get_text(lang, 'theme_mismatch', theme=task[3]))
        return
    
    # Сохраняем в БД
    db_execute("INSERT INTO task_completions (task_id, user_id, review_text, created_at) VALUES (?, ?, ?, ?)",
               (task_id, message.from_user.id, review_text, datetime.now().isoformat()))
    db_execute("UPDATE tasks SET count = count - 1 WHERE id = ?", (task_id,))
    
    task_check = db_execute("SELECT count FROM tasks WHERE id = ?", (task_id,))
    if task_check and task_check[0][0] == 0:
        db_execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
    
    add_balance(message.from_user.id, 5000)
    
    # Участие в конкурсах
    contests = db_execute("SELECT id FROM contests WHERE is_active = 1 AND datetime(start_date) <= datetime('now') AND datetime(end_date) >= datetime('now')")
    for contest in contests:
        participant = db_execute("SELECT * FROM contest_participants WHERE contest_id = ? AND user_id = ?", (contest[0], message.from_user.id))
        if not participant:
            db_execute("INSERT INTO contest_participants (contest_id, user_id, completed_tasks, created_at) VALUES (?, ?, 1, ?)",
                       (contest[0], message.from_user.id, datetime.now().isoformat()))
        else:
            db_execute("UPDATE contest_participants SET completed_tasks = completed_tasks + 1 WHERE contest_id = ? AND user_id = ?", 
                       (contest[0], message.from_user.id))
    
    # Отправка создателю (forward)
    creator_id = task[1]
    username_sender = message.from_user.username or 'unknown'
    try:
        await bot.send_message(creator_id, get_text(lang, 'review_forward', username=username_sender))
        await bot.forward_message(
            chat_id=creator_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except Exception as e:
        logging.error(f"Forward error: {e}")
    
    await state.clear()
    await message.answer(
        get_text(lang, 'task_completed', task_id=task_id, balance=get_user(message.from_user.id)[3]),
        reply_markup=main_keyboard(lang)
    )

@dp.callback_query(F.data == "back_to_tasks")
async def back_to_tasks_callback(callback: CallbackQuery):
    await callback.message.delete()
    await show_tasks(callback.message)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.delete()
    user = get_user(callback.from_user.id)
    if user:
        await callback.message.answer(
            "Главное меню" if user[2] == 'ru' else "Main menu",
            reply_markup=main_keyboard(user[2])
        )

# ========== БАЛАНС ==========
@dp.message(F.text.in_(["💰 Мой баланс", "💰 My balance"]))
async def show_balance(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    await message.answer(get_text(user[2], 'balance', balance=user[3]))

# ========== РЕФЕРАЛЫ ==========
@dp.message(F.text.in_(["👥 Рефералы", "👥 Referrals"]))
async def show_referrals(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    refs = db_execute("SELECT referred_id FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
    await message.answer(
        get_text(lang, 'referrals', count=len(refs), code=message.from_user.id, bot=BOT_USERNAME)
    )

# ========== ТОП РЕФЕРАЛОВ ==========
@dp.message(F.text.in_(["🏆 Топ рефералов", "🏆 Top referrers"]))
async def show_leaderboard(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    leaderboard = db_execute("""
        SELECT u.user_id, u.username, COUNT(r.id) as ref_count
        FROM users u
        JOIN referrals r ON u.user_id = r.referrer_id
        WHERE r.created_at >= ?
        GROUP BY u.user_id
        ORDER BY ref_count DESC
        LIMIT 10
    """, (week_ago,))
    
    if not leaderboard:
        text = "📭 Нет данных за неделю" if lang == 'ru' else "📭 No data for this week"
    else:
        text = "🏆 Топ рефералов за неделю:\n\n" if lang == 'ru' else "🏆 Top referrers this week:\n\n"
        for i, entry in enumerate(leaderboard, 1):
            username = entry[1] or f"User {entry[0]}"
            text += f"{i}. @{username} — {entry[2]} чел.\n"
    
    await message.answer(text)

# ========== КОНКУРСЫ ==========
@dp.message(F.text.in_(["🎯 Конкурсы", "🎯 Contests"]))
async def show_contests(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    contests = db_execute("""
        SELECT id, name, description, bonus_get, start_date, end_date 
        FROM contests 
        WHERE is_active = 1 AND datetime(start_date) <= datetime('now') AND datetime(end_date) >= datetime('now')
    """)
    
    if not contests:
        text = "🎯 Активных конкурсов нет" if lang == 'ru' else "🎯 No active contests"
    else:
        text = "🎯 Активные конкурсы:\n\n" if lang == 'ru' else "🎯 Active contests:\n\n"
        for contest in contests:
            text += f"📌 {contest[1]}\n📝 {contest[2]}\n💰 Бонус: {contest[3]} GET\n📅 До {contest[5]}\n{'='*20}\n\n"
    
    await message.answer(text)

# ========== СТАТИСТИКА ==========
@dp.message(F.text.in_(["📊 Статистика", "📊 Statistics"]))
async def show_stats(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    tasks = db_execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")[0][0]
    completed = db_execute("SELECT COUNT(*) FROM task_completions")[0][0]
    
    await message.answer(
        get_text(lang, 'stats', users=users, tasks=tasks, completed=completed, balance=user[3])
    )

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "🛠 Админ-панель" if lang == 'ru' else "🛠 Admin panel",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["⬅️ Выйти из админки", "⬅️ Exit admin"]))
async def exit_admin(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Главное меню" if lang == 'ru' else "Main menu",
        reply_markup=main_keyboard(lang)
    )

# ========== СБРОС БАЗЫ ДАННЫХ ==========
@dp.message(F.text.in_(["🗑 Сбросить БД", "🗑 Reset DB"]))
async def reset_db_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚠️ ДА, СБРОСИТЬ ВСЁ" if lang == 'ru' else "⚠️ YES, RESET ALL")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "⚠️ ВНИМАНИЕ! Это действие НЕОБРАТИМО!\n\n"
        "Будут удалены ВСЕ данные:\n"
        "- 👥 Все пользователи\n"
        "- 📋 Все задания\n"
        "- 💰 Все транзакции\n"
        "- 👥 Все рефералы\n"
        "- 🎯 Все конкурсы\n\n"
        "Вы уверены?" if lang == 'ru' else
        "⚠️ WARNING! This action is IRREVERSIBLE!\n\n"
        "ALL data will be deleted:\n"
        "- 👥 All users\n"
        "- 📋 All tasks\n"
        "- 💰 All transactions\n"
        "- 👥 All referrals\n"
        "- 🎯 All contests\n\n"
        "Are you sure?",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.reset_db_confirm)

@dp.message(AdminStates.reset_db_confirm)
async def reset_db_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    if message.text not in ["⚠️ ДА, СБРОСИТЬ ВСЁ", "⚠️ YES, RESET ALL"]:
        await message.answer(
            "❌ Отмена" if lang == 'ru' else "❌ Cancelled",
            reply_markup=admin_keyboard(lang)
        )
        await state.clear()
        return
    
    try:
        # Удаляем файл базы данных
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
            await message.answer(
                "✅ База данных полностью сброшена!\n\n"
                "Бот перезапускается с чистой БД..." if lang == 'ru' else
                "✅ Database completely reset!\n\n"
                "Bot restarting with clean DB...",
                reply_markup=admin_keyboard(lang)
            )
            # Пересоздаём БД
            init_db()
            await message.answer(
                "✅ База данных создана заново!" if lang == 'ru' else "✅ Database recreated!",
                reply_markup=admin_keyboard(lang)
            )
        else:
            await message.answer(
                "❌ Файл базы данных не найден. Создаю новый..." if lang == 'ru' else "❌ Database file not found. Creating new...",
                reply_markup=admin_keyboard(lang)
            )
            init_db()
            await message.answer(
                "✅ База данных создана!" if lang == 'ru' else "✅ Database created!",
                reply_markup=admin_keyboard(lang)
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при сбросе БД: {e}" if lang == 'ru' else f"❌ Error resetting DB: {e}",
            reply_markup=admin_keyboard(lang)
        )
    
    await state.clear()

# ========== УПРАВЛЕНИЕ КАНАЛОМ ==========
@dp.message(F.text.in_(["📢 Управление каналом", "📢 Channel management"]))
async def channel_management(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    current_channel = get_channel() or "Не установлен" if lang == 'ru' else "Not set"
    channel_text = f"📢 Текущий канал: {current_channel}" if lang == 'ru' else f"📢 Current channel: {current_channel}"
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить канал" if lang == 'ru' else "➕ Add channel")],
        [KeyboardButton(text="❌ Удалить канал" if lang == 'ru' else "❌ Delete channel")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(channel_text, reply_markup=keyboard)

@dp.message(F.text.in_(["➕ Добавить канал", "➕ Add channel"]))
async def add_channel_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите @канал для обязательной подписки:" if lang == 'ru' else "Enter @channel for mandatory subscription:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.channel_add)

@dp.message(AdminStates.channel_add)
async def add_channel_save(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await channel_management(message, state)
        await state.clear()
        return
    
    channel = message.text.strip()
    if not channel.startswith("@"):
        await message.answer("❌ Канал должен начинаться с @" if lang == 'ru' else "❌ Channel must start with @")
        return
    
    set_channel(channel)
    await state.clear()
    await message.answer(
        f"✅ Канал {channel} добавлен в обязательную подписку!" if lang == 'ru' else f"✅ Channel {channel} added to mandatory subscription!",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["❌ Удалить канал", "❌ Delete channel"]))
async def delete_channel_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    current = get_channel()
    if not current:
        await message.answer(
            "❌ Канал не установлен" if lang == 'ru' else "❌ Channel not set",
            reply_markup=admin_keyboard(lang)
        )
        return
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Да, удалить" if lang == 'ru' else "✅ Yes, delete")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        f"⚠️ Вы уверены, что хотите удалить канал {current}?" if lang == 'ru' else f"⚠️ Are you sure you want to delete channel {current}?",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.channel_delete)

@dp.message(AdminStates.channel_delete)
async def delete_channel_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await channel_management(message, state)
        await state.clear()
        return
    
    if message.text in ["✅ Да, удалить", "✅ Yes, delete"]:
        set_channel("")
        await state.clear()
        await message.answer(
            "✅ Канал удалён из обязательной подписки!" if lang == 'ru' else "✅ Channel removed from mandatory subscription!",
            reply_markup=admin_keyboard(lang)
        )
    else:
        await message.answer(
            "❌ Отмена" if lang == 'ru' else "❌ Cancelled",
            reply_markup=admin_keyboard(lang)
        )
        await state.clear()

# ========== РАССЫЛКА ==========
@dp.message(F.text.in_(["📢 Рассылка", "📢 Broadcast"]))
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "📢 Введите текст рассылки:" if lang == 'ru' else "📢 Enter broadcast text:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.broadcast)

@dp.message(AdminStates.broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    users = db_execute("SELECT user_id, language FROM users WHERE is_banned = 0")
    success = 0
    
    await message.answer(
        f"📢 Начинаю рассылку {len(users)} пользователям..." if lang == 'ru' else f"📢 Starting broadcast to {len(users)} users..."
    )
    
    for user_data in users:
        try:
            await bot.send_message(user_data[0], message.text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await state.clear()
    await message.answer(
        f"✅ Отправлено: {success}/{len(users)}" if lang == 'ru' else f"✅ Sent: {success}/{len(users)}"
    )

# ========== БАНЫ ==========
@dp.message(F.text.in_(["🚫 Баны", "🚫 Bans"]))
async def ban_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔨 Забанить" if lang == 'ru' else "🔨 Ban")],
        [KeyboardButton(text="🔓 Разбанить" if lang == 'ru' else "🔓 Unban")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "🚫 Управление банами" if lang == 'ru' else "🚫 Ban management",
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["🔨 Забанить", "🔨 Ban"]))
async def ban_user_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID или @username" if lang == 'ru' else "Enter ID or @username",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.ban_user)

@dp.message(AdminStates.ban_user)
async def ban_user_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except:
        username = message.text.strip().replace("@", "")
        user_data = db_execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if not user_data:
            await message.answer("❌ Не найден" if lang == 'ru' else "❌ Not found")
            return
        user_id = user_data[0][0]
    
    db_execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    await state.clear()
    await message.answer(
        f"✅ Забанен {user_id}" if lang == 'ru' else f"✅ Banned {user_id}",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["🔓 Разбанить", "🔓 Unban"]))
async def unban_user_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID или @username" if lang == 'ru' else "Enter ID or @username",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.unban_user)

@dp.message(AdminStates.unban_user)
async def unban_user_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except:
        username = message.text.strip().replace("@", "")
        user_data = db_execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if not user_data:
            await message.answer("❌ Не найден" if lang == 'ru' else "❌ Not found")
            return
        user_id = user_data[0][0]
    
    db_execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    await state.clear()
    await message.answer(
        f"✅ Разбанен {user_id}" if lang == 'ru' else f"✅ Unbanned {user_id}",
        reply_markup=admin_keyboard(lang)
    )

# ========== УПРАВЛЕНИЕ БАЛАНСОМ ==========
@dp.message(F.text.in_(["🔨 Управление балансом", "🔨 Balance management"]))
async def balance_admin_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Выдать GET" if lang == 'ru' else "➕ Add GET")],
        [KeyboardButton(text="➖ Забрать GET" if lang == 'ru' else "➖ Remove GET")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "🔨 Управление балансом" if lang == 'ru' else "🔨 Balance management",
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["➕ Выдать GET", "➕ Add GET"]))
async def add_balance_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID и сумму через пробел" if lang == 'ru' else "Enter ID and amount separated by space",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.add_balance)

@dp.message(AdminStates.add_balance)
async def add_balance_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Нужно ID и сумма" if lang == 'ru' else "❌ Need ID and amount")
        return
    
    try:
        user_id, amount = int(parts[0]), int(parts[1])
    except:
        await message.answer("❌ Неверный формат" if lang == 'ru' else "❌ Invalid format")
        return
    
    add_balance(user_id, amount)
    await state.clear()
    await message.answer(
        f"✅ +{amount} GET пользователю {user_id}" if lang == 'ru' else f"✅ +{amount} GET to user {user_id}",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["➖ Забрать GET", "➖ Remove GET"]))
async def remove_balance_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID и сумму" if lang == 'ru' else "Enter ID and amount",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.remove_balance)

@dp.message(AdminStates.remove_balance)
async def remove_balance_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Нужно ID и сумма" if lang == 'ru' else "❌ Need ID and amount")
        return
    
    try:
        user_id, amount = int(parts[0]), int(parts[1])
    except:
        await message.answer("❌ Неверный формат" if lang == 'ru' else "❌ Invalid format")
        return
    
    if subtract_balance(user_id, amount):
        await message.answer(
            f"✅ -{amount} GET у {user_id}" if lang == 'ru' else f"✅ -{amount} GET from {user_id}",
            reply_markup=admin_keyboard(lang)
        )
    else:
        await message.answer(
            "❌ Недостаточно средств" if lang == 'ru' else "❌ Insufficient funds",
            reply_markup=admin_keyboard(lang)
        )
    await state.clear()

# ========== ЗАЯВКИ НА ПОПОЛНЕНИЕ ==========
@dp.message(F.text.in_(["💳 Заявки на пополнение", "💳 Deposit requests"]))
async def deposit_requests_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    requests = db_execute("""
        SELECT id, user_id, request_id, stars_amount, get_amount, status, created_at 
        FROM deposit_requests WHERE status = 'pending'
    """)
    
    if not requests:
        await message.answer("📭 Нет заявок" if lang == 'ru' else "📭 No requests")
        return
    
    for req in requests:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить" if lang == 'ru' else "✅ Confirm", callback_data=f"confirm_dep_{req[0]}")],
            [InlineKeyboardButton(text="❌ Отклонить" if lang == 'ru' else "❌ Reject", callback_data=f"reject_dep_{req[0]}")]
        ])
        await message.answer(
            f"📩 #{req[2]}\n👤 {req[1]}\n⭐ {req[3]} = {req[4]} GET",
            reply_markup=keyboard
        )

@dp.callback_query(F.data.startswith("confirm_dep_"))
async def confirm_deposit(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    req = db_execute("SELECT * FROM deposit_requests WHERE id = ?", (req_id,))
    if not req:
        await callback.answer("❌ Нет")
        return
    
    req = req[0]
    add_balance(req[1], req[4])
    db_execute("UPDATE deposit_requests SET status = 'completed' WHERE id = ?", (req_id,))
    
    user = get_user(req[1])
    lang = user[2] if user else 'ru'
    await bot.send_message(req[1], f"✅ Пополнено на {req[4]} GET!" if lang == 'ru' else f"✅ Deposited {req[4]} GET!")
    await callback.message.edit_text(f"✅ Заявка {req[2]} подтверждена")
    await callback.answer("✅")

@dp.callback_query(F.data.startswith("reject_dep_"))
async def reject_deposit(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    db_execute("UPDATE deposit_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    await callback.message.edit_text("❌ Отклонено")
    await callback.answer("❌")

# ========== ЗАЯВКИ НА ВЫВОД ==========
@dp.message(F.text.in_(["💸 Заявки на вывод", "💸 Withdraw requests"]))
async def withdraw_requests_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    requests = db_execute("""
        SELECT id, user_id, username, get_amount, stars_amount, gift_name, status, created_at 
        FROM withdraw_requests WHERE status = 'pending'
    """)
    
    if not requests:
        await message.answer("📭 Нет заявок" if lang == 'ru' else "📭 No requests")
        return
    
    for req in requests:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить" if lang == 'ru' else "✅ Confirm", callback_data=f"confirm_wd_{req[0]}")],
            [InlineKeyboardButton(text="❌ Отклонить" if lang == 'ru' else "❌ Reject", callback_data=f"reject_wd_{req[0]}")]
        ])
        await message.answer(
            f"🎁 {req[5]}\n👤 @{req[2]}\n⭐ {req[4]} = {req[3]} GET",
            reply_markup=keyboard
        )

@dp.callback_query(F.data.startswith("confirm_wd_"))
async def confirm_withdraw(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    req = db_execute("SELECT * FROM withdraw_requests WHERE id = ?", (req_id,))
    if not req:
        await callback.answer("❌ Нет")
        return
    
    req = req[0]
    db_execute("UPDATE withdraw_requests SET status = 'completed' WHERE id = ?", (req_id,))
    
    user = get_user(req[1])
    lang = user[2] if user else 'ru'
    await bot.send_message(req[1], 
        f"✅ Вывод подтверждён! {req[5]} отправлен." if lang == 'ru' else f"✅ Withdrawal confirmed! {req[5]} sent.")
    await callback.message.edit_text(f"✅ Заявка {req_id} подтверждена")
    await callback.answer("✅")

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
        user = get_user(req[0][1])
        lang = user[2] if user else 'ru'
        await bot.send_message(req[0][1], 
            "❌ Заявка отклонена, GET возвращены." if lang == 'ru' else "❌ Request rejected, GET returned.")
    
    await callback.message.edit_text("❌ Отклонено")
    await callback.answer("❌")

# ========== ПРОМОКОДЫ ==========
@dp.message(F.text.in_(["🎟 Создать промокод", "🎟 Create promo"]))
async def create_promo_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "🎟 Введите код:" if lang == 'ru' else "🎟 Enter code:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.promo_code)

@dp.message(AdminStates.promo_code)
async def create_promo_code(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    code = message.text.strip().upper()
    if not code:
        await message.answer("❌ Пусто" if lang == 'ru' else "❌ Empty")
        return
    
    await state.update_data(promo_code=code)
    await message.answer(
        "Введите бонус в GET:" if lang == 'ru' else "Enter bonus in GET:"
    )
    await state.set_state(AdminStates.promo_bonus)

@dp.message(AdminStates.promo_bonus)
async def create_promo_bonus(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        bonus = int(message.text.strip())
    except:
        await message.answer("❌ Число" if lang == 'ru' else "❌ Number")
        return
    
    await state.update_data(promo_bonus=bonus)
    await message.answer(
        "Лимит (0 - безлимит):" if lang == 'ru' else "Limit (0 - unlimited):"
    )
    await state.set_state(AdminStates.promo_limit)

@dp.message(AdminStates.promo_limit)
async def create_promo_limit(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        limit = int(message.text.strip())
    except:
        await message.answer("❌ Число" if lang == 'ru' else "❌ Number")
        return
    
    data = await state.get_data()
    db_execute("""
        INSERT INTO promo_codes (code, bonus_get, uses_limit, created_at)
        VALUES (?, ?, ?, ?)
    """, (data['promo_code'], data['promo_bonus'], limit, datetime.now().isoformat()))
    
    await state.clear()
    await message.answer(
        f"✅ Промокод {data['promo_code']} +{data['promo_bonus']} GET" if lang == 'ru' else f"✅ Promo {data['promo_code']} +{data['promo_bonus']} GET",
        reply_markup=admin_keyboard(lang)
    )

# ========== КОНКУРСЫ (АДМИН) ==========
@dp.message(F.text.in_(["🎯 Конкурсы", "🎯 Contests"]))
async def contests_admin_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать конкурс" if lang == 'ru' else "➕ Create contest")],
        [KeyboardButton(text="📋 Активные конкурсы" if lang == 'ru' else "📋 Active contests")],
        [KeyboardButton(text="🏆 Выдать бонусы" if lang == 'ru' else "🏆 Give bonuses")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "🎯 Управление конкурсами" if lang == 'ru' else "🎯 Contest management",
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["➕ Создать конкурс", "➕ Create contest"]))
async def create_contest_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "📌 Название конкурса:" if lang == 'ru' else "📌 Contest name:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.contest_name)

@dp.message(AdminStates.contest_name)
async def create_contest_name(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    await state.update_data(contest_name=message.text.strip())
    await message.answer(
        "📝 Описание конкурса:" if lang == 'ru' else "📝 Contest description:"
    )
    await state.set_state(AdminStates.contest_desc)

@dp.message(AdminStates.contest_desc)
async def create_contest_desc(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    await state.update_data(contest_desc=message.text.strip())
    await message.answer(
        "💰 Бонус за участие (GET):" if lang == 'ru' else "💰 Bonus for participation (GET):"
    )
    await state.set_state(AdminStates.contest_bonus)

@dp.message(AdminStates.contest_bonus)
async def create_contest_bonus(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        bonus = int(message.text.strip())
    except:
        await message.answer("❌ Число" if lang == 'ru' else "❌ Number")
        return
    
    await state.update_data(contest_bonus=bonus)
    await message.answer(
        "📅 Дата начала (ГГГГ-ММ-ДД):" if lang == 'ru' else "📅 Start date (YYYY-MM-DD):"
    )
    await state.set_state(AdminStates.contest_start)

@dp.message(AdminStates.contest_start)
async def create_contest_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        start = datetime.strptime(message.text.strip(), "%Y-%m-%d").isoformat()
    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД" if lang == 'ru' else "❌ Format: YYYY-MM-DD")
        return
    
    await state.update_data(contest_start=start)
    await message.answer(
        "📅 Дата окончания (ГГГГ-ММ-ДД):" if lang == 'ru' else "📅 End date (YYYY-MM-DD):"
    )
    await state.set_state(AdminStates.contest_end)

@dp.message(AdminStates.contest_end)
async def create_contest_end(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        end = datetime.strptime(message.text.strip(), "%Y-%m-%d").isoformat()
    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД" if lang == 'ru' else "❌ Format: YYYY-MM-DD")
        return
    
    data = await state.get_data()
    
    db_execute("""
        INSERT INTO contests (name, description, bonus_get, start_date, end_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data['contest_name'], data['contest_desc'], data['contest_bonus'], 
          data['contest_start'], end, datetime.now().isoformat()))
    
    await state.clear()
    await message.answer(
        f"✅ Конкурс '{data['contest_name']}' создан!" if lang == 'ru' else f"✅ Contest '{data['contest_name']}' created!",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["📋 Активные конкурсы", "📋 Active contests"]))
async def list_contests_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    contests = db_execute("SELECT id, name, description, bonus_get, start_date, end_date, is_active FROM contests")
    
    if not contests:
        await message.answer("📭 Нет конкурсов" if lang == 'ru' else "📭 No contests")
        return
    
    text = "📋 Конкурсы:\n\n" if lang == 'ru' else "📋 Contests:\n\n"
    for c in contests:
        status = "✅ Активен" if c[6] == 1 else "❌ Не активен"
        if lang == 'en':
            status = "✅ Active" if c[6] == 1 else "❌ Inactive"
        text += f"#{c[0]}: {c[1]}\n📝 {c[2]}\n💰 {c[3]} GET\n📅 {c[4][:10]} → {c[5][:10]}\n{status}\n{'='*20}\n\n"
    
    await message.answer(text[:4000])

@dp.message(F.text.in_(["🏆 Выдать бонусы", "🏆 Give bonuses"]))
async def give_contest_bonuses(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID конкурса для выдачи бонусов:" if lang == 'ru' else "Enter contest ID to give bonuses:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.leaderboard_bonus)

@dp.message(AdminStates.leaderboard_bonus)
async def give_contest_bonuses_execute(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        contest_id = int(message.text.strip())
    except:
        await message.answer("❌ Введите число" if lang == 'ru' else "❌ Enter a number")
        return
    
    contest = db_execute("SELECT * FROM contests WHERE id = ?", (contest_id,))
    if not contest:
        await message.answer("❌ Конкурс не найден" if lang == 'ru' else "❌ Contest not found")
        return
    
    participants = db_execute("""
        SELECT user_id, completed_tasks
        FROM contest_participants
        WHERE contest_id = ?
        ORDER BY completed_tasks DESC
        LIMIT 3
    """, (contest_id,))
    
    if not participants:
        await message.answer("📭 Нет участников" if lang == 'ru' else "📭 No participants")
        await state.clear()
        return
    
    contest = contest[0]
    text = f"🏆 Призеры конкурса '{contest[1]}':\n\n" if lang == 'ru' else f"🏆 Contest '{contest[1]}' winners:\n\n"
    
    bonuses = [contest[3], contest[3] // 2, contest[3] // 3]
    
    for i, participant in enumerate(participants[:3]):
        user_id, tasks_done = participant
        bonus = bonuses[i] if i < len(bonuses) else 0
        add_balance(user_id, bonus)
        text += f"{i+1}. Пользователь {user_id} — {tasks_done} заданий, +{bonus} GET\n" if lang == 'ru' else f"{i+1}. User {user_id} — {tasks_done} tasks, +{bonus} GET\n"
        
        try:
            await bot.send_message(user_id, 
                f"🏆 Вы заняли {i+1} место в конкурсе '{contest[1]}'!\n💰 +{bonus} GET на баланс!" if lang == 'ru' else
                f"🏆 You took {i+1} place in contest '{contest[1]}'!\n💰 +{bonus} GET to balance!")
        except:
            pass
    
    await state.clear()
    await message.answer(text, reply_markup=admin_keyboard(lang))

# ========== ПОЛЬЗОВАТЕЛИ ==========
@dp.message(F.text.in_(["👥 Пользователи", "👥 Users"]))
async def users_list(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    banned = db_execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")[0][0]
    total = db_execute("SELECT SUM(balance) FROM users")[0][0]
    verified = db_execute("SELECT COUNT(*) FROM users WHERE is_verified = 1")[0][0]
    
    await message.answer(
        f"👥 Всего: {users}\n✅ Верифицированы: {verified}\n🚫 Забанено: {banned}\n💰 Общий баланс: {total if total else 0}\n🌐 Языки: RU/EN" if lang == 'ru' else
        f"👥 Total: {users}\n✅ Verified: {verified}\n🚫 Banned: {banned}\n💰 Total balance: {total if total else 0}\n🌐 Languages: RU/EN"
    )

# ========== ПРОМОКОДЫ (ДЛЯ ПОЛЬЗОВАТЕЛЕЙ) ==========
@dp.message(Command("promo"))
async def use_promo(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ /promo КОД" if lang == 'ru' else "❌ /promo CODE")
        return
    
    code = args[1].upper()
    promo = db_execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
    if not promo:
        await message.answer("❌ Не найден" if lang == 'ru' else "❌ Not found")
        return
    
    promo = promo[0]
    used = db_execute("SELECT * FROM promo_uses WHERE promo_id = ? AND user_id = ?", (promo[0], message.from_user.id))
    if used:
        await message.answer("❌ Уже использован" if lang == 'ru' else "❌ Already used")
        return
    
    if promo[3] > 0 and promo[4] >= promo[3]:
        await message.answer("❌ Лимит исчерпан" if lang == 'ru' else "❌ Limit reached")
        return
    
    add_balance(message.from_user.id, promo[2])
    db_execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", (promo[0],))
    db_execute("INSERT INTO promo_uses (promo_id, user_id, created_at) VALUES (?, ?, ?)",
               (promo[0], message.from_user.id, datetime.now().isoformat()))
    
    await message.answer(f"✅ +{promo[2]} GET" if lang == 'ru' else f"✅ +{promo[2]} GET")

# ========== ЗАПУСК ==========
async def main():
    init_db()
    logging.info("🚀 Бот запущен!")
    logging.info(f"📱 Бот: @{BOT_USERNAME}")
    logging.info(f"👑 Админ: {ADMIN_IDS[0]}")
    logging.info(f"📢 Канал: {get_channel()}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
