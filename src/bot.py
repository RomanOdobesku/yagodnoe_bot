import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from tortoise import Tortoise, fields, models
import os
import re
from src.logger import LOGGER

API_TOKEN = os.getenv('API_TOKEN')
ORGANIZER_USERNAMES = ['@roman_odobesku']

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


# -------- Tortoise ORM Model -------- #
class User(models.Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=100, unique=True)
    balance = fields.IntField(default=0)

    def __str__(self):
        return self.username


async def get_or_create_user(username):
    user, created = await User.get_or_create(username=username)
    return user


async def get_balance(username):
    user = await User.get_or_none(username=username)
    return user.balance if user else 0


async def update_balance(username, amount):
    if not isinstance(amount, int):
        raise ValueError("Amount must be an integer")
    user = await get_or_create_user(username)
    user.balance += amount
    await user.save()


# -------- BOT COMMANDS -------- #
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    username = f"@{message.from_user.username}"
    await get_or_create_user(username)
    await message.answer("Вы зарегистрированы!\nИспользуйте /balance чтобы проверить баланс")


@dp.message_handler(commands=['balance'])
async def cmd_balance(message: types.Message):
    username = f"@{message.from_user.username}"
    balance = await get_balance(username)
    await message.answer(f"Ваш баланс: {balance} жетонов.")


@dp.message_handler(commands=['transfer'])
async def cmd_transfer(message: types.Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.reply("Формат: /transfer @username количество")
        return
    to_user, amount_str = parts[1], parts[2]
    from_user = f"@{message.from_user.username}"

    if not re.match(r"^@\w+$", to_user):
        await message.reply("Неверный формат username.")
        return

    if not amount_str.isdigit():
        await message.reply("Количество должно быть положительным целым числом.")
        return

    amount = int(amount_str)
    if amount <= 0:
        await message.reply("Количество должно быть больше нуля.")
        return

    sender = await get_or_create_user(from_user)
    if sender.balance < amount:
        await message.reply("Недостаточно жетонов.")
        return

    await get_or_create_user(to_user)
    await update_balance(from_user, -amount)
    await update_balance(to_user, amount)

    await message.reply(f"Переведено {amount} жетонов {to_user} от {from_user}.")


# -------- ORGANIZER COMMANDS -------- #
def is_organizer(username):
    return f"@{username}" in ORGANIZER_USERNAMES


@dp.message_handler(commands=['addtokens'])
async def cmd_addtokens(message: types.Message):
    LOGGER.info('addtokens start')
    if not is_organizer(message.from_user.username):
        await message.reply("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.reply("Формат: /addtokens @username количество")
        return

    to_user, amount_str = parts[1], parts[2]
    if not re.match(r"^@\w+$", to_user):
        await message.reply("Неверный username.")
        return

    if not amount_str.isdigit():
        await message.reply("Количество должно быть положительным целым числом.")
        return

    amount = int(amount_str)
    if amount <= 0:
        await message.reply("Количество должно быть больше нуля.")
        return
    
    LOGGER.info(f'addtokens process user: {to_user}, amount: {amount}')

    await get_or_create_user(to_user)
    await update_balance(to_user, amount)
    await message.reply(f"Начислено {amount} жетонов для {to_user}.")


@dp.message_handler(commands=['removetokens'])
async def cmd_removetokens(message: types.Message):
    if not is_organizer(message.from_user.username):
        await message.reply("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.reply("Формат: /removetokens @username количество")
        return

    to_user, amount_str = parts[1], parts[2]
    if not re.match(r"^@\w+$", to_user):
        await message.reply("Неверный username.")
        return

    if not amount_str.isdigit():
        await message.reply("Количество должно быть положительным целым числом.")
        return

    amount = int(amount_str)
    LOGGER.info(f"removetokens amount: {amount}, amount_str: {amount_str}")
    if amount <= 0:
        await message.reply("Количество должно быть больше нуля.")
        return

    user = await get_or_create_user(to_user)
    if user.balance < amount:
        await message.reply(f"Нельзя списать больше, чем есть у участника. Участник имеет {user.balance} жетонов")
        return

    try:
        await update_balance(to_user, -amount)
        await message.reply(f"Списано {amount} жетонов у {to_user}.")
    except ValueError as e:
        await message.reply(str(e))


# -------- MAIN -------- #
async def on_startup(dp):
    await Tortoise.init(
        db_url=f"postgres://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
        modules={"models": [__name__]}
    )
    await Tortoise.generate_schemas()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
