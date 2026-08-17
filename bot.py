import random
import asyncio
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

TOKEN = "8949176656:AAHWimiNzkL4gN4ZxXrjkHav5V3y5DPglM8"
ADMIN_ID = 8815793802

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "users_data.json"
users_db = {}
user_bets = {}
auto_loss_limit = 300


# --- СОХРАНЕНИЕ И ЗАГРУЗКА БАЗЫ ДАННЫХ ---
def load_db():
    global users_db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for u_id, u_data in data.items():
                    if u_data.get("banned_until"):
                        u_data["banned_until"] = datetime.fromisoformat(u_data["banned_until"])
                    users_db[int(u_id)] = u_data
        except Exception as e:
            print(f"Ошибка загрузки БД: {e}")


def save_db():
    try:
        data_to_save = {}
        for u_id, u_data in users_db.items():
            copy_data = u_data.copy()
            if copy_data.get("banned_until"):
                copy_data["banned_until"] = copy_data["banned_until"].isoformat()
            data_to_save[str(u_id)] = copy_data
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения БД: {e}")


class BetState(StatesGroup):
    waiting_for_custom_bet = State()


def get_user_data(user_id: int):
    if user_id not in users_db:
        users_db[user_id] = {
            "balance": 1000,
            "forced_losses": 0,
            "forced_wins": 0,
            "is_deleted": False,
            "banned_until": None
        }
        save_db()
    if "forced_wins" not in users_db[user_id]:
        users_db[user_id]["forced_wins"] = 0
    return users_db[user_id]


def check_access(user_id: int) -> tuple[bool, str]:
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
            user["banned_until"] = None
            save_db()
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


def get_rig_mode(user_id: int, current_bet: int) -> str:
    global auto_loss_limit
    user = get_user_data(user_id)
    if user.get("forced_wins", 0) > 0:
        user["forced_wins"] -= 1
        save_db()
        return "win"
    if user.get("forced_losses", 0) > 0:
        user["forced_losses"] -= 1
        save_db()
        return "loss"
    if current_bet >= auto_loss_limit:
        return "loss"
    return "none"


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


def post_game_keyboard(game_code: str, last_bet: int, user_balance: int):
    builder = InlineKeyboardBuilder()
    double_bet = last_bet * 2
    va_bank_bet = max(0, user_balance)
    builder.button(text="🔄 Еще раз", callback_data=f"setbet_{game_code}_{last_bet}")
    builder.button(text=f"✖️2️⃣ Х2 (${double_bet})", callback_data=f"setbet_{game_code}_{double_bet}")
    builder.button(text=f"🔥 ВБ (${va_bank_bet})", callback_data=f"setbet_{game_code}_{va_bank_bet}")
    builder.button(text="🔙 Главное меню", callback_data="main_menu")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


# --- КОМАНДЫ ---
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
    await callback.message.edit_text("🎰 **LOMTIK GAME — Главное меню**\n\nВыберите нужную игру:", reply_markup=main_keyboard(), parse_mode="Markdown")


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


