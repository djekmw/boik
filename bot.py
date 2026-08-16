import random
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Токен вашего бота
TOKEN = "8949176656:AAHWimiNzkL4gN4ZxXrjkHav5V3y5DPglM8"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище балансов и ставок пользователей (в памяти)
users_db = {}
user_bets = {}

def get_user_data(user_id: int):
    """Инициализация или получение данных пользователя."""
    if user_id not in users_db:
        users_db[user_id] = {"balance": 1000}
    return users_db[user_id]

# Главное меню
def main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Угадай число (1-5)", callback_data="game_guess")
    builder.button(text="📊 Больше / Меньше", callback_data="game_hl")
    builder.button(text="🎲 Чет / Нечет", callback_data="game_even")
    builder.button(text="💰 Мой баланс", callback_data="check_balance")
    builder.adjust(1)
    return builder.as_markup()

# Клавиатура выбора ставки
def bet_keyboard(game_code: str):
    builder = InlineKeyboardBuilder()
    for bet in [50, 100, 250, 500]:
        builder.button(text=f"${bet}", callback_data=f"setbet_{game_code}_{bet}")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    data = get_user_data(message.from_user.id)
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Добро пожаловать в игрового бота.\n\n"
        f"💵 Твой баланс: **${data['balance']}**\n"
        f"Выбери игру:",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

# --- КОМАНДА АДМИНА ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ---
@dp.message(Command("admin"))
async def admin_stats(message: types.Message):
    if not users_db:
        await message.answer("Пока никто не играл и не запускал бота.")
        return

    text = "📊 **Список игроков и балансы:**\n\n"
    for user_id, data in users_db.items():
        text += f"👤 ID: `{user_id}` | Баланс: **${data.get('balance', 0)}**\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выбери игру:", reply_markup=main_keyboard())

@dp.callback_query(F.data == "check_balance")
async def check_balance(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    await callback.answer(f"Твой баланс: ${data['balance']}", show_alert=True)

# --- ВЫБОР СТАВКИ ---
@dp.callback_query(F.data.startswith("game_"))
async def choose_bet(callback: types.CallbackQuery):
    game_code = callback.data.split("_")[1]
    await callback.message.edit_text(
        "Выбери сумму ставки:", reply_markup=bet_keyboard(game_code)
    )

# --- ИГРА 1: УГАДАЙ ЧИСЛО ---
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
    
    await callback.message.edit_text(
        f"Ставка: **${bet}**\nУгадай число от 1 до 5:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(),
    )

@dp.callback_query(F.data.startswith("play_guess_"))
async def guess_game_result(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    bet = user_bets.get(user_id, 50)
    user_choice = int(callback.data.split("_")[2])
    secret_num = random.randint(1, 5)

    if user_choice == secret_num:
        win = int(bet * 3)
        data["balance"] += win - bet
        res_text = f"🎉 **Победа!** Выпало число {secret_num}.\nТвой выигрыш: **+${win}**"
    else:
        data["balance"] -= bet
        res_text = f"❌ **Проигрыш!** Было загадано число {secret_num}."

    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.edit_text(
        res_text, parse_mode="Markdown", reply_markup=main_keyboard()
    )

# --- ИГРА 2: БОЛЬШЕ / МЕНЬШЕ ---
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
    
    await callback.message.edit_text(
        f"Ставка: **${bet}**\nБросаем кость (1-6). Какое число выпадет?",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(),
    )

@dp.callback_query(F.data.startswith("play_hl_"))
async def hl_game_result(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    bet = user_bets.get(user_id, 50)
    choice = callback.data.split("_")[2]

    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(2)
    dice_val = dice_msg.dice.value

    is_win = (choice == "low" and dice_val <= 3) or (
        choice == "high" and dice_val >= 4
    )

    if is_win:
        win = int(bet * 1.8)
        data["balance"] += win - bet
        res_text = f"🎉 **Выигрыш!** Выпало {dice_val}.\nТвой плюс: **+${win}**"
    else:
        data["balance"] -= bet
        res_text = f"❌ **Проигрыш!** Выпало {dice_val}."

    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.answer(
        res_text, parse_mode="Markdown", reply_markup=main_keyboard()
    )

# --- ИГРА 3: ЧЕТ / НЕЧЕТ ---
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
    
    await callback.message.edit_text(
        f"Ставка: **${bet}**\nЧетное или нечетное?",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(),
    )

@dp.callback_query(F.data.startswith("play_even_"))
async def even_game_result(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    bet = user_bets.get(user_id, 50)
    choice = callback.data.split("_")[2]

    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(2)
    dice_val = dice_msg.dice.value

    is_even = dice_val % 2 == 0
    is_win = (choice == "even" and is_even) or (
        choice == "odd" and not is_even
    )

    if is_win:
        win = int(bet * 1.8)
        data["balance"] += win - bet
        res_text = (
            f"🎉 **Отлично!** Выпало {dice_val}.\nТвой выигрыш: **+${win}**"
        )
    else:
        data["balance"] -= bet
        res_text = f"❌ **Не угадал!** Выпало {dice_val}."

    res_text += f"\n\n💵 Баланс: **${data['balance']}**"
    await callback.message.answer(
        res_text, parse_mode="Markdown", reply_markup=main_keyboard()
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
