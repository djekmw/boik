import random
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = "8949176656:AAHWimiNzkL4gN4ZxXrjkHav5V3y5DPglM8"
ADMIN_ID = 7587884784  # Ваш Telegram ID

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("casino.db")
    cursor = conn.cursor()
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 1000,
            forced_losses INTEGER DEFAULT 0
        )
    """)
    # Таблица глобальных настроек админа
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    """)
    # Значение порога ставки по умолчанию ($300)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_loss_limit', 300)")
    conn.commit()
    conn.close()

init_db()

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("casino.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = None
    if fetchone:
        data = cursor.fetchone()
    elif fetchall:
        data = cursor.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return data

def get_user_data(user_id: int):
    user = db_query("SELECT balance, forced_losses FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        db_query("INSERT INTO users (user_id, balance, forced_losses) VALUES (?, 1000, 0)", (user_id,), commit=True)
        return {"balance": 1000, "forced_losses": 0}
    return {"balance": user[0], "forced_losses": user[1]}

def update_balance(user_id: int, amount: int):
    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id), commit=True)

def get_auto_loss_limit():
    res = db_query("SELECT value FROM settings WHERE key = 'auto_loss_limit'", fetchone=True)
    return res[0] if res else 300

def set_auto_loss_limit(limit: int):
    db_query("UPDATE settings SET value = ? WHERE key = 'auto_loss_limit'", (limit,), commit=True)

# Проверка: должен ли игрок проиграть в этом раунде
def should_user_lose(user_id: int, current_bet: int) -> bool:
    user = get_user_data(user_id)
    forced_losses = user["forced_losses"]
    limit = get_auto_loss_limit()

    # 1. Принудительные проигрыши от админа
    if forced_losses > 0:
        db_query("UPDATE users SET forced_losses = forced_losses - 1 WHERE user_id = ?", (user_id,), commit=True)
        return True

    # 2. Если ставка выше лимита
    if current_bet >= limit:
        return True

    return False

# --- КЛАВИАТУРЫ ---
def main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Угадай число (1-5)", callback_data="game_guess")
    builder.button(text="📊 Больше / Меньше", callback_data="game_hl")
    builder.button(text="🎲 Чет / Нечет", callback_data="game_even")
    builder.button(text="💰 Мой баланс", callback_data="check_balance")
    builder.adjust(1)
    return builder.as_markup()

def bet_keyboard(game_code: str):
    builder = InlineKeyboardBuilder()
    for bet in [50, 100, 250, 500]:
        builder.button(text=f"${bet}", callback_data=f"setbet_{game_code}_{bet}")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

user_bets = {}

# --- ОСНОВНЫЕ КОМАНДЫ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    data = get_user_data(message.from_user.id)
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"💵 Твой баланс: **${data['balance']}**\n"
        f"Выбери игру:",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выбери игру:", reply_markup=main_keyboard())

@dp.callback_query(F.data == "check_balance")
async def check_balance(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    await callback.answer(f"Твой баланс: ${data['balance']}", show_alert=True)

# --- РАСШИРЕННАЯ АДМИНКА ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = db_query("SELECT user_id, balance, forced_losses FROM users", fetchall=True)
    limit = get_auto_loss_limit()

    text = "🛠 **ПАНЕЛЬ АДМИНИСТРАТОРА**\n\n"
    text += f"⚙️ Авто-проигрыш при ставке от: **${limit}**\n\n"
    text += "📊 **Список игроков:**\n"

    for u in users:
        text += f"👤 ID: `{u[0]}` | Баланс: **${u[1]}** | Подкрутка: **{u[2]} игр**\n"

    text += "\n**Команды админа:**\n"
    text += "• `/give ID СУММА` — выдать баланс (пример: `/give 12345 500`)\n"
    text += "• `/take ID СУММА` — забрать баланс (пример: `/take 12345 300`)\n"
    text += "• `/rig ID ИГР` — сделать N проигрышей подряд (пример: `/rig 12345 3`)\n"
    text += "• `/setlimit СУММА` — авто-проигрыш при ставке >= СУММА (пример: `/setlimit 400`)\n"
    text += "• `/bc ТЕКСТ` — рассылка всем игрокам\n"

    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("give"))
