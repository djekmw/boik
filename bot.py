import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

TOKEN = "8949176656:AAHWimiNzkL4gN4ZxXrjkHav5V3y5DPglM8"
ADMIN_ID = 8815793802  # Ваш Telegram ID

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище данных
users_db = {}
user_bets = {}
auto_loss_limit = 300

# Состояние для ввода своей ставки
class BetState(StatesGroup):
    waiting_for_custom_bet = State()

def get_user_data(user_id: int):
    if user_id not in users_db:
        users_db[user_id] = {
            "balance": 1000, 
            "forced_losses": 0,
            "is_deleted": False,
            "banned_until": None
        }
    return users_db[user_id]

def check_access(user_id: int) -> tuple[bool, str]:
    """Проверка, может ли игрок пользоваться ботом"""
    user = get_user_data(user_id)
    
    if user["is_deleted"]:
        return False, "❌ Вы были удалены из системы LOMTIK GAME."
    
    if user["banned_until"]:
        now = datetime.now()
        if now < user["banned_until"]:
            remaining = user["banned_until"] - now
            minutes = int(remaining.total_seconds() // 60) + 1
            return False, f"⛔ **Вы заблокированы!**\nДо окончания бана осталось: **{minutes} мин.**"
        else:
            user["banned_until"] = None  # Бан истек
            
    return True, ""

def get_status(balance: int) -> str:
    if balance < 500:
        return "🥉 Новичок"
    elif balance < 2500:
        return "🥈 Игрок"
    elif balance < 10000:
        return "🥇 VIP-Игрок"
    else:
        return "💎 Магнат LOMTIK"

def should_user_lose(user_id: int, current_bet: int) -> bool:
    global auto_loss_limit
    user = get_user_data(user_id)
    
    if user["forced_losses"] > 0:
        user["forced_losses"] -= 1
        return True

    if current_bet >= auto_loss_limit:
        return True

    return False

# --- КЛАВИАТУРЫ ---
def main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Угадай число (1-5)", callback_data="game_guess")
    builder.button(text="📊 Больше / Меньше", callback_data="game_hl")
    builder.button(text="🎲 Чет / Нечет", callback_data="game_even")
    builder.button(text="💳 Мой профиль и баланс", callback_data="check_balance")
    builder.adjust(1)
    return builder.as_markup()

def bet_keyboard(game_code: str):
    builder = InlineKeyboardBuilder()
    for bet in [50, 100, 250, 500]:
        builder.button(text=f"💵 ${bet}", callback_data=f"setbet_{game_code}_{bet}")
    builder.button(text="✏️ Своя сумма", callback_data=f"custombet_{game_code}")
    builder.button(text="🔙 Главное меню", callback_data="main_menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

# --- ОСНОВНЫЕ КОМАНДЫ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    can_play, msg = check_access(user_id)
    if not can_play:
        await message.answer(msg, parse_mode="Markdown")
        return

    data = get_user_data(user_id)
    status = get_status(data['balance'])
    
    welcome_text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В LOMTIK GAME** ✨\n"
        "━━━━━━━ 🎰 ━━━━━━━\n\n"
        f"👤 **Игрок:** {message.from_user.first_name}\n"
        f"🆔 **Ваш ID:** `{user_id}`\n"
        f"🏆 Статус: **{status}**\n"
        f"💵 Баланс: **${data['balance']}**\n\n"
        "🔥 Испытай свою удачу прямо сейчас! Выбери игру ниже:"
    )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_keyboard())

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    await callback.message.edit_text(
        "🎰 **LOMTIK GAME — Главное меню**\n\nВыберите нужную игру:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "check_balance")
async def check_balance(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    data = get_user_data(callback.from_user.id)
    status = get_status(data['balance'])
    
    profile_text = (
        f"💳 **Профиль LOMTIK GAME**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 **Имя:** {callback.from_user.first_name}\n"
        f"🆔 **ID:** `{callback.from_user.id}`\n"
        f"🏆 **Статус:** {status}\n"
        f"💰 **Баланс:** ${data['balance']}"
    )
    
    await callback.answer(f"Твой баланс: ${data['balance']}", show_alert=True)
    await callback.message.edit_text(profile_text, parse_mode="Markdown", reply_markup=main_keyboard())

# --- ВВОД СВОЕЙ СТАВКИ ---
@dp.callback_query(F.data.startswith("custombet_"))
async def prompt_custom_bet(callback: types.CallbackQuery, state: FSMContext):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    game_code = callback.data.split("_")[1]
    await state.update_data(game_code=game_code)
    await state.set_state(BetState.waiting_for_custom_bet)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Отмена", callback_data="main_menu")
    
    await callback.message.edit_text(
        "✍️ **Введите вашу сумму ставки числом в чат:**\n(Минимум $1)",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@dp.message(BetState.waiting_for_custom_bet)
async def process_custom_bet(message: types.Message, state: FSMContext):
    can_play, msg = check_access(message.from_user.id)
    if not can_play:
        await message.answer(msg, parse_mode="Markdown")
        return

    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите корректное целое число!")
        return

    bet = int(message.text)
    if bet < 1:
        await message.answer("❌ Минимальная ставка — $1!")
        return

    user_id = message.from_user.id
    data = get_user_data(user_id)

    if data["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Твой баланс: **${data['balance']}**", parse_mode="Markdown")
        return

    fsm_data = await state.get_data()
    game_code = fsm_data.get("game_code")
    await state.clear()

    user_bets[user_id] = bet

    if game_code == "guess":
        builder = InlineKeyboardBuilder()
        for num in range(1, 6):
            builder.button(text=f"🔢 {num}", callback_data=f"play_guess_{num}")
        builder.adjust(5)
        await message.answer(f"🎯 **Угадай число**\n\nВаша ставка: **${bet}**\nВыбери число от 1 до 5:", parse_mode="Markdown", reply_markup=builder.as_markup())

    elif game_code == "hl":
        builder = InlineKeyboardBuilder()
        builder.button(text="📉 Меньше (1-3)", callback_data="play_hl_low")
        builder.button(text="📈 Больше (4-6)", callback_data="play_hl_high")
        builder.adjust(2)
        await message.answer(f"📊 **Больше или Меньше**\n\nСтавка: **${bet}**\nКуда упадет кость?", parse_mode="Markdown", reply_markup=builder.as_markup())

    elif game_code == "even":
        builder = InlineKeyboardBuilder()
        builder.button(text="🔴 Четное", callback_data="play_even_even")
        builder.button(text="🔵 Нечетное", callback_data="play_even_odd")
        builder.adjust(2)
        await message.answer(f"🎲 **Четное или Нечетное**\n\nСтавка: **${bet}**\nСделай выбор:", parse_mode="Markdown", reply_markup=builder.as_markup())

# --- АДМИНКА И БАНЫ ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return

    text = "🛠 **ПАНЕЛЬ АДМИНИСТРАТОРА LOMTIK GAME**\n\n"
    text += f"⚙️ Авто-проигрыш при ставке от: **${auto_loss_limit}**\n\n"
    text += "📊 **Список игроков:**\n"

    for u_id, u_data in users_db.items():
        status_tag = ""
        if u_data["is_deleted"]:
            status_tag = " [❌ УДАЛЕН]"
        elif u_data["banned_until"] and datetime.now() < u_data["banned_until"]:
            status_tag = " [⛔ В БАНЕ]"

        text += f"👤 ID: `{u_id}`{status_tag} | 💵 **${u_data['balance']}** | 😈 **{u_data['forced_losses']} игр**\n"

    text += "\n**Команды управления игроками:**\n"
    text += "• `/give ID СУММА` — выдать баланс\n"
    text += "• `/take ID СУММА` — забрать баланс\n"
    text += "• `/rig ID ИГР` — подкрутить проигрыши\n"
    text += "• `/ban ID МИНУТЫ` — забанить на время\n"
    text += "• `/unban ID` — разбанить игрока\n"
    text += "• `/delete_user ID` — полностью удалить пользователя\n"
    text += "• `/setlimit СУММА` — порог авто-слива\n"
    text += "• `/bc ТЕКСТ` — рассылка всем\n"

    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, minutes = message.text.split()
        data = get_user_data(int(target_id))
        data["banned_until"] = datetime.now() + timedelta(minutes=int(minutes))
        
        try:
            await bot.send_message(int(target_id), f"⛔ **Вы получили временную блокировку в игре на {minutes} мин.**")
        except: pass

        await message.answer(f"✅ Пользователь `{target_id}` заблокирован на **{minutes}** минут!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/ban ID МИНУТЫ`", parse_mode="Markdown")

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id = message.text.split()
        data = get_user_data(int(target_id))
        data["banned_until"] = None
        data["is_deleted"] = False
        
        try:
            await bot.send_message(int(target_id), "✅ **Ваш аккаунт был разблокирован! Снова добро пожаловать в игру.**")
        except: pass

        await message.answer(f"✅ Пользователь `{target_id}` успешно разбанен!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/unban ID`", parse_mode="Markdown")

@dp.message(Command("delete_user"))
async def delete_user(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id = message.text.split()
        data = get_user_data(int(target_id))
        data["is_deleted"] = True
        
        try:
            await bot.send_message(int(target_id), "❌ **Ваш профиль был полностью удален администратором.**")
        except: pass

        await message.answer(f"🗑 Пользователь `{target_id}` заблокирован и помечен как удаленный!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/delete_user ID`", parse_mode="Markdown")

@dp.message(Command("give"))
async def give_money(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, amount = message.text.split()
        data = get_user_data(int(target_id))
        data["balance"] += int(amount)
        await message.answer(f"✅ Выдано **${amount}** пользователю `{target_id}`", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/give ID СУММА`", parse_mode="Markdown")

@dp.message(Command("take"))
async def take_money(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, amount = message.text.split()
        data = get_user_data(int(target_id))
        data["balance"] -= int(amount)
        await message.answer(f"✅ Забрано **${amount}** у пользователя `{target_id}`", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/take ID СУММА`", parse_mode="Markdown")

@dp.message(Command("rig"))
async def set_rig(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, games_count = message.text.split()
        data = get_user_data(int(target_id))
        data["forced_losses"] = int(games_count)
        await message.answer(f"😈 Пользователь `{target_id}` проиграет следующие **{games_count}** игр!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/rig ID КОЛИЧЕСТВО_ИГР`", parse_mode="Markdown")

@dp.message(Command("setlimit"))
async def change_limit(message: types.Message):
    global auto_loss_limit
    if message.from_user.id != ADMIN_ID: return
    try:
        _, limit = message.text.split()
        auto_loss_limit = int(limit)
        await message.answer(f"⚙️ Ставки от **${limit}** теперь автоматически проигрышные!", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка! Используйте: `/setlimit СУММА`", parse_mode="Markdown")

@dp.message(Command("bc"))
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text_to_send = message.text.replace("/bc ", "").strip()
    if not text_to_send or text_to_send == "/bc":
        await message.answer("❌ Введите текст для рассылки!")
        return

    count = 0
    for u_id in users_db.keys():
        try:
            await bot.send_message(u_id, f"📢 **АНОНС LOMTIK GAME:**\n\n{text_to_send}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Сообщение отправлено **{count}** пользователям!")

# --- ИГРОВАЯ ЛОГИКА ---
@dp.callback_query(F.data.startswith("game_"))
async def choose_bet(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    game_code = callback.data.split("_")[1]
    await callback.message.edit_text("💰 **Выбери сумму ставки:**", reply_markup=bet_keyboard(game_code), parse_mode="Markdown")

# ИГРА 1: УГАДАЙ ЧИСЛО
@dp.callback_query(F.data.startswith("setbet_guess_"))
async def guess_game_start(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    bet = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    if data["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    user_bets[user_id] = bet
    builder = InlineKeyboardBuilder()
    for num in range(1, 6):
        builder.button(text=f"🔢 {num}", callback_data=f"play_guess_{num}")
    builder.adjust(5)
    
    await callback.message.edit_text(f"🎯 **Угадай число**\n\nВаша ставка: **${bet}**\nВыбери число от 1 до 5:", parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("play_guess_"))
async def guess_game_result(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    user_id = callback.from_user.id
    bet = user_bets.get(user_id, 50)
    user_choice = int(callback.data.split("_")[2])

    force_loss = should_user_lose(user_id, bet)

    if force_loss:
        options = [n for n in range(1, 6) if n != user_choice]
        secret_num = random.choice(options)
    else:
        secret_num = random.randint(1, 5)

    data = get_user_data(user_id)
    if user_choice == secret_num:
        win = int(bet * 3)
        data["balance"] += win - bet
        res_text = (
            f"🎉 **ПОБЕДА!** 🎉\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Загадано: **{secret_num}** | Ваш выбор: **{user_choice}**\n"
            f"🟢 Выигрыш: **+${win}**"
        )
    else:
        data["balance"] -= bet
        res_text = (
            f"💥 **ПРОИГРЫШ**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Загадано: **{secret_num}** | Ваш выбор: **{user_choice}**\n"
            f"🔴 Списано: **-${bet}**"
        )

    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.edit_text(res_text, parse_mode="Markdown", reply_markup=main_keyboard())

# ИГРА 2: БОЛЬШЕ / МЕНЬШЕ
@dp.callback_query(F.data.startswith("setbet_hl_"))
async def hl_game_start(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

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
    
    await callback.message.edit_text(f"📊 **Больше или Меньше**\n\nСтавка: **${bet}**\nКуда упадет кость?", parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("play_hl_"))
async def hl_game_result(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

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
    data = get_user_data(user_id)

    if is_win:
        win = int(bet * 1.8)
        data["balance"] += win - bet
        res_text = (
            f"🎉 **ОТЛИЧНЫЙ БРОСОК!** 🎉\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎲 Выпало: **{dice_val}**\n"
            f"🟢 Выигрыш: **+${win}**"
        )
    else:
        data["balance"] -= bet
        res_text = (
            f"💥 **НЕ УГАДАЛ**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎲 Выпало: **{dice_val}**\n"
            f"🔴 Проигрыш: **-${bet}**"
        )

    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.answer(res_text, parse_mode="Markdown", reply_markup=main_keyboard())

# ИГРА 3: ЧЕТ / НЕЧЕТ
@dp.callback_query(F.data.startswith("setbet_even_"))
async def even_game_start(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

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
    
    await callback.message.edit_text(f"🎲 **Четное или Нечетное**\n\nСтавка: **${bet}**\nСделай выбор:", parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("play_even_"))
async def even_game_result(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return

    user_id = callback.from_user.id
    bet = user_bets.get(user_id, 50)
    choice = callback.data.split("_")[2]

    force_loss = should_user_lose(user_id, bet)

    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(2)

    if force_loss:
        odds = [1, 3, 5]
        evens = [2, 4, 6]
        dice_val = random.choice(odds) if choice == "even" else random.choice(evens)
    else:
        dice_val = dice_msg.dice.value

    is_even = dice_val % 2 == 0
    is_win = (choice == "even" and is_even) or (choice == "odd" and not is_even)
    data = get_user_data(user_id)

    if is_win:
        win = int(bet * 1.8)
        data["balance"] += win - bet
        res_text = (
            f"🎉 **ТОЧНО В ЦЕЛЬ!** 🎉\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎲 Выпало: **{dice_val}**\n"
            f"🟢 Выигрыш: **+${win}**"
        )
    else:
        data["balance"] -= bet
        res_text = (
            f"💥 **НЕ УГАДАЛ**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎲 Выпало: **{dice_val}**\n"
            f"🔴 Проигрыш: **-${bet}**"
        )

    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.answer(res_text, parse_mode="Markdown", reply_markup=main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
