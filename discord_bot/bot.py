import discord
import mysql.connector as MC
import time
import os
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

# Structure en memoire pour stocker les messages programmes
scheduled_messages = []  # Liste contenant des dicts : {"id", "send_time", "channel_id", "message"}

# Role requis pour les commandes specifiques
ROLE_REQUIRED = "Calendrier"

# Verification des permissions
async def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

async def has_calendar_role_or_admin(ctx):
    if await is_admin(ctx):
        return True
    role = discord.utils.get(ctx.author.roles, name=ROLE_REQUIRED)
    return role is not None

# Connexion a la base de donnees
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

# Charger les messages depuis la DB au demarrage
def load_messages_from_db():
    """
    Charge les messages depuis la base de données et synchronise strictement les messages en memoire avec les messages de la base.
    """
    global scheduled_messages
    db = connect_db()
    if db:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, send_time, channel_id, message FROM scheduled_messages ORDER BY id ASC")
        scheduled_messages = cursor.fetchall()
        cursor.close()
        db.close()

# Sauvegarder un message dans la DB
def save_message_to_db(send_time, channel_id, message):
    """
    Sauvegarde les messages dans la base de données
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

# Supprimer un message de la DB
def delete_message_from_db(message_id):
    """
    Supprime le message spécifié de la base de données
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

# Gestion des erreurs globales
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ Vous n'avez pas la permission d'utiliser cette commande.")
    else:
        await ctx.send(f"❌ Une erreur est survenue : {error}")

@bot.command()
@commands.check(is_admin)
async def timestamp(ctx, date: str, time_str: str, format_code: str = "R"):
    """
    Permet d'avoir le timestamp
    En fonction de l'année, le mois, le jour, l'heure, la minute, et la seconde
    22/07/2066 17:15:00
    R Relatif : dans x années
    t Temps cours : 17:15
    T Temps long : 17:15:00
    d Date courte : 22/07/2066
    D Date longue : 22 juillet 2066
    f Date longue avec heure : 22 juillet 2066 17:15
    F Date longue avec jour de la semaine : jeudi 22 juillet 2066 17:15
    
    Exemple : !timestamp 13/01/2025 12:15:00 R
    --> <t:1736766900:R>
    """
    valid_formats = ["R", "t", "T", "d", "D", "f", "F"]

    try:
        # Vérification du format de la date et de l'heure
        dt = datetime.strptime(f"{date} {time_str}", "%d/%m/%y %H:%M:%S")
        
        # Vérification du format donné par l'utilisateur
        if format_code not in valid_formats:
            await ctx.send(f"Format invalide. Utilisez l'un des formats suivants : {', '.join(valid_formats)}.")
            return

        # Conversion en timestamp
        timestamp = int(time.mktime(dt.timetuple()))

        # Construction de l'affichage pour Discord
        await ctx.send(f"```<t:{timestamp}:{format_code}>```")
    
    except ValueError:
        await ctx.send("Format de date ou d'heure incorrect. Utilisez JJ/MM/AA HH:MM:SS.")
    except Exception as e:
        await ctx.send(f"Une erreur est survenue : {e}")

@bot.command()
@commands.check(is_admin)
async def drop(ctx, date1: str, time1: str, date2:str, time2:str, *args):
    """
    Programme un message.
    Exemple : !drop 21/11/24 18:30 25/11/24 20:00 Bonjour tout le monde !
    --> notifs-drops : @Drops --> <t:1732561200:R> Bonjour tout le monde
    """
    try:
        channel_id = 1334177160319209594
        # Conversion de la date et de l'heure
        send_time = datetime.strptime(f"{date1} {time1}", "%d/%m/%y %H:%M")
        dt = datetime.strptime(f"{date2} {time2}", "%d/%m/%y %H:%M")
        timestamp = int(time.mktime(dt.timetuple()))
            
        # Vérification des arguments restants
        if len(args) == 0:
            await ctx.send("Veuillez spécifier un message.")
            return

        else:
            message =f"<@&1283096960567480321> Jusqu'au <t:{timestamp}:F>, <t:{timestamp}:R> " + " ".join(args) # Tout est considéré comme le message
                    
        if not message:
            await ctx.send("Le contenu du message est vide. Veuillez fournir un message valide.")
            return

        # Sauvegarde en mémoire
        message_id = save_message_to_db(send_time, channel_id, message)
        if message_id is None:
            message_id = len(scheduled_messages) + 1  # ID temporaire si DB inaccessible
        scheduled_messages.append({"id": message_id, "send_time": send_time, "channel_id": channel_id, "message": message})

        await ctx.send(f"Message programmé pour le {send_time} dans le canal <#{channel_id}>.")
    except ValueError:
        await ctx.send("Le format de date ou d'heure est incorrect. Utilisez JJ/MM/AA HH:MM.")
    except Exception as e:
        await ctx.send(f"Une erreur est survenue : {e}")
                
