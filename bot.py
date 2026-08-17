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
                    if u_data.get("last_bonus"):
                        u_data["last_bonus"] = datetime.fromisoformat(u_data["last_bonus"])
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
            if copy_data.get("last_bonus"):
                copy_data["last_bonus"] = copy_data["last_bonus"].isoformat()
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
            "xp": 0,
            "level": 1,
            "forced_losses": 0,
            "forced_wins": 0,
            "is_deleted": False,
            "banned_until": None,
            "last_bonus": None,
            "history": []
        }
        save_db()
    
    u = users_db[user_id]
    u.setdefault("forced_wins", 0)
    u.setdefault("forced_losses", 0)
    u.setdefault("xp", 0)
    u.setdefault("level", 1)
    u.setdefault("last_bonus", None)
    u.setdefault("history", [])
    return u


def log_game(user_id: int, game_name: str, bet: int, result: str, outcome_amount: int):
    user = get_user_data(user_id)
    time_str = datetime.now().strftime("%d.%m %H:%M")
    entry = {
        "time": time_str,
        "game": game_name,
        "bet": bet,
        "result": result,  # "WIN" или "LOSS"
        "amount": outcome_amount
    }
    user["history"].append(entry)
    if len(user["history"]) > 20:
        user["history"] = user["history"][-20:]
    save_db()


