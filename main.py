import csv
import http.client
import json
import gettext
import datetime
import asyncio
import tempfile
from gettext import gettext as _
import sys
from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, \
    CallbackQuery, Message
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher import storage
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.bot import Bot
from aiogram.utils import executor
import os
import pandas as pd
from coinbase_commerce.client import Client
from aiogram.contrib.fsm_storage.memory import MemoryStorage

data = None
API_KEY = ""  # HERE COINBASE PAY API KEY
client = Client(api_key=API_KEY)

bot = Bot(token='')  # HERE BOT TOKEN
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
Dispatcher.set_current(dp)


class Form(StatesGroup):
    charging = State()
    search_string = State()
    searching = State()
    num_rows = State()
    purchased = State()
    start = State()
    set_admin = State()
    offer = State()
    announcement = State()
    offer_sent = State()
    add_new_prices = State()
    modify_prices = State()
    delete_prices = State()


async def profile(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    user_balance = 0
    user_sub = "False"

    # Read the CSV file into a DataFrame
    df = pd.read_csv("users.csv")

    # Check if the user already exists in the DataFrame
    user_exists = df['user_id'].eq(user_id).any()

    if not user_exists:
        # If the user does not exist, create a new entry in the DataFrame
        df = df.append({'user_id': user_id, 'user_balance': '0', 'user_sub': "False", 'language': "en"},
                       ignore_index=True)
        # Save the DataFrame to the CSV file
        df.to_csv("users.csv", index=False)
    else:
        # Retrieve the user's balance and subscription status
        user_balance = df.loc[df['user_id'] == user_id, 'user_balance'].item()
        user_sub = df.loc[df['user_id'] == user_id, 'user_sub'].item()
    top_up_button = InlineKeyboardButton("Top Up", callback_data="top_up")
    markup = InlineKeyboardMarkup().add(top_up_button)
    await message.answer(
        _("*👤 Name:*") + " " + user_name + "\n" + _("*💵 Balance:*") + " " + str(
            round(user_balance, 2)) + "$" + "\n" + _(
            "*🚀 Subscription:*") + " " + str(user_sub), parse_mode='Markdown', reply_markup=markup)


@dp.callback_query_handler(lambda c: c.data == "top_up")
async def top_up(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await Form.charging.set()
    print(await state.get_state())
    await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id,
                                        reply_markup=None)
    await bot.send_message(chat_id=callback_query.from_user.id, text=_('Please insert the amount you want to charge:'))

    # Register a message handler to handle the user's response
    @dp.message_handler(state=Form.charging)
    async def process_amount(message: types.Message, state: FSMContext):
        print(await state.get_state())
        amount = float(message.text)
        checkout_info = {
            "name": 'Top Up',
            "description": 'Top up your account',
            "pricing_type": 'fixed_price',
            "local_price": {
                "amount": amount,
                "currency": "USD"
            },
        }
        charge = client.charge.create(**checkout_info)
        payment_url = charge.hosted_url
        global charge_id
        charge_id = payment_url.split('/')[4]
        print("*The charge_id for the user has been created!:*", charge_id)
        # send payment URL to user
        keyboard = InlineKeyboardMarkup()
        pay_button = InlineKeyboardButton(_('Pay'), url=payment_url)
        check_payment_button = InlineKeyboardButton(_('Check Payment'), callback_data='check_payment')
        back = InlineKeyboardButton(_('Back'), callback_data='back')
        keyboard.add(pay_button, check_payment_button)
        keyboard.add(back)
        await bot.send_message(chat_id=message.chat.id,
                               text=_("*Click the button Pay below to top up your account 💵*"), parse_mode='Markdown',
                               reply_markup=keyboard)
        await state.finish()
        print(await state.get_state())


@dp.callback_query_handler(lambda c: c.data == "back")
async def back(callback_query: types.CallbackQuery, state: FSMContext):
    await start(callback_query.message, state)
    try:
        await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id,
                                            reply_markup=None)
    except:
        print("No reply markup to delete")