async def give_money(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, amount = message.text.split()
        update_balance(int(target_id), int(amount))
        await message.answer(f"✅ Выдано ${amount} пользователю `{target_id}`", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/give ID СУММА`", parse_mode="Markdown")

@dp.message(Command("take"))
async def take_money(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, amount = message.text.split()
        update_balance(int(target_id), -int(amount))
        await message.answer(f"✅ Забрано ${amount} у пользователя `{target_id}`", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/take ID СУММА`", parse_mode="Markdown")

@dp.message(Command("rig"))
async def set_rig(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, games_count = message.text.split()
        db_query("UPDATE users SET forced_losses = ? WHERE user_id = ?", (int(games_count), int(target_id)), commit=True)
        await message.answer(f"😈 Пользователь `{target_id}` проиграет следующие **{games_count}** игр!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/rig ID КОЛИЧЕСТВО_ИГР`", parse_mode="Markdown")

@dp.message(Command("setlimit"))
async def change_limit(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, limit = message.text.split()
        set_auto_loss_limit(int(limit))
        await message.answer(f"⚙️ Теперь ставки от **${limit}** будут автоматически проигрышными!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/setlimit СУММА`", parse_mode="Markdown")

@dp.message(Command("bc"))
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text_to_send = message.text.replace("/bc ", "").strip()
    if not text_to_send or text_to_send == "/bc":
        await message.answer("❌ Введите текст для рассылки!")
        return

    users = db_query("SELECT user_id FROM users", fetchall=True)
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 **Объявление:**\n\n{text_to_send}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Сообщение отправлено **{count}** пользователям!")

# --- ИГРОВАЯ ЛОГИКА С ПОДКТРУТКОЙ ---
@dp.callback_query(F.data.startswith("game_"))
async def choose_bet(callback: types.CallbackQuery):
    game_code = callback.data.split("_")[1]
    await callback.message.edit_text("Выбери сумму ставки:", reply_markup=bet_keyboard(game_code))

# ИГРА 1: УГАДАЙ ЧИСЛО
@dp.callback_query(F.data.startswith("setbet_guess_"))
async def guess_game_start(callback: types.CallbackQuery):
    bet = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    if data["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    user_bets[user_id] = bet
    builder = InlineKeyboardBuilder()
    for num in range(1, 6):
        builder.button(text=str(num), callback_data=f"play_guess_{num}")
    builder.adjust(5)
    
    await callback.message.edit_text(f"Ставка: **${bet}**\nУгадай число от 1 до 5:", parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("play_guess_"))
async def guess_game_result(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bet = user_bets.get(user_id, 50)
    user_choice = int(callback.data.split("_")[2])

    force_loss = should_user_lose(user_id, bet)

    if force_loss:
        # Генерируем число, отличающееся от выбора игрока
        options = [n for n in range(1, 6) if n != user_choice]
        secret_num = random.choice(options)
    else:
        secret_num = random.randint(1, 5)

    if user_choice == secret_num:
        win = int(bet * 3)
        update_balance(user_id, win - bet)
        res_text = f"🎉 **Победа!** Выпало число {secret_num}.\nТвой выигрыш: **+${win}**"
    else:
        update_balance(user_id, -bet)
        res_text = f"❌ **Проигрыш!** Было загадано число {secret_num}."

    data = get_user_data(user_id)
    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.edit_text(res_text, parse_mode="Markdown", reply_markup=main_keyboard())

# ИГРА 2: БОЛЬШЕ / МЕНЬШЕ
@dp.callback_query(F.data.startswith("setbet_hl_"))
async def hl_game_start(callback: types.CallbackQuery):
    bet = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    if data["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    user_bets[user_id] = bet
    builder = InlineKeyboardBuilder()
    builder.button(text="📉 Меньше (1-3)", callback_data="play_hl_low")
    builder.button(text="📈 Больше (4-6)", callback_data="play_hl_high")
    builder.adjust(2)
    
    await callback.message.edit_text(f"Ставка: **${bet}**\nБросаем кость (1-6). Какое число выпадет?", parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("play_hl_"))
async def hl_game_result(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bet = user_bets.get(user_id, 50)
    choice = callback.data.split("_")[2]

    force_loss = should_user_lose(user_id, bet)

    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(2)

    if force_loss:
        dice_val = random.randint(4, 6) if choice == "low" else random.randint(1, 3)
    else:
        dice_val = dice_msg.dice.value

    is_win = (choice == "low" and dice_val <= 3) or (choice == "high" and dice_val >= 4)

    if is_win:
        win = int(bet * 1.8)
        update_balance(user_id, win - bet)
        res_text = f"🎉 **Выигрыш!** Выпало {dice_val}.\nТвой плюс: **+${win}**"
    else:
        update_balance(user_id, -bet)
        res_text = f"❌ **Проигрыш!** Выпало {dice_val}."

    data = get_user_data(user_id)
    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.answer(res_text, parse_mode="Markdown", reply_markup=main_keyboard())

# ИГРА 3: ЧЕТ / НЕЧЕТ
@dp.callback_query(F.data.startswith("setbet_even_"))
async def even_game_start(callback: types.CallbackQuery):
    bet = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    if data["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    user_bets[user_id] = bet
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Четное", callback_data="play_even_even")
    builder.button(text="🔵 Нечетное", callback_data="play_even_odd")
    builder.adjust(2)
    
    await callback.message.edit_text(f"Ставка: **${bet}**\nЧетное или нечетное?", parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("play_even_"))
async def even_game_result(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bet = user_bets.get(user_id, 50)
    choice = callback.data.split("_")[2]

    force_loss = should_user_lose(user_id, bet)

    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(2)

    if force_loss:
        # Выбираем нечетное число, если игрок поставил на четное, и наоборот
        odds = [1, 3, 5]
        evens = [2, 4, 6]
        dice_val = random.choice(odds) if choice == "even" else random.choice(evens)
    else:
        dice_val = dice_msg.dice.value

    is_even = dice_val % 2 == 0
    is_win = (choice == "even" and is_even) or (choice == "odd" and not is_even)

    if is_win:
        win = int(bet * 1.8)
        update_balance(user_id, win - bet)
        res_text = f"🎉 **Отлично!** Выпало {dice_val}.\nТвой выигрыш: **+${win}**"
    else:
        update_balance(user_id, -bet)
        res_text = f"❌ **Не угадал!** Выпало {dice_val}."

    data = get_user_data(user_id)
    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.answer(res_text, parse_mode="Markdown", reply_markup=main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