def add_xp(user_id: int, amount: int):
    user = get_user_data(user_id)
    user["xp"] += amount
    new_level = (user["xp"] // 100) + 1
    if new_level > user["level"]:
        user["level"] = new_level
        user["balance"] += new_level * 100
        return True, new_level
    return False, user["level"]


def check_access(user_id: int) -> tuple[bool, str]:
    user = get_user_data(user_id)
    if user.get("is_deleted"):
        return False, "❌ Вы были удалены из системы LOMTIK GAME."
    if user.get("banned_until"):
        now = datetime.now()
        if now < user["banned_until"]:
            remaining = user["banned_until"] - now
            minutes = int(remaining.total_seconds() // 60) + 1
            return False, f"⛔ **Вы заблокированы!**\nДо окончания бана осталось: **{minutes} мин.**"
        else:
            user["banned_until"] = None
            save_db()
    return True, ""


def get_status(user_id: int) -> str:
    user = get_user_data(user_id)
    lvl = user["level"]
    if lvl < 3:
        return f"🥉 Новичок (Ур. {lvl})"
    elif lvl < 7:
        return f"🥈 Опытный Игрок (Ур. {lvl})"
    elif lvl < 15:
        return f"🥇 Хайроллер (Ур. {lvl})"
    else:
        return f"💎 Легенда LOMTIK (Ур. {lvl})"


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
    builder.button(text="🎯 Угадай число (x3)", callback_data="game_guess")
    builder.button(text="📊 Больше / Меньше (x2)", callback_data="game_hl")
    builder.button(text="🎲 Чет / Нечет (x2)", callback_data="game_even")
    builder.button(text="🎁 Ежедневный бонус", callback_data="get_bonus")
    builder.button(text="💳 Профиль и Статистика", callback_data="check_balance")
    builder.adjust(1)
    return builder.as_markup()


def profile_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 История моих игр", callback_data="my_history_cb")
    builder.button(text="🔙 Главное меню", callback_data="main_menu")
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
    builder.button(text="🔄 Повторить", callback_data=f"setbet_{game_code}_{last_bet}")
    builder.button(text=f"✖️2️⃣ Х2 (${double_bet})", callback_data=f"setbet_{game_code}_{double_bet}")
    builder.button(text=f"🔥 Ва-Банк (${va_bank_bet})", callback_data=f"setbet_{game_code}_{va_bank_bet}")
    builder.button(text="🔙 В меню", callback_data="main_menu")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


# --- КОМАНДЫ И НАВИГАЦИЯ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    can_play, msg = check_access(user_id)
    if not can_play:
        await message.answer(msg, parse_mode="Markdown")
        return
    data = get_user_data(user_id)
    status = get_status(user_id)
    welcome_text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В LOMTIK GAME 2.0** ✨\n"
        "━━━━━━━ 🎰 ━━━━━━━\n\n"
        f"👤 **Игрок:** {message.from_user.first_name}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"🏆 **Ранг:** {status}\n"
        f"⭐ **Опыт:** {data['xp']} XP\n"
        f"💵 **Баланс:** ${data['balance']}\n\n"
        "🔥 **Выберите режим игры из меню ниже:**"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_keyboard())


@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    await callback.message.edit_text("🎰 **LOMTIK GAME — Главное меню**\n\nВыберите нужный раздел:", reply_markup=main_keyboard(), parse_mode="Markdown")


@dp.callback_query(F.data == "check_balance")
async def check_balance(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    can_play, msg = check_access(callback.from_user.id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    data = get_user_data(callback.from_user.id)
    status = get_status(callback.from_user.id)
    profile_text = (
        "👤 **ЛИЧНЫЙ КАБИНЕТ ИГРОКА**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 **Имя:** {callback.from_user.first_name}\n"
        f"🆔 **ID аккаунта:** `{callback.from_user.id}`\n"
        f"🏆 **Текущий ранг:** {status}\n"
        f"⭐ **Накопленный XP:** {data['xp']} XP\n"
        f"💵 **Доступный баланс:** ${data['balance']}\n\n"
        "📌 **ДОСТУПНЫЕ КОМАНДЫ ЧАТА:**\n"
        "• `/start` — Вызов главного меню\n"
        "• `/myhistory` — Просмотр личной истории игр"
    )
    await callback.message.edit_text(profile_text, parse_mode="Markdown", reply_markup=profile_keyboard())


@dp.message(Command("myhistory"))
@dp.callback_query(F.data == "my_history_cb")
async def show_my_history(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    can_play, msg = check_access(user_id)
    if not can_play:
        if isinstance(event, types.CallbackQuery):
            await event.answer(msg, show_alert=True)
        else:
            await event.answer(msg, parse_mode="Markdown")
        return

    data = get_user_data(user_id)
    history = data.get("history", [])

    if not history:
        text = "📜 **ЛИЧНАЯ ИСТОРИЯ ИГР**\n━━━━━━━━━━━━━━━━━━━━━\n\n*Вы еще не сыграли ни одной игры.*"
    else:
        text = "📜 **ЛИЧНАЯ ИСТОРИЯ ИГР (Последние 10)**\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for h in reversed(history[-10:]):
            tag = "✅ ВЫИГРЫШ" if h["result"] == "WIN" else "❌ ПРОИГРЫШ"
            sign = "+" if h["amount"] > 0 else ""
            text += f"🕒 `{h['time']}` | **{h['game']}**\n"
            text += f" └ Ставка: ${h['bet']} | Итог: **{tag} ({sign}${h['amount']})**\n\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад в профиль", callback_data="check_balance")

    if isinstance(event, types.Message):
        await event.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    else:
        await event.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "get_bonus")
async def get_daily_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    can_play, msg = check_access(user_id)
    if not can_play:
        await callback.answer(msg, show_alert=True)
        return
    data = get_user_data(user_id)
    now = datetime.now()
    if data["last_bonus"]:
        next_bonus = data["last_bonus"] + timedelta(hours=24)
        if now < next_bonus:
            remaining = next_bonus - now
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            await callback.answer(f"⏳ Следующий бонус будет доступен через {hours}ч {minutes}мин", show_alert=True)
            return

    bonus_amount = random.randint(150, 400)
    data["balance"] += bonus_amount
    data["last_bonus"] = now
    save_db()
    await callback.answer(f"🎁 Вы успешно получили ежедневный бонус: ${bonus_amount}!", show_alert=True)
    await check_balance(callback, None)


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
        await callback.message.edit_text(f"🎯 **Угадай число (1-5)**\n\nСтавка: **${bet}**\nВыбери число:", parse_mode="Markdown", reply_markup=builder.as_markup())
    elif game_code == "hl":
        builder = InlineKeyboardBuilder()
        builder.button(text="📉 Меньше (1-3)", callback_data="play_hl_low")
        builder.button(text="📈 Больше (4-6)", callback_data="play_hl_high")
        builder.adjust(2)
        await callback.message.edit_text(f"📊 **Больше или Меньше**\n\nСтавка: **${bet}**\nСделайте прогноз:", parse_mode="Markdown", reply_markup=builder.as_markup())
    elif game_code == "even":
        builder = InlineKeyboardBuilder()
        builder.button(text="🔴 Четное", callback_data="play_even_even")
        builder.button(text="🔵 Нечетное", callback_data="play_even_odd")
        builder.adjust(2)
        await callback.message.edit_text(f"🎲 **Четное или Нечетное**\n\nСтавка: **${bet}**\nСделайте выбор:", parse_mode="Markdown", reply_markup=builder.as_markup())


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
    await callback.message.edit_text("✍️ **Введите сумму ставки в чат:**\n(Минимум $1)", parse_mode="Markdown", reply_markup=builder.as_markup())


@dp.message(BetState.waiting_for_custom_bet)
async def process_custom_bet(message: types.Message, state: FSMContext):
    can_play, msg = check_access(message.from_user.id)
    if not can_play:
        await message.answer(msg, parse_mode="Markdown")
        return
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите корректное число!")
        return
    bet = int(message.text)
    if bet < 1:
        await message.answer("❌ Минимальная ставка — $1!")
        return
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if data["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: **${data['balance']}**", parse_mode="Markdown")
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
        await message.answer(f"🎯 **Угадай число**\n\nСтавка: **${bet}**\nВыбери число:", parse_mode="Markdown", reply_markup=builder.as_markup())
    elif game_code == "hl":
        builder = InlineKeyboardBuilder()
        builder.button(text="📉 Меньше (1-3)", callback_data="play_hl_low")
        builder.button(text="📈 Больше (4-6)", callback_data="play_hl_high")
        builder.adjust(2)
        await message.answer(f"📊 **Больше или Меньше**\n\nСтавка: **${bet}**\nСделай выбор:", parse_mode="Markdown", reply_markup=builder.as_markup())
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

    await callback.message.edit_text("🎲 *Бросаем кубик...*", parse_mode="Markdown")
    await asyncio.sleep(1.2)

    if rig_mode == "win":
        secret_num = chosen_num
    elif rig_mode == "loss":
        other_nums = [n for n in range(1, 6) if n != chosen_num]
        secret_num = random.choice(other_nums)
    else:
        secret_num = random.randint(1, 5)

    leveled_up, new_lvl = add_xp(user_id, 15)

    if chosen_num == secret_num:
        win_amount = bet * 3
        user["balance"] += win_amount
        log_game(user_id, "Угадай число", bet, "WIN", win_amount)
        res_text = f"🎉 **ПОБЕДА!** Выпало число **{secret_num}**!\n💰 Выигрыш: **+${win_amount}** (+15 XP)"
    else:
        user["balance"] -= bet
        log_game(user_id, "Угадай число", bet, "LOSS", -bet)
        res_text = f"💥 **ПРОИГРЫШ!** Выпало число **{secret_num}**.\n💸 Потеряно: **-${bet}** (+15 XP)"

    if leveled_up:
        res_text += f"\n\n🎊 **ПОЗДРАВЛЯЕМ! Новый уровень: {new_lvl}!**"

    save_db()
    res_text += f"\n\n💵 Баланс: **${user['balance']}**"
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

    await callback.message.edit_text("📊 *Крутим кости...*", parse_mode="Markdown")
    await asyncio.sleep(1.2)

    if rig_mode == "win":
        dice = random.choice([1, 2, 3]) if choice == "low" else random.choice([4, 5, 6])
    elif rig_mode == "loss":
        dice = random.choice([4, 5, 6]) if choice == "low" else random.choice([1, 2, 3])
    else:
        dice = random.randint(1, 6)

    is_win = (choice == "low" and dice <= 3) or (choice == "high" and dice >= 4)
    leveled_up, new_lvl = add_xp(user_id, 10)

    if is_win:
        win_amount = bet
        user["balance"] += win_amount
        log_game(user_id, "Больше/Меньше", bet, "WIN", win_amount)
        res_text = f"🎉 **ПОБЕДА!** Выпало число **{dice}**!\n💰 Выигрыш: **+${win_amount}** (+10 XP)"
    else:
        user["balance"] -= bet
        log_game(user_id, "Больше/Меньше", bet, "LOSS", -bet)
        res_text = f"💥 **ПРОИГРЫШ!** Выпало число **{dice}**.\n💸 Потеряно: **-${bet}** (+10 XP)"

    if leveled_up:
        res_text += f"\n\n🎊 **ПОЗДРАВЛЯЕМ! Новый уровень: {new_lvl}!**"

    save_db()
    res_text += f"\n\n💵 Баланс: **${user['balance']}**"
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

    await callback.message.edit_text("🎲 *Бросаем рулетку...*", parse_mode="Markdown")
    await asyncio.sleep(1.2)

    if rig_mode == "win":
        dice = random.choice([2, 4, 6]) if choice == "even" else random.choice([1, 3, 5])
    elif rig_mode == "loss":
        dice = random.choice([1, 3, 5]) if choice == "even" else random.choice([2, 4, 6])
    else:
        dice = random.randint(1, 6)

    is_win = (choice == "even" and dice % 2 == 0) or (choice == "odd" and dice % 2 != 0)
    leveled_up, new_lvl = add_xp(user_id, 10)

    if is_win:
        win_amount = bet
        user["balance"] += win_amount
        log_game(user_id, "Чет/Нечет", bet, "WIN", win_amount)
        res_text = f"🎉 **ПОБЕДА!** Выпало число **{dice}**!\n💰 Выигрыш: **+${win_amount}** (+10 XP)"
    else:
        user["balance"] -= bet
        log_game(user_id, "Чет/Нечет", bet, "LOSS", -bet)
        res_text = f"💥 **ПРОИГРЫШ!** Выпало число **{dice}**.\n💸 Потеряно: **-${bet}** (+10 XP)"

    if leveled_up:
        res_text += f"\n\n🎊 **ПОЗДРАВЛЯЕМ! Новый уровень: {new_lvl}!**"

    save_db()
    res_text += f"\n\n💵 Баланс: **${user['balance']}**"
    await callback.message.edit_text(res_text, parse_mode="Markdown", reply_markup=post_game_keyboard("even", bet, user["balance"]))


# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_admin_panel(message)


async def show_admin_panel(target: types.Message | types.CallbackQuery):
    text = "🛠 **ПАНЕЛЬ АДМИНИСТРАТОРА LOMTIK GAME 2.0**\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
                f" ├ 💵 Баланс: **${u_data['balance']}** (Ур. {u_data.get('level', 1)})\n"
                f" ├ 👑 Побед подкручено: **{wins}**\n"
                f" └ 😈 Сливов подкручено: **{losses}**\n\n"
            )

    text += "🎮 **УПРАВЛЕНИЕ ПОДКТРУТКОЙ:**\n"
    text += "• `/rig_win ID ИГР` — подкрутить победы\n"
    text += "• `/rig_loss ID ИГР` — подкрутить сливы\n\n"
    text += "📜 **ПРОСМОТР ИСТОРИИ:**\n"
    text += "• `/history ID` — смотреть историю игрока\n\n"
    text += "💰 **УПРАВЛЕНИЕ БАЛАНСОМ:**\n"
    text += "• `/give ID СУММА` — выдать баланс\n"
    text += "• `/take ID СУММА` — списать баланс\n"
    text += "• `/setlimit СУММА` — измерить порог авто-слива\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить данные", callback_data="refresh_admin")

    if isinstance(target, types.Message):
        await target.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    else:
        try:
            await target.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
            await target.answer("Данные обновлены!")
        except Exception:
            await target.answer("Все актуально!")