@bot.command()
@commands.check(is_admin)
async def preview(ctx, date: str, time: str, *args):
    """
    Programme un message.
    Exemple : !drop 21/11/24 18:30 #général Bonjour tout le monde !
              !drop 21/11/24 18:30 Bonjour tout le monde ! (par défaut dans #le_marché)
    """
    try:
        # Conversion de la date et de l'heure
        send_time = datetime.strptime(f"{date} {time}", "%d/%m/%y %H:%M")

        # Vérification des arguments restants
        if len(args) == 0:
            await ctx.send("Veuillez spécifier un message ou un channel suivi d'un message.")
            return

        if args[0].startswith("<#"):  # Si le premier argument est une mention de channel
            channel_id = int(args[0].strip("<#>"))
            message = " ".join(args[1:])  # Le reste est le message
        else:
            channel_id = DEFAULT_CHANNEL_ID  # Par défaut
            message = " ".join(args)  # Tout est considéré comme le message

        if not message:
            await ctx.send("Le contenu du message est vide. Veuillez fournir un message valide.")
            return

        # Sauvegarde en mémoire
        message_id = save_message_to_db(send_time, channel_id, message)
        if message_id is None:
            message_id = len(scheduled_messages) + 1  # ID temporaire si DB inaccessible
        scheduled_messages.append({"id": message_id, "send_time": send_time, "channel_id": channel_id, "message": message})

        await ctx.send(f"Message programmé pour le {send_time} dans le canal <#{channel_id}>.")
    except ValueError:
        await ctx.send("Le format de date ou d'heure est incorrect. Utilisez JJ/MM/AA HH:MM.")
    except Exception as e:
        await ctx.send(f"Une erreur est survenue : {e}")

@bot.command()
@commands.check(is_admin)
async def view(ctx):
    """
    Affiche la liste des messages programmés avec pagination pour éviter de dépasser la limite de 2000 caractères.
    """
    if scheduled_messages:
        response = "Messages programmés :\n"
        messages = []
        
        for msg in scheduled_messages:
            send = msg['send_time']
            line = f"- {msg['id']}. <t:{(int(time.mktime(send.timetuple())))}:R> dans <#{msg['channel_id']}> : {msg['message']}\n"
            if len(response) + len(line) > 2000:
                messages.append(response)  # Sauvegarde le bloc actuel
                response = line  # Commence un nouveau bloc
            else:
                response += line
        
        # Ajouter le dernier bloc s'il y en a un
        if response:
            messages.append(response)
        
        # Envoyer les blocs un par un
        for part in messages:
            await ctx.send(part)
    else:
        await ctx.send("Aucun message programmé.")

@bot.command()
@commands.check(is_admin)
async def delete(ctx, message_id: int):
    """
    Supprime un message programmé par son ID.
    """
    global scheduled_messages
    message_to_delete = next((msg for msg in scheduled_messages if msg['id'] == message_id), None)
    if message_to_delete:
        scheduled_messages = [msg for msg in scheduled_messages if msg['id'] != message_id]
        db_success = delete_message_from_db(message_id)
        if not db_success:
            await ctx.send(f"Message {message_id} supprimé de la mémoire, mais pas de la DB (DB inaccessible).")
        else:
            await ctx.send(f"Message {message_id} supprimé avec succès.")
    else:
        await ctx.send(f"Aucun message trouvé avec l'ID {message_id}.")

@bot.command()
@commands.check(is_admin)
async def edit(ctx, message_id: int, field: str, *, value: str):
    """
    Modifie un message programmé.
    Exemple : !edit 1 message <Nouveau contenu du message>
    """
    global scheduled_messages
    fields = {"date": "send_time", "message": "message", "channel": "channel_id"}
    if field not in fields:
        await ctx.send("Champ invalide. Utilisez : date, message, ou channel.")
        return

    message_to_edit = next((msg for msg in scheduled_messages if msg['id'] == message_id), None)
    if not message_to_edit:
        await ctx.send(f"Aucun message trouvé avec l'ID {message_id}.")
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

        # Mise à jour dans la DB si possible
        db = connect_db()
        if db:
            cursor = db.cursor()
            cursor.execute(f"UPDATE scheduled_messages SET {fields[field]} = %s WHERE id = %s", (new_value, message_id))
            db.commit()
            cursor.close()
            db.close()

        await ctx.send(f"Message {message_id} mis à jour avec succès.")
    except ValueError:
        await ctx.send("Format de valeur incorrect pour le champ choisi.")

@bot.command()
async def hour(ctx):
    """
    Affiche l'heure du bot.
    """
    now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
    await ctx.send(f"Heure actuelle : {now}")

@bot.command()
@commands.check(is_admin)
async def clear(ctx):
    """
    Supprime tous les messages du bot et ceux contenant une commande du bot.
    """
    def is_bot_command_or_message(message):
        return message.author == bot.user or message.content.startswith(PREFIX)

    await ctx.channel.purge(limit=None, check=is_bot_command_or_message, bulk=True)
    await ctx.send("Nettoyage terminé.", delete_after=5)

# --- Tâches asynchrones ---
@tasks.loop(seconds=20)
async def send_scheduled_messages():
    """
    Tâche qui vérifie les messages programmés et les envoie.
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
    load_messages_from_db()  # Charger les messages au démarrage
    send_scheduled_messages.start()  # Démarrer la tâche d'envoi

bot.run(TOKEN)