@dp.callback_query_handler(lambda c: c.data == "check_payment")
async def check_payment(callback_query: types.CallbackQuery):
    conn = http.client.HTTPSConnection("api.commerce.coinbase.com")
    payload = ''
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-CC-Api-Key': 'fb8f8d40-5936-4578-b3c8-b80a94eaacaa'
    }
    conn.request("GET", f"/charges/{charge_id}", payload, headers)
    res = conn.getresponse()
    data = res.read()
    response_json = json.loads(data)
    status = (response_json['data']['timeline'][0]['status'])

    if status == "NEW":
        await bot.send_message(chat_id=callback_query.from_user.id, text=_("*Waiting for payment 🟡*"),
                               parse_mode='Markdown', )
    elif status == "PENDING":
        await bot.send_message(chat_id=callback_query.from_user.id,
                               text=_("*Payment received, but need confirmations 🟡*"), parse_mode='Markdown', )
        print("Payment received, but need confirmations 🟡")
    elif status == "COMPLETED":
        await bot.send_message(chat_id=callback_query.from_user.id, text=_("*Payment completed ✅*"),
                               parse_mode='Markdown', )
        # Update the user's balance in the CSV file
        df = pd.read_csv("users.csv")
        user_balance = df.loc[df['user_id'] == callback_query.from_user.id, 'user_balance'].item()
        new_balance = user_balance + float(response_json['data']['pricing']['local']['amount'])
        new_balance = round(new_balance, 2)
        df.loc[df['user_id'] == callback_query.from_user.id, 'user_balance'] = new_balance
        await bot.send_message(chat_id=callback_query.from_user.id,
                               text=_(f"Thanks for purchase! Your new balance is {new_balance} 💵"))
        df.to_csv("users.csv", index=False)
        print("Payment completed ✅")

    else:
        await bot.send_message(chat_id=callback_query.from_user.id, text=_("*Payment failed*"), parse_mode='Markdown', )


async def subscription(message, state: FSMContext):
    with open("users.csv", "r") as file:
        reader = csv.reader(file)
        for row in reader:
            if row[0] == str(message.from_user.id):
                user_sub = row[2]
                user_balance = float(row[1])
                break
    if user_sub == "True":
        await message.answer(_("*You already have a subscription*"), parse_mode='Markdown', )
    else:
        keyboard = InlineKeyboardMarkup()
        yes_button = InlineKeyboardButton(_("Yes"), callback_data="subscribe_yes")
        no_button = InlineKeyboardButton(_("No"), callback_data="subscribe_no")
        top_up_button = InlineKeyboardButton(_("Top Up"), callback_data="top_up")
        keyboard.add(yes_button, no_button)
        keyboard.add(top_up_button)
        await message.answer(_("Do you want to subscribe for 10$?"), reply_markup=keyboard)
    await start(message, state)


@dp.callback_query_handler(lambda c: c.data == "subscribe_yes")
async def process_callback_subscribe_yes(callback_query):
    user_id = callback_query.from_user.id
    with open("users.csv", "r") as file:
        reader = csv.reader(file)
        data = list(reader)
        for i, row in enumerate(data):
            if row[0] == str(user_id):
                if float(row[1]) < 10:
                    await callback_query.answer(_("*You don't have enough balance to subscribe*"),
                                                parse_mode='Markdown', )
                    menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
                    menu_keyboard.add(KeyboardButton(_("⬅️ Back")), KeyboardButton(_("Profile 👤")))

                    await bot.send_message(chat_id=callback_query.from_user.id,
                                           text=_(f"Your balance is {row[1]}$"),
                                           reply_markup=menu_keyboard)
                else:
                    row[1] = str(float(row[1]) - 10)
                    row[2] = "True"
                    data[i] = row
                    with open("users.csv", "w", newline='') as file:
                        writer = csv.writer(file)
                        writer.writerows(data)
                    keyboard = InlineKeyboardMarkup()
                    await bot.edit_message_text(chat_id=callback_query.message.chat.id,
                                                message_id=callback_query.message.message_id,
                                                text=_("*You have successfully subscribed*"), parse_mode='Markdown',
                                                reply_markup=keyboard)
                    print("An user subscribed")


@dp.callback_query_handler(lambda c: c.data == "subscribe_no")
async def process_callback_subscribe_no(callback_query):
    await callback_query.answer(_("You have not subscribed"))


counter = 1


@dp.callback_query_handler(lambda c: c.data == "back_getrow", state="*")
async def back_getrow(callback_query: types.CallbackQuery, state: FSMContext):
    await start(callback_query.message, state)


async def get_rows(message, state: FSMContext):
    current_loop = asyncio.get_event_loop()
    asyncio.run_coroutine_threadsafe(get_rowss(message, state), current_loop)

