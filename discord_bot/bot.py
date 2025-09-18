import discord
import mysql.connector as MC
import time
import os
import asyncio
from discord.ext import commands, tasks
from datetime import datetime
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

TOKEN = os.getenv("TOKEN")
DEFAULT_CHANNEL_ID = os.getenv("DEFAULT_CHANNEL_ID")
PREFIX = "!"
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

scheduled_messages = []

async def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

def connect_db():
    try:
        conn = MC.connect(
            host=os.getenv('host'),
            database=os.getenv('database'),
            user=os.getenv('user'),
            password=os.getenv('password')
        )
        if conn.is_connected():
            return conn
    except MC.Error:
        return None

def load_messages_from_db():
    """
    Load messages from the databse and sync them in the memory.
    """
    global scheduled_messages
    db = connect_db()
    if db:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, send_time, channel_id, message FROM scheduled_messages ORDER BY id ASC")
        scheduled_messages = cursor.fetchall()
        cursor.close()
        db.close()
        
def save_message_to_db(send_time, channel_id, message):
    """
    Saves the messages to the database.
    """
    db = connect_db()
    if db:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO scheduled_messages (send_time, channel_id, message) 
            VALUES (%s, %s, %s)
        """, (send_time, channel_id, message))
        db.commit()
        last_id = cursor.lastrowid
        cursor.close()
        db.close()
        return last_id
    return None

def delete_message_from_db(message_id):
    """
    Delete specified messages from the database.
    """
    db = connect_db()
    if db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM scheduled_messages WHERE id = %s", (message_id,))
        db.commit()
        row_count = cursor.rowcount
        cursor.close()
        db.close()
        return row_count > 0
    return False

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have enough permission to use this command.")
    else:
        await ctx.send(f"An error as occured : {error}")

@bot.command()
@commands.check(is_admin)
async def timestamp(ctx, date: str, time_str: str, format_code: str = "R"):
    """
    Return a timestamp with a format code ready to use in discord
    With year, month, day, hour, minute and second.
    22/07/2066 17:15:00
    R Relative : In x Years
    t Short time : 17:15
    T Long time : 17:15:00
    d Short date : 22/07/2066
    D Long date : 22 July 2066
    f Long date with hour : 22 July 2066 17:15
    F Long date with day of the week : Thursday 22 july 2066 17:15
    
    Example : !timestamp 13/01/2025 12:15:00 R
    --> <t:1736766900:R>
    """
    valid_formats = ["R", "t", "T", "d", "D", "f", "F"]

    try:
        dt = datetime.strptime(f"{date} {time_str}", "%d/%m/%y %H:%M:%S")

        if format_code not in valid_formats:
            await ctx.send(f"Inlavid format. Use one of the following format : {', '.join(valid_formats)}.")
            return

        timestamp = int(time.mktime(dt.timetuple()))

        await ctx.send(f"```<t:{timestamp}:{format_code}>```")
    
    except ValueError:
        await ctx.send("Date or hour format incorrect. Use DD/MM/YY HH:MM:SS.")
    except Exception as e:
        await ctx.send(f"An error as occured : {e}")

@bot.command()
@commands.check(is_admin)
async def drop(ctx, date1: str, time1: str, date2:str, time2:str, *args):
    """
    Plan a message at a specified date and time with a Timestamp integrated.
    Exemple : !drop 21/11/24 18:30 25/11/24 20:00 Hello World !
    --> @Drops --> <t:1732561200:R> Hello World !
    """
    try:
        channel_id = int(os.getenv('drop_channel'))
        drop_role = os.getenv("drop_role")
        send_time = datetime.strptime(f"{date1} {time1}", "%d/%m/%y %H:%M")
        dt = datetime.strptime(f"{date2} {time2}", "%d/%m/%y %H:%M")
        timestamp = int(time.mktime(dt.timetuple()))

        if len(args) == 0:
            await ctx.send("Specify a message.")
            return

        else:
            message =f"<@&{drop_role}> --> <t:{timestamp}:F>, <t:{timestamp}:R> " + " ".join(args)
                    
        if not message:
            await ctx.send("The content of the message is empty. Please provide a valid message.")
            return

        message_id = save_message_to_db(send_time, channel_id, message)
        if message_id is None:
            message_id = len(scheduled_messages) + 1
        scheduled_messages.append({"id": message_id, "send_time": send_time, "channel_id": channel_id, "message": message})

        await ctx.send(f"Message programmed for {send_time} in channel : <#{channel_id}>.")
    except ValueError:
        await ctx.send("Date or time format invalid. Use DD/MM/YY HH:MM.")
    except Exception as e:
        await ctx.send(f"An error as occured : {e}")
                
@bot.command()
@commands.check(is_admin)
async def plan(ctx, date: str, time: str, *args):
    """
    Plan a message at a specified date and time.
    Example : !plan 21/11/24 18:30 #general Hello World !
              !plan 21/11/24 18:30 Hello World !
    """
    try:
        send_time = datetime.strptime(f"{date} {time}", "%d/%m/%y %H:%M")

        if len(args) == 0:
            await ctx.send("Please specify a message or a channel followed by a message.")
            return

        if args[0].startswith("<#"):
            channel_id = int(args[0].strip("<#>"))
            message = " ".join(args[1:])
        else:
            channel_id = DEFAULT_CHANNEL_ID
            message = " ".join(args)
        if not message:
            await ctx.send("The content of the message is empty. Please provide a valid message.")
            return

        message_id = save_message_to_db(send_time, channel_id, message)
        if message_id is None:
            message_id = len(scheduled_messages) + 1
        scheduled_messages.append({"id": message_id, "send_time": send_time, "channel_id": channel_id, "message": message})

        await ctx.send(f"Message programmed for the {send_time} in the channel <#{channel_id}>.")
    except ValueError:
        await ctx.send("Date or time format ins invalid. Use DD/MM/YY HH:MM.")
    except Exception as e:
        await ctx.send(f"An error as occured : {e}")

@bot.command()
@commands.check(is_admin)
async def view(ctx):
    """
    Show the list of programmed messages.
    """
    if scheduled_messages:
        response = "Programmed messages :\n"
        messages = []
        
        for msg in scheduled_messages:
            send = msg['send_time']
            line = f"- {msg['id']}. <t:{(int(time.mktime(send.timetuple())))}:R> dans <#{msg['channel_id']}> : {msg['message']}\n"
            if len(response) + len(line) > 2000:
                messages.append(response)
                response = line
            else:
                response += line

        if response:
            messages.append(response)

        for part in messages:
            await ctx.send(part)
    else:
        await ctx.send("No programmed message.")

@bot.command()
@commands.check(is_admin)
async def delete(ctx, message_id: int):
    """
    Delete a message base on his ID.
    """
    global scheduled_messages
    message_to_delete = next((msg for msg in scheduled_messages if msg['id'] == message_id), None)
    if message_to_delete:
        scheduled_messages = [msg for msg in scheduled_messages if msg['id'] != message_id]
        db_success = delete_message_from_db(message_id)
        if not db_success:
            await ctx.send(f"Message {message_id} deleted from the memory, but not from DataBase (DataBase unavailable).")
        else:
            await ctx.send(f"Message {message_id} deleted with success.")
    else:
        await ctx.send(f"No message found with the ID : {message_id}.")

@bot.command()
@commands.check(is_admin)
async def edit(ctx, message_id: int, field: str, *, value: str):
    """
    Modify a programmed message.
    Example : !edit 1 message <New content>
    date, channel, message
    """
    global scheduled_messages
    fields = {"date": "send_time", "message": "message", "channel": "channel_id"}
    if field not in fields:
        await ctx.send("Invalid field. Use : date, message or channel.")
        return

    message_to_edit = next((msg for msg in scheduled_messages if msg['id'] == message_id), None)
    if not message_to_edit:
        await ctx.send(f"No message found with the ID : {message_id}.")
        return

    try:
        if field == "date":
            new_value = datetime.strptime(value, "%d/%m/%y %H:%M:%S")
            message_to_edit["send_time"] = new_value
        elif field == "channel":
            new_value = int(value.strip("<#>"))
            message_to_edit["channel_id"] = new_value
        elif field == "message":
            new_value = value
            message_to_edit["message"] = new_value

        db = connect_db()
        if db:
            cursor = db.cursor()
            cursor.execute(f"UPDATE scheduled_messages SET {fields[field]} = %s WHERE id = %s", (new_value, message_id))
            db.commit()
            cursor.close()
            db.close()

        await ctx.send(f"Message {message_id} updated with success.")
    except ValueError:
        await ctx.send("Value Format is incorect for the chosen field.")

@bot.command()
async def hour(ctx):
    """
    Show the time of the bot.
    """
    now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
    await ctx.send(f"Current time : {now}")

@bot.command()
@commands.check(is_admin)
async def clear(ctx):
    """
    Delete all the messages from the bot or with a command related to the bot.
    """
    def is_bot_command_or_message(message):
        return message.author == bot.user or message.content.startswith(PREFIX)

    await ctx.channel.purge(limit=None, check=is_bot_command_or_message, bulk=True)
    await ctx.send("Cleaning finished.", delete_after=5)
    
@bot.command()
@commands.check(is_admin)
async def test(ctx):
    """
    Send 3 messages spaced by 5 seconds.
    """
    guild = ctx.guild
    channel = ctx.channel

    for i in range(3):
            try:
                await channel.send(f"test {i+1}")
            except discord.Forbidden:
                await ctx.send("Error : bot doesn't have permission to send messages.")
            except discord.HTTPException as e:
                await ctx.send(f"Error : {e}")
                return
            await asyncio.sleep(1)
            if i < 2:
                await asyncio.sleep(5)

# --- Tâches asynchrones ---
@tasks.loop(seconds=20)
async def send_scheduled_messages():
    """
    Task to check on programmed messages and send them.
    """
    global scheduled_messages
    now = datetime.now()
    to_send = [msg for msg in scheduled_messages if msg['send_time'] <= now]
    for msg in to_send:
        channel = bot.get_channel(msg['channel_id'])
        if channel:
            await channel.send(
                msg['message'], 
                allowed_mentions=discord.AllowedMentions(roles=True))
        scheduled_messages.remove(msg)
        delete_message_from_db(msg['id'])

@bot.event
async def on_ready():
    load_messages_from_db()
    send_scheduled_messages.start()

bot.run(TOKEN)