@dp.callback_query(F.data == "refresh_admin")
async def refresh_admin_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await show_admin_panel(callback)


@dp.message(Command("history"))
async def show_user_history(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id = message.text.split()
        data = get_user_data(int(target_id))
        history = data.get("history", [])
        
        if not history:
            await message.answer(f"📜 У пользователя `{target_id}` пока нет сыгранных игр.", parse_mode="Markdown")
            return

        msg_text = f"📜 **История игр (ID: `{target_id}`):**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for h in reversed(history[-10:]):
            tag = "✅ WIN" if h["result"] == "WIN" else "❌ LOSS"
            sign = "+" if h["amount"] > 0 else ""
            msg_text += f"🕒 `{h['time']}` | {h['game']}\n"
            msg_text += f" └ Ставка: ${h['bet']} | Результат: **{tag} ({sign}${h['amount']})**\n\n"

        await message.answer(msg_text, parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Команда: `/history ID`", parse_mode="Markdown")


@dp.message(Command("rig_win"))
async def set_rig_win(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, games_count = message.text.split()
        data = get_user_data(int(target_id))
        data["forced_wins"] = int(games_count)
        save_db()
        await message.answer(f"👑 Игрок `{target_id}` **ВЫИГРАЕТ** {games_count} игр!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Команда: `/rig_win ID КОЛИЧЕСТВО`", parse_mode="Markdown")


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
        await message.answer(f"😈 Игрок `{target_id}` **ПРОИГРАЕТ** {games_count} игр!", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Команда: `/rig_loss ID КОЛИЧЕСТВО`", parse_mode="Markdown")


@dp.message(Command("give"))
async def give_money(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, amount = message.text.split()
        data = get_user_data(int(target_id))
        data["balance"] += int(amount)
        save_db()
        await message.answer(f"💰 Игроку `{target_id}` начислено **${amount}**", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Команда: `/give ID СУММА`", parse_mode="Markdown")


@dp.message(Command("take"))
async def take_money(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, target_id, amount = message.text.split()
        data = get_user_data(int(target_id))
        data["balance"] = max(0, data["balance"] - int(amount))
        save_db()
        await message.answer(f"💸 У игрока `{target_id}` списано **${amount}**", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Команда: `/take ID СУММА`", parse_mode="Markdown")


@dp.message(Command("setlimit"))
async def set_limit(message: types.Message):
    global auto_loss_limit
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, amount = message.text.split()
        auto_loss_limit = int(amount)
        await message.answer(f"⚙️ Лимит авто-слива установлен: **${auto_loss_limit}**", parse_mode="Markdown")
    except Exception:
        await message.answer("❌ Команда: `/setlimit СУММА`", parse_mode="Markdown")


# --- ЗАПУСК ---
async def main():
    load_db()
    print("Бот LOMTIK GAME 2.0 успешно запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