# --- ИГРЫ И СТАВКИ ---
@dp.callback_query(F.data.in_(["game_guess", "game_hl", "game_even"]))
async def select_game(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    game_code = callback.data.split("_")[1]
    await callback.message.edit_text("💵 **Выберите размер вашей ставки:**", reply_markup=bet_keyboard(game_code), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("setbet_"))
async def set_bet_value(callback: types.CallbackQuery):
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    _, game_code, bet_str = callback.data.split("_")
    bet = int(bet_str)
    user_id = callback.from_user.id
    data = get_user_data(user_id)

    if bet < 1:
        await callback.answer("❌ Ставка должна быть больше $0!", show_alert=True)
        return

    if data["balance"] < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: ${data['balance']}", show_alert=True)
        return

    user_bets[user_id] = bet

    if game_code == "guess":
        builder = InlineKeyboardBuilder()
        for num in range(1, 6):
            builder.button(text=f"🔢 {num}", callback_data=f"play_guess_{num}")
        builder.adjust(5)
        await callback.message.edit_text(f"🎯 **Угадай число**\n\nВаша ставка: **${bet}**\nВыбери число от 1 до 5:", parse_mode="Markdown", reply_markup=builder.as_markup())
    elif game_code == "hl":
        builder = InlineKeyboardBuilder()
        builder.button(text="📉 Меньше (1-3)", callback_data="play_hl_low")
        builder.button(text="📈 Больше (4-6)", callback_data="play_hl_high")
        builder.adjust(2)
        await callback.message.edit_text(f"📊 **Больше или Меньше**\n\nСтавка: **${bet}**\nКуда упадет кость?", parse_mode="Markdown", reply_markup=builder.as_markup())
    elif game_code == "even":
        builder = InlineKeyboardBuilder()
        builder.button(text="🔴 Четное", callback_data="play_even_even")
        builder.button(text="🔵 Нечетное", callback_data="play_even_odd")
        builder.adjust(2)
        await callback.message.edit_text(f"🎲 **Четное или Нечетное**\n\nСтавка: **${bet}**\nСделай выбор:", parse_mode="Markdown", reply_markup=builder.as_markup())


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
    await callback.message.edit_text("✍️ **Введите вашу сумму ставки числом в чат:**\n(Минимум $1)", parse_mode="Markdown", reply_markup=builder.as_markup())


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


# --- ОБРАБОТЧИКИ ИГР ---
@dp.callback_query(F.data.startswith("play_guess_"))
async def play_guess(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    can_play, msg = check_access(user_id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    bet = user_bets.get(user_id, 50)
    user = get_user_data(user_id)

    if user["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    chosen_num = int(callback.data.split("_")[2])
    rig_mode = get_rig_mode(user_id, bet)

    if rig_mode == "win":
        secret_num = chosen_num
    elif rig_mode == "loss":
        other_nums = [n for n in range(1, 6) if n != chosen_num]
        secret_num = random.choice(other_nums)
    else:
        secret_num = random.randint(1, 5)

    if chosen_num == secret_num:
        win_amount = bet * 3
        user["balance"] += win_amount
        res_text = f"🎉 **ПОБЕДА!** Вы угадали число **{secret_num}**!\n💰 Выигрыш: **+${win_amount}**"
    else:
        user["balance"] -= bet
        res_text = f"💥 **ПРОИГРЫШ!** Выпало число **{secret_num}**.\n💸 Потеряно: **-${bet}**"

    save_db()
    res_text += f"\n\n💵 Ваш баланс: **${user['balance']}**"
    await callback.message.edit_text(res_text, parse_mode="Markdown", reply_markup=post_game_keyboard("guess", bet, user["balance"]))


@dp.callback_query(F.data.startswith("play_hl_"))
async def play_hl(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    can_play, msg = check_access(user_id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    bet = user_bets.get(user_id, 50)
    user = get_user_data(user_id)

    if user["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    choice = callback.data.split("_")[2]
    rig_mode = get_rig_mode(user_id, bet)

    if rig_mode == "win":
        dice = random.choice([1, 2, 3]) if choice == "low" else random.choice([4, 5, 6])
    elif rig_mode == "loss":
        dice = random.choice([4, 5, 6]) if choice == "low" else random.choice([1, 2, 3])
    else:
        dice = random.randint(1, 6)

    is_win = (choice == "low" and dice <= 3) or (choice == "high" and dice >= 4)

    if is_win:
        win_amount = bet
        user["balance"] += win_amount
        res_text = f"🎉 **ПОБЕДА!** Выпало число **{dice}**!\n💰 Выигрыш: **+${win_amount}**"
    else:
        user["balance"] -= bet
        res_text = f"💥 **ПРОИГРЫШ!** Выпало число **{dice}**.\n💸 Потеряно: **-${bet}**"

    save_db()
    res_text += f"\n\n💵 Ваш баланс: **${user['balance']}**"
    await callback.message.edit_text(res_text, parse_mode="Markdown", reply_markup=post_game_keyboard("hl", bet, user["balance"]))


@dp.callback_query(F.data.startswith("play_even_"))
async def play_even(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    can_play, msg = check_access(user_id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    bet = user_bets.get(user_id, 50)
    user = get_user_data(user_id)

    if user["balance"] < bet:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    choice = callback.data.split("_")[2]
    rig_mode = get_rig_mode(user_id, bet)

    if rig_mode == "win":
        dice = random.choice([2, 4, 6]) if choice == "even" else random.choice([1, 3, 5])
    elif rig_mode == "loss":
        dice = random.choice([1, 3, 5]) if choice == "even" else random.choice([2, 4, 6])
    else:
        dice = random.randint(1, 6)

    is_win = (choice == "even" and dice % 2 == 0) or (choice == "odd" and dice % 2 != 0)

    if is_win:
        win_amount = bet
        user["balance"] += win_amount
        res_text = f"🎉 **ПОБЕДА!** Выпало число **{dice}**!\n💰 Выигрыш: **+${win_amount}**"
    else:
        user["balance"] -= bet
        res_text = f"💥 **ПРОИГРЫШ!** Выпало число **{dice}**.\n💸 Потеряно: **-${bet}**"

    save_db()
    res_text += f"\n\n💵 Ваш баланс: **${user['balance']}**"
    await callback.message.edit_text(res_text, parse_mode="Markdown", reply_markup=post_game_keyboard("even", bet, user["balance"]))


# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_admin_panel(message)


async def show_admin_panel(target: types.Message | types.CallbackQuery):
    text = "🛠 **ПАНЕЛЬ АДМИНИСТРАТОРА LOMTIK GAME**\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"⚙️ **Авто-слив при ставке от:** `${auto_loss_limit}`\n\n"
    text += "📊 **СПИСОК ИГРОКОВ:**\n"
    if not users_db:
        text += "└ *Игроков пока нет*\n\n"
    else:
        for u_id, u_data in users_db.items():
            status_tag = ""
            if u_data.get("is_deleted"):
                status_tag = " ❌ [УДАЛЕН]"
            elif u_data.get("banned_until") and datetime.now() < u_data["banned_until"]:
                status_tag = " ⛔ [В БАНЕ]"
            wins = u_data.get("forced_wins", 0)
            losses = u_data.get("forced_losses", 0)
            text += (
                f"👤 **ID:** `{u_id}`{status_tag}\n"
                f" ├ 💵 Баланс: **${u_data['balance']}**\n"
                f" ├ 👑 Подкручено побед: **{wins}**\n"
                f" └ 😈 Подкручено сливов: **{losses}**\n\n"
            )

    text += "🎮 **УПРАВЛЕНИЕ ПОДКТРУТКОЙ:**\n"
    text += "• `/rig_win ID ИГР` — гарантированные победы\n"
    text += "• `/rig_loss ID ИГР` — гарантированные сливы\n\n"
    text += "💰 **УПРАВЛЕНИЕ БАЛАНСОМ:**\n"
    text += "• `/give ID СУММА` — выдать деньги\n"
    text += "• `/take ID СУММА` — забрать деньги\n"
    text += "• `/setlimit СУММА` — установить лимит авто-слива\n\n"
    text += "⛔ **БЛОКИРОВКИ И УДАЛЕНИЕ:**\n"
    text += "• `/ban ID МИНУТЫ` — забанить на время\n"
    text += "• `/unban ID` — разбанить игрока\n"
    text += "• `/delete_user ID` — полностью удалить профиль\n\n"
    text += "📢 **ОБЩИЕ КОМАНДЫ:**\n"
    text += "• `/bc ТЕКСТ` — сделать рассылку всем игрокам\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить список", callback_data="refresh_admin")

    if isinstance(target, types.Message):
        await target.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    else:
        try:
            await target.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
            await target.answer("Список обновлен!")
        except Exception:
            await target.answer("Данные уже актуальны!")


@dp.callback_query(F.data == "refresh_admin")
async def refresh_admin_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await show_admin_panel(callback)


@dp.message(Command("rig_win"))
async def set_rig_win(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, games_count = message.text.split()
        data = get_user_data(int(target_id))
        data["forced_wins"] = int(games_count)
        save_db()
        await message.answer(f"👑 Пользователь `{target_id}` **ВЫИГРАЕТ** следующие **{games_count}** игр!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/rig_win ID КОЛИЧЕСТВО_ИГР`", parse_mode="Markdown")


@dp.message(Command("rig_loss"))
@dp.message(Command("rig"))
async def set_rig_loss(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, games_count = message.text.split()
        data = get_user_data(int(target_id))
        data["forced_losses"] = int(games_count)
        save_db()
        await message.answer(f"😈 Пользователь `{target_id}` **ПРОИГРАЕТ** следующие **{games_count}** игр!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/rig_loss ID КОЛИЧЕСТВО_ИГР`", parse_mode="Markdown")


@dp.message(Command("give"))
async def give_money(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, amount = message.text.split()
        data = get_user_data(int(target_id))
        data["balance"] += int(amount)
        save_db()
        await message.answer(f"💰 Пользователю `{target_id}` выдано **${amount}**. Новый баланс: **${data['balance']}**", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/give ID СУММА`", parse_mode="Markdown")


@dp.message(Command("take"))
async def take_money(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, amount = message.text.split()
        data = get_user_data(int(target_id))
        data["balance"] = max(0, data["balance"] - int(amount))
        save_db()
        await message.answer(f"💸 У пользователя `{target_id}` забрано **${amount}**. Новый баланс: **${data['balance']}**", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/take ID СУММА`", parse_mode="Markdown")


@dp.message(Command("setlimit"))
async def set_limit(message: types.Message):
    global auto_loss_limit
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, amount = message.text.split()
        auto_loss_limit = int(amount)
        await message.answer(f"⚙️ Лимит авто-слива установлен на **${auto_loss_limit}**", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/setlimit СУММА`", parse_mode="Markdown")


@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, minutes = message.text.split()
        data = get_user_data(int(target_id))
        data["banned_until"] = datetime.now() + timedelta(minutes=int(minutes))
        save_db()
        try:
            await bot.send_message(int(target_id), f"⛔ **Вы получили временную блокировку в игре на {minutes} мин.**")
        except Exception:
            pass
        await message.answer(f"✅ Пользователь `{target_id}` заблокирован на **{minutes}** минут!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/ban ID МИНУТЫ`", parse_mode="Markdown")


@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id = message.text.split()
        data = get_user_data(int(target_id))
        data["banned_until"] = None
        data["is_deleted"] = False
        save_db()
        try:
            await bot.send_message(int(target_id), "✅ **Ваш аккаунт был разблокирован!**")
        except Exception:
            pass
        await message.answer(f"✅ Пользователь `{target_id}` успешно разбанен!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/unban ID`", parse_mode="Markdown")


@dp.message(Command("delete_user"))
async def delete_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id = message.text.split()
        data = get_user_data(int(target_id))
        data["is_deleted"] = True
        save_db()
        try:
            await bot.send_message(int(target_id), "❌ **Ваш аккаунт был удален из системы.**")
        except Exception:
            pass
        await message.answer(f"✅ Пользователь `{target_id}` успешно удален из системы!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Используйте: `/delete_user ID`", parse_mode="Markdown")


@dp.message(Command("bc"))
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/bc", "").strip()
    if not text:
        await message.answer("❌ Введите текст рассылки! Пример: `/bc Всем привет!`", parse_mode="Markdown")
        return
    count = 0
    for u_id in list(users_db.keys()):
        try:
            await bot.send_message(u_id, f"📢 **СООБЩЕНИЕ ОТ АДМИНИСТРАЦИИ:**\n\n{text}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Рассылка завершена! Отправлено пользователям: **{count}**", parse_mode="Markdown")


# --- ЗАПУСК ---
async def main():
    load_db()
    print("Бот успешно запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