async def get_rowss(message, state: FSMContext):
    global search_string, counter, data, half_rows
    with open("users.csv", "r") as file:
        reader = csv.reader(file)
        for row in reader:
            if row[0] == str(message.from_user.id):
                user_sub = row[2]
                break
        if user_sub == "True":

            keyboard = InlineKeyboardMarkup()
            back_getrow = InlineKeyboardButton('Back', callback_data='back_getrow')
            keyboard.add(back_getrow)
            # state = none before clicking it
            await bot.send_message(chat_id=message.chat.id, text=_('*Please enter the string to search for: 🔎*'),
                                   parse_mode='Markdown',
                                   reply_markup=keyboard)
            await Form.searching.set()

            @dp.message_handler(state=Form.searching)
            async def process_searching(message: types.Message, state: FSMContext):
                global available_rows, half_rows, search_string, data, probab_element
                search_string = message.text
                await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=message.message_id - 1,
                                                    reply_markup=None)
                await bot.send_message(chat_id=message.chat.id, text=_("*Searching... 🔎, this may take 3 to 5 minutes*"),
                                       parse_mode='Markdown', )

                with open("list.txt", "r") as data:
                    try:
                        data = data.readlines()
                    except ValueError as e:
                        raise Exception('Invalid json from file {}: {}'.format(json_file, e)) from e
                available_rows = []
                for row in data:
                    try:
                        row_elements = row.split(":")
                        if len(row_elements) < 2:
                            continue
                        if search_string in row_elements[1]:
                            available_rows.append(row)
                    except IndexError:
                        continue

                if len(available_rows) < 2:
                    await message.answer(_("No results found for the string entered"))
                    await state.finish()
                    await get_rows(message, state)
                else:
                    df = pd.read_csv("prices.csv")
                    probab_element = df[df['query'] == (search_string)]
                    available_rows = []
                    for row in data:
                        try:
                            if search_string in row.split(":")[1]:
                                available_rows.append(row)
                        except IndexError:
                            continue
                    if len(available_rows) > 2:
                        half_rows = len(available_rows) // 2
                        menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                        menu_keyboard.add(KeyboardButton(f"{half_rows}"), KeyboardButton(f"{len(available_rows)}"))
                        menu_keyboard.add(KeyboardButton("⬅️ Back"))
                        await bot.send_message(chat_id=message.chat.id,
                                               text=_("*Occurrencies for*") + " ' " + search_string + " '  :  " + str(
                                                   len(available_rows)) + "\n" + _(
                                                   "*Choose if you want to buy Half or All of them*"),
                                               parse_mode='Markdown',
                                               reply_markup=menu_keyboard)

                        await Form.num_rows.set()
                    else:
                        await state.finish()
                        print(len(available_rows))
                        print(await state.get_state())

                    @dp.message_handler(state=Form.searching)
                    async def process_searching_again(message: types.Message, state: FSMContext):
                        await state.finish()
                        await get_rows(message, state)
                print(len(available_rows))
                print(await state.get_state())

            @dp.message_handler(state=Form.num_rows)
            async def process_num_rows(message: types.Message, state: FSMContext):
                global search_string, counter, data, half_rows, available_rows, selected_rows, price
                if message.text != "⬅️ Back":
                    num_rows = int(message.text)
                    # print(len(available_rows))
                    if num_rows not in [len(available_rows) // 2, len(available_rows)]:
                        await message.answer(_("*You can only select half or all of the available rows, please try again*"),
                                             parse_mode='Markdown', )
                        await get_rows(message, state)
                        return
                    selected_rows = []
                    for row in data:
                        try:
                            if search_string in row.split(":")[1]:
                                selected_rows.append(row)
                        except:
                            pass
                        if len(selected_rows) == num_rows:
                            break
                    df = pd.read_csv("prices.csv")
                    price = df[df['query'].apply(lambda x: x in search_string)]['price']
                    if (len(price) > 0):
                        for i in price:
                            price = i
                        price = price * len(selected_rows)
                        price = round(price, 2)
                        Ask = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                        Ask.add(KeyboardButton(_("Accept")), KeyboardButton(_("Decline")), KeyboardButton(_("Home")))
                        await bot.send_message(chat_id=message.chat.id,
                                               text=_("Price for") + " " + str(len(selected_rows)) + _(
                                                   " lines of") + " " + search_string + ": " + str(price) + "$",
                                               reply_markup=Ask)
                        await Form.purchased.set()
                    else:
                        ask = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                        ask.add(KeyboardButton(_("Make an offer")), KeyboardButton(_("Decline")))
                        ask.add(KeyboardButton(_("Home")))
                        await message.answer(_("*No price has been set for this query, please make an offer or decline*"),
                                             parse_mode='Markdown',
                                             reply_markup=ask)
                        await state.finish()
                        await Form.offer.set()
                else:
                    await start(message, state)

            @dp.message_handler(state=Form.offer)
            async def process_offer(message: types.Message, state: FSMContext):
                global search_string, counter, data, half_rows, available_rows, selected_rows, price
                if message.text == _("Make an offer"):
                    await message.answer(_("*Please enter the amount you want to offer*"), parse_mode='Markdown', )
                    await Form.offer_sent.set()
                elif message.text == _("Decline "):
                    await message.answer(_("You have declined the offer "))
                    await state.finish()
                    await get_rows(message, state)
                else:
                    await state.finish()
                    await start(message, state)

            @dp.message_handler(state=Form.offer_sent)
            async def process_offer_sent(message: types.Message, state: FSMContext):
                await bot.send_message(chat_id=message.chat.id,
                                       text=_(
                                           "*The request has been sent! You will recieve a message as soon as the owner replies!*"),
                                       parse_mode='Markdown', )
                for i in admin_ids:
                    await bot.send_message(chat_id=i,
                                           text=f"*Required a {float(message.text)}$ offer for {len(selected_rows)} lines of {search_string} by @{message.chat.username}*",
                                           parse_mode='Markdown', )
                await state.finish()
                await start(message, state)

            @dp.message_handler(state=Form.purchased)
            async def process_purchased(message: types.Message, state: FSMContext):
                global search_string, counter, data, half_rows, available_rows, selected_rows, price
                print(await state.get_state())
                await state.finish()
                if message.text == _("Accept"):
                    df = pd.read_csv("users.csv")
                    user_index = df.index[df['user_id'] == message.chat.id].tolist()[0]
                    if df.at[user_index, 'user_balance'] >= price:
                        df.at[user_index, 'user_balance'] -= price
                        df.to_csv("users.csv", index=False)
                        with open(f"{search_string}_{counter}.txt", "w", errors='ignore') as f:
                            f.write("".join(selected_rows))
                        await bot.send_document(chat_id=message.chat.id,
                                                document=open(f"{search_string}_{counter}.txt", 'rb'))
                        os.remove(f"{search_string}_{counter}.txt")
                        remaining_data = [row for row in data if row not in selected_rows]
                        with open("list.txt", "w", errors='ignore') as f:
                            f.writelines(remaining_data)
                        await message.answer(_("Thank you for your purchase!"))
                        tr = pd.read_csv("transaction.csv")
                        tr.append({"user_id": message.chat.id, "query": search_string, "price": price}, ignore_index=True)
                        tr.to_csv("transaction.csv", index=False)
                        counter += 1
                        f.close()
                        with open("sold.txt", "r", errors='ignore') as s:
                            sold = s.readline()
                        s.close()
                        sold = int(sold) + len(selected_rows)
                        with open("sold.txt", "w", errors='ignore') as f:
                            f.write(str(sold))
                        f.close()
                    else:
                        await bot.send_message(chat_id=message.chat.id, text="No funds.")
                    await start(message, state)
                elif message.text == _("Decline"):
                    await message.answer(_("Thank you for your time!"))
                    await start(message, state)
                elif message.text == _("Home"):
                    await start(message, state)
                else:
                    await message.answer(_("Please select one of the options"))
                    await get_rows(message, state)
        else:
            await message.answer(_("You have to subscribe to get access to the bot"))


@dp.message_handler(commands=['admin'])
async def admin_menu(message: types.Message):
    global admin_ids
    admins_df = pd.read_csv("admins.csv")
    admin_ids = set(admins_df["user_id"])
    # Check if the user is an admin
    if message.from_user.id in admin_ids:
        # Create the admin menu keyboard
        announcement = KeyboardButton("Announcement 📣")
        set_price_button = KeyboardButton("Set Price 📉")
        stats_button = KeyboardButton("Stats 👤")
        upgrade_list = KeyboardButton("Upgrade List 🚀")
        set_admin = KeyboardButton("Set Admin 🔐")
        back = KeyboardButton("⬅️ Back")
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Set Price 📉"), KeyboardButton("Announcement 📣"))
        markup.add(KeyboardButton("Stats 👤"), KeyboardButton("Set Admin 🔐"), KeyboardButton("Upgrade List 🚀"))
        markup.add(KeyboardButton("⬅️ Back"))

        # Send the admin menu to the user
        await bot.send_message(chat_id=message.from_user.id, text="Admin Menu:", reply_markup=markup)
    else:
        # Send a message to the user that they are not an admin
        await bot.send_message(chat_id=message.from_user.id, text="You are not an admin.")


last_announcement = None


@dp.message_handler(lambda message: message.text == "Announcement 📣")
async def announcement(message: types.Message):
    global last_announcement
    if message.chat.id in admin_ids:
        back = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        back.add(KeyboardButton("⬅️ Back"))
        back.add(KeyboardButton("❌ Cancel Previous Announcement!"))
        await message.reply("Insert the text of the announcement:", reply_markup=back)
        await Form.announcement.set()
    else:
        await message.reply("Not something you are allowed to do.")


@dp.message_handler(lambda message: message.text == "Set Price 📉")
async def set_price(message: types.Message):
    if message.chat.id in admin_ids:
        back = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        back.add(KeyboardButton("Display Prices 📊"), KeyboardButton("Add new prices 📌"))
        back.add(KeyboardButton("Delete Prices ❌"), KeyboardButton("Modify Prices 📝"))
        back.add(KeyboardButton("⬅️ Back"))
        await bot.send_message(chat_id=message.chat.id, text="What do you want to do?", reply_markup=back)
    else:
        await message.reply("Not something you are allowed to do.")


@dp.message_handler(lambda message: message.text == "Display Prices 📊")
async def prices(message: types.Message):
    df = pd.read_csv("prices.csv")
    prices_text = _("Prices: 💵 ") + "\n"
    for i in range(len(df)):
        prices_text += f"● {df['query'][i].capitalize()} ➡️ {df['price'][i]}$\n"
    await bot.send_message(chat_id=message.from_user.id, text=prices_text)
    await set_price(message)


@dp.message_handler(lambda message: message.text == "Add new prices 📌")
async def set_new_prices(message: types.Message):
    if message.chat.id in admin_ids:
        back = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        back.add(KeyboardButton("⬅️ Back"))
        await message.reply("Add the new prices following this format\nDO NOT include the $ sign:\n"
                            "query1,price1\n"
                            "query2,price2\n"
                            "query3,price3\n", reply_markup=back)
        await Form.add_new_prices.set()
    else:
        await message.reply("Not something you are allowed to do.")


@dp.message_handler(state=Form.add_new_prices)
async def add_new_prices(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Back":
        await set_price(message)
        await state.finish()
    else:
        prices = message.text.split("\n")
        df = pd.read_csv("prices.csv")
        for price in prices:
            query, price = price.split(",")
            df = df.append({"query": query, "price": price}, ignore_index=True)
        df.to_csv("prices.csv", index=False)
        await message.reply("Prices added successfully!")
        await set_price(message)
        await state.finish()


@dp.message_handler(lambda message: message.text == "Delete Prices ❌")
async def delete_prices(message: types.Message):
    if message.chat.id in admin_ids:
        back = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        back.add(KeyboardButton("⬅️ Back"))
        await message.reply(
            "Insert the queries you want to delete in the following format\nDO NOT include the $ sign:\n"
            "query1\n"
            "query2\n"
            "query3\n", reply_markup=back)
        await Form.delete_prices.set()
    else:
        await message.reply("Not something you are allowed to do.")


@dp.message_handler(state=Form.delete_prices)
async def delete_prices(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Back":
        await set_price(message)
        await state.finish()
    else:
        queries = message.text.split("\n")
        df = pd.read_csv("prices.csv")
        for query in queries:
            df = df[df["query"] != query]
        df.to_csv("prices.csv", index=False)
        await message.reply("Prices deleted successfully!")
        await set_price(message)
        await state.finish()


@dp.message_handler(lambda message: message.text == "Modify Prices 📝")
async def modify_prices(message: types.Message):
    if message.chat.id in admin_ids:
        back = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        back.add(KeyboardButton("⬅️ Back"))
        await message.reply("Insert the new prices in the following format\nDO NOT include the $ sign:\n"
                            "query1,price1\n"
                            "query2,price2\n"
                            "query3,price3\n", reply_markup=back)
        await Form.modify_prices.set()
    else:
        await message.reply("Not something you are allowed to do.")


@dp.message_handler(state=Form.modify_prices)
async def modify_prices(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Back":
        await set_price(message)
        await state.finish()
    else:
        prices = message.text.split("\n")
        df = pd.read_csv("prices.csv")
        for price in prices:
            query, price = price.split(",")
            df.loc[df["query"] == query, "price"] = price
        df.to_csv("prices.csv", index=False)
        await message.reply("Prices modified successfully!")
        await set_price(message)
        await state.finish()


@dp.message_handler(state=Form.announcement)
async def handle_announcement_text(message: types.Message, state: FSMContext):
    global last_announcement
    df = pd.read_csv("users.csv")
    user_ids = set(df["user_id"])
    if message.text != "⬅️ Back" and message.text != "❌ Cancel Previous Announcement!":
        announcement_text = message.text
        last_announcement = {}
        for user_id in user_ids:
            sent_message = await bot.send_message(chat_id=user_id, text=announcement_text, disable_notification=True)
            last_announcement[user_id] = sent_message.message_id
        await message.reply("Announcement sent!")
    if message.text == "❌ Cancel Previous Announcement!":
        now = datetime.datetime.now()
        time_limit = now - datetime.timedelta(hours=48)
        if last_announcement is not None and message.date > time_limit:
            for user_id, message_id in last_announcement.items():
                await bot.delete_message(chat_id=user_id, message_id=message_id)
            await message.reply("Previous announcement deleted!")
        elif message.date > time_limit:
            await message.reply("The time limit of 48 hours for deleting the previous announcement has passed!")
        else:
            await message.reply("No previous announcement to delete!")
    await state.finish()
    await admin_menu(message)


@dp.message_handler(lambda message: message.text == "Stats 👤")
async def show_stats(message: types.Message):
    # Get the number of users in the database
    users_df = pd.read_csv("users.csv")
    num_users = len(users_df)

    # Get the number of admins in the database
    admins_df = pd.read_csv("admins.csv")
    num_admins = len(admins_df)

    # Get the number of rows in the database
    with open("total.txt", "r") as f:
        liness = f.readline()
        f.close

    # Send the stats to the user
    await bot.send_message(chat_id=message.from_user.id,
                           text=f"Users: {num_users}\nAdmins: {num_admins}\nRows: {liness}")


@dp.message_handler(lambda message: message.text == "Upgrade List 🚀")
async def upgrade_list(message: types.Message):
    path = 'list/'
    data = []
    if len(os.listdir(path)) == 0:
        await bot.send_message(chat_id=message.from_user.id, text="No lists found in the list folder")
    else:
        await bot.send_message(chat_id=message.from_user.id, text="Upgrading list...")
        for file in os.listdir(path):
            if file.endswith(".txt"):
                with open(os.path.join(path, file), errors="ignore") as f:
                    data += f.readlines()
        with open("list.txt", "a") as f:
            for i in data:
                f.write(i)
        for file in os.listdir(path):
            if file.endswith(".txt"):
                os.remove(os.path.join(path, file))

        with open("list.txt", "r", errors='ignore') as f:
            totallines = len(f.readlines())
            f.close()
        with open("total.txt", "w", errors='ignore') as f:
            f.write(str(totallines))
            f.close()

        await bot.send_message(chat_id=message.from_user.id,
                                   text="List upgraded successfully, new total: " + str(totallines))
        print("List upgraded successfully, new total: " + str(totallines))


@dp.callback_query_handler(lambda c: c.data == "back_admin", state="*")
async def back_admin(call: types.CallbackQuery, state: FSMContext):
    await start(call.message, state)
    await state.finish()


@dp.message_handler(lambda message: message.text == "Set Admin 🔐", state="*")
async def announcement(message: types.Message):
    if (message.chat.id in admin_ids):
        await message.reply("Insert the id of the user that will be admin:")
        await Form.set_admin.set()
    else:
        await message.reply("Why would you want to do that?")


@dp.message_handler(state=Form.set_admin)
async def handle_announcement_text(message: types.Message, state: FSMContext):
    admin_id = message.text
    df = pd.read_csv("admins.csv")
    df = df.append({"user_id": admin_id}, ignore_index=True)
    df.to_csv("admins.csv", index=False)
    await message.reply("Admin set!")
    await state.finish()
    await admin_menu(message)


@dp.message_handler(lambda message: message.text == "Language 🌐")
async def language(message: types.Message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("English", callback_data="en"))
    markup.add(InlineKeyboardButton("Русский", callback_data="ru"))
    await bot.send_message(chat_id=message.from_user.id, text=_("*Please select your language:*"),
                           parse_mode='Markdown', reply_markup=markup)


@dp.callback_query_handler(lambda c: c.data == "en")
async def en(call: types.CallbackQuery, state: FSMContext):
    df = pd.read_csv("users.csv")
    df.loc[df['user_id'] == call.from_user.id, 'language'] = "en"
    df.to_csv("users.csv", index=False)
    await bot.send_message(chat_id=call.from_user.id,
                           text=_("Language changed to English. Do /start to see the changes."))


@dp.callback_query_handler(lambda c: c.data == "ru")
async def ru(call: types.CallbackQuery, state: FSMContext):
    df = pd.read_csv("users.csv")
    df.loc[df['user_id'] == call.from_user.id, 'language'] = "ru"
    df.to_csv("users.csv", index=False)
    await bot.send_message(chat_id=call.from_user.id,
                           text=_("Language changed to Russian. Do /start to see the changes."))


@dp.callback_query_handler(lambda c: c.data == "prices")
async def prices(message: types.Message, state: FSMContext):
    df = pd.read_csv("prices.csv")
    prices_text = _("Prices: 💵 ") + "\n"
    for i in range(len(df)):
        prices_text += f"● {df['query'][i].capitalize()} ➡️ {df['price'][i]}$\n"
    await bot.send_message(chat_id=message.from_user.id, text=prices_text)
    await start(message, state)


async def faq(message: types.Message):
    with open("faq.txt", "r") as f:
        faq_text = f.read()
        f.close()
    await bot.send_message(chat_id=message.from_user.id, text=faq_text, parse_mode='Markdown')


@dp.message_handler(lambda message: message.text == _("⬅️ Back"))
async def back(message: types.Message, state: FSMContext):
    await start(message, state)


translations_folder = "./translations"
ru = gettext.translation("messages", translations_folder, ["ru"])
en = gettext.translation("messages", translations_folder, ["en"])


# function for the /start command
async def start(message, state: FSMContext):
    global _, admin_ids
    admin_ids = []
    df = pd.read_csv('admins.csv')
    admin_ids = df['user_id'].tolist()
    user_id = message.from_user.id
    df = pd.read_csv("users.csv")
    user_language = None
    if df[df['user_id'] == user_id].empty:
        df = df.append({'user_id': user_id, 'user_balance': '0', 'user_sub': "False", 'language': "en"},
                       ignore_index=True)
        user_language = 'en'
        df.to_csv("users.csv", index=False)
    else:
        user_language = df.loc[df['user_id'] == user_id, 'language'].iloc[0]
    if user_language == "en":
        en.install()
        _ = en.gettext
    elif user_language == "ru":
        ru.install()
        _ = ru.gettext
    else:
        en.install()
        _ = en.gettext
        print("Sacc")
    global lines
    await state.finish()
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton(_("Get rows 🎯")))
    markup.add(KeyboardButton(_("Profile 👤")), KeyboardButton(_("Subscription 🚀")))
    markup.add(KeyboardButton(_("Prices 📊")), KeyboardButton(_("Language 🌐")))
    markup.add(KeyboardButton(_("FAQ 📢")))
    # double check
    with open("total.txt", "r", errors='ignore') as f:
        lines = f.read()
        f.close()
    with open("sold.txt", "r", errors='ignore') as f:
        sold = f.read()
        f.close()
    await message.answer(_("*👤 Loaded Lines:*") + f" {lines}\n" + _("*💵 Sold lines:*") + f" {sold}",
                         parse_mode='Markdown', reply_markup=markup)


dp.register_message_handler(start, commands=["start"])
dp.register_message_handler(get_rows, lambda message: message.text == _("Get rows 🎯"))
dp.register_message_handler(profile, lambda message: message.text == _("Profile 👤"))
dp.register_message_handler(subscription, lambda message: message.text == _("Subscription 🚀"))
dp.register_message_handler(prices, lambda message: message.text == _("Prices 📊"))
dp.register_message_handler(language, lambda message: message.text == _("Language 🌐"))
dp.register_message_handler(faq, lambda message: message.text == _("FAQ 📢"))

if __name__ == '__main__':
    executor.start_polling(dp)
