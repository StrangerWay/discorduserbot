import discum
import requests
import threading
import time
import json
import os
from datetime import datetime, timedelta
import signal
import sys
import subprocess
import psutil
import platform
from PIL import Image, ImageDraw, ImageFont
import io

# Load configuration
def load_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            
        # Ensure directories exist
        for path_type, path in config['paths'].items():
            if isinstance(path, str) and not path.endswith('.json') and not path.endswith('.txt'):
                os.makedirs(path, exist_ok=True)
            elif isinstance(path, dict):
                # Handle nested paths like fonts
                for _, nested_path in path.items():
                    os.makedirs(os.path.dirname(nested_path), exist_ok=True)
                    
        return config
    except FileNotFoundError:
        print("Error: config.json not found!")
        exit(1)

# Get config
config = load_config()
TOKEN = config['tokens']['selfbot']
WEBHOOK_CONFIG = {
    'SELFBOT': config['webhooks']['selfbot'],
    'LOGS': config['webhooks']['logs']
}
USERS_TO_MONITOR = config['users_to_monitor']
ALERT_RECIPIENTS = config['alert_recipients']
ADMIN_USER_ID = config['admin_user_id']
COMMAND_PREFIX = config['command_prefix']
PATHS = config['paths']

# Initialize Discord client
bot = discum.Client(token=TOKEN, log={"console":False, "file":False})

# Global session tracking
sessions = {}

def send_webhook(content, webhook_type='LOGS', username=None):
    if username is None:
        username = "Session Monitor" if webhook_type == 'SELFBOT' else "System Log"
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_content = f"[{timestamp}] {content}"
    
    payload = {
        "username": username,
        "avatar_url": WEBHOOK_CONFIG[webhook_type]['avatar'],
        "content": formatted_content if "```" in formatted_content else f"```\n{formatted_content}\n```"
    }
    
    try:
        requests.post(WEBHOOK_CONFIG[webhook_type]['url'], json=payload)
    except Exception as e:
        print(f"[ERROR] Webhook error: {str(e)}")

def save_session_data(user_id, username, start_time, end_time):
    try:
        current_time = int(time.time())
        print(f"[DEBUG] Saving session: user={username}, start={start_time}, end={end_time}, current={current_time}")
        
        if start_time > current_time or end_time > current_time:
            print(f"[ERROR] Invalid timestamps detected")
            return
        
        start_dt = datetime.fromtimestamp(start_time)
        end_dt = datetime.fromtimestamp(end_time)
        
        print(f"[DEBUG] Session dates: start={start_dt}, end={end_dt}")
        
        if start_dt.date() != end_dt.date():
            print(f"[INFO] Session spans multiple days for {username}")
            save_daily_session(user_id, username, start_time, end_time)
        else:
            save_daily_session(user_id, username, start_time, end_time)
            
    except Exception as e:
        print(f"[ERROR] Failed to save session: {str(e)}")
        send_webhook(f"[ERROR] Failed to save session: {str(e)}", 'LOGS')

def save_daily_session(user_id, username, start_time, end_time):
    try:
        current_time = int(time.time())
        print(f"[DEBUG] Saving session: {username} from {start_time} to {end_time}")
        
        if start_time > current_time or end_time > current_time:
            print(f"[ERROR] Invalid timestamps detected")
            return
            
        duration = end_time - start_time
        if duration <= 0:
            print(f"[ERROR] Invalid duration: {duration}s")
            return
            
        date = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')
        
        new_session = {
            'user_id': user_id,
            'username': username,
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration,
            'date': date
        }

        try:
            if os.path.exists(PATHS['session_data']):
                with open(PATHS['session_data'], 'r', encoding='utf-8') as f:
                    all_sessions = json.load(f)
            else:
                all_sessions = []
                
            print(f"[DEBUG] Loaded {len(all_sessions)} existing sessions")
            
            SESSION_MERGE_THRESHOLD = 60
            merged = False
            
            for i in range(len(all_sessions) - 1, -1, -1):
                session = all_sessions[i]
                if (session['user_id'] == user_id and 
                    session['date'] == date and 
                    abs(start_time - session['end_time']) <= SESSION_MERGE_THRESHOLD):
                    
                    all_sessions[i]['end_time'] = end_time
                    all_sessions[i]['duration'] = end_time - session['start_time']
                    merged = True
                    print(f"[INFO] Merged session for {username} (Duration: {all_sessions[i]['duration']}s)")
                    break
            
            if not merged:
                all_sessions.append(new_session)
                print(f"[INFO] Added new session for {username} (Duration: {duration}s)")
            
            with open(PATHS['session_data'], 'w', encoding='utf-8') as f:
                json.dump(all_sessions, f, indent=4)
                print(f"[INFO] Successfully saved to {PATHS['session_data']}")
            
        except Exception as e:
            print(f"[ERROR] Failed to handle file operations: {str(e)}")
            
    except Exception as e:
        print(f"[ERROR] Failed to save session: {str(e)}")
def get_daily_stats(user_id, date):
    try:
        with open(PATHS['session_data'], 'r', encoding='utf-8') as f:
            sessions = json.load(f)
        
        daily_sessions = [s for s in sessions if s['user_id'] == user_id and s['date'] == date]
        total_duration = sum(s['duration'] for s in daily_sessions)
        
        return {
            'sessions': len(daily_sessions),
            'total_duration': total_duration,
            'average_session': total_duration / len(daily_sessions) if daily_sessions else 0
        }
    except Exception:
        return None

def format_stats(stats, username, date):
    if not stats:
        return f"No data for {username} on {date}"
    
    return (
        f":bar_chart: Stats for {username} on {date}\n"
        f"Sessions: {stats['sessions']}\n"
        f"Total time: {format_duration(stats['total_duration'])}\n"
        f"Average/session: {format_duration(stats['average_session'])}"
    )

def format_duration(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_user_info(user_id):
    try:
        user_info = bot.getProfile(user_id)
        return user_info.json()['user']['username']
    except:
        return 'Unknown'

def send_dm(user_id, content):
    try:
        dm_channel = bot.createDM([user_id]).json()
        channel_id = dm_channel['id']
        print(f"[DEBUG] Opening DM channel: {channel_id}")
        
        response = bot.sendMessage(channel_id, content)
        print(f"[DEBUG] Message sent: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to send message: {response.text}")
            
    except Exception as e:
        print(f"[ERROR] Failed to send DM: {str(e)}")

def refresh_sessions():
    current_time = int(time.time())
    
    try:
        for user_id, session_data in sessions.copy().items():
            if 'start_time' in session_data and session_data['start_time'] is not None:
                try:
                    username = get_user_info(user_id)
                    start_time = session_data['start_time']
                    
                    if start_time <= current_time:
                        print(f"[INFO] Saving session for {username} during refresh")
                        save_daily_session(user_id, username, start_time, current_time)
                except Exception as e:
                    print(f"[ERROR] Failed to save session during refresh for {user_id}: {str(e)}")
        
        sessions.clear()
        return "✅ Successfully saved all current sessions!"
    except Exception as e:
        error_msg = f"❌ Failed to save sessions: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return error_msg

def get_system_info():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        memory = psutil.virtual_memory()
        memory_total = memory.total / (1024 ** 3)
        memory_used = memory.used / (1024 ** 3)
        memory_percent = memory.percent
        
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024 ** 3)
        disk_used = disk.used / (1024 ** 3)
        disk_percent = disk.percent
        
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        fields = [
            {
                "name": "🖥️ CPU",
                "value": f"```Usage: {cpu_percent}%\nCores: {cpu_count}```",
                "inline": True
            },
            {
                "name": "💾 Memory",
                "value": f"```Total: {memory_total:.1f}GB\nUsed: {memory_used:.1f}GB\nUsage: {memory_percent}%```",
                "inline": True
            },
            {
                "name": "💿 Disk",
                "value": f"```Total: {disk_total:.1f}GB\nUsed: {disk_used:.1f}GB\nUsage: {disk_percent}%```",
                "inline": True
            },
            {
                "name": "⚙️ System",
                "value": f"```OS: {platform.system()} {platform.release()}\nUptime: {str(uptime).split('.')[0]}```",
                "inline": False
            }
        ]
        
        return fields
    except Exception as e:
        print(f"[ERROR] Failed to get system info: {str(e)}")
        send_webhook(f"Failed to get system info: {str(e)}", 'LOGS')
        return None

def create_stats_image():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        memory = psutil.virtual_memory()
        memory_total = memory.total / (1024 ** 3)
        memory_used = memory.used / (1024 ** 3)
        memory_percent = memory.percent
        
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024 ** 3)
        disk_used = disk.used / (1024 ** 3)
        disk_percent = disk.percent
        
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        width = 800
        height = 400
        background_color = (44, 47, 51)
        text_color = (255, 255, 255)
        
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        
        try:
            title_font = ImageFont.truetype(PATHS['fonts']['arial'], 36)
            main_font = ImageFont.truetype(PATHS['fonts']['arial'], 24)
        except:
            title_font = ImageFont.load_default()
            main_font = ImageFont.load_default()

        title = "System Usage Statistics"
        draw.text((width/2, 30), title, font=title_font, fill=text_color, anchor="mm")

        y_position = 100
        padding = 20
        
        stats_text = [
            f"CPU Usage: {cpu_percent}% | Cores: {cpu_count}",
            f"Memory: {memory_used:.1f}GB / {memory_total:.1f}GB ({memory_percent}%)",
            f"Disk: {disk_used:.1f}GB / {disk_total:.1f}GB ({disk_percent}%)",
            f"OS: {platform.system()} {platform.release()}",
            f"Uptime: {str(uptime).split('.')[0]}"
        ]

        for text in stats_text:
            draw.text((padding, y_position), text, font=main_font, fill=text_color)
            y_position += 50

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((width-padding, height-padding), timestamp, font=main_font, fill=text_color, anchor="rb")

        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        return img_byte_arr.getvalue()
        
    except Exception as e:
        print(f"[ERROR] Failed to create stats image: {str(e)}")
        return None

def send_usage_stats(channel_id, username):
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        memory = psutil.virtual_memory()
        memory_total = memory.total / (1024 ** 3)
        memory_used = memory.used / (1024 ** 3)
        memory_percent = memory.percent
        
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024 ** 3)
        disk_used = disk.used / (1024 ** 3)
        disk_percent = disk.percent
        
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        message = (
            "📊 **System Usage Statistics**\n\n"
            "🖥️ **CPU**\n"
            f"```Usage: {cpu_percent}%\nCores: {cpu_count}```\n"
            "💾 **Memory**\n"
            f"```Total: {memory_total:.1f}GB\nUsed: {memory_used:.1f}GB\nUsage: {memory_percent}%```\n"
            "💿 **Disk**\n"
            f"```Total: {disk_total:.1f}GB\nUsed: {disk_used:.1f}GB\nUsage: {disk_percent}%```\n"
            "⚙️ **System**\n"
            f"```OS: {platform.system()} {platform.release()}\nUptime: {str(uptime).split('.')[0]}```\n\n"
            f"*Requested by {username} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        )
        
        bot.sendMessage(channel_id, message)
        send_webhook("System usage stats sent", 'LOGS')
        
    except Exception as e:
        error_msg = f"Failed to send usage stats: {str(e)}"
        bot.sendMessage(channel_id, f"❌ {error_msg}")
        send_webhook(f"Error sending usage stats: {error_msg}", 'LOGS')

@bot.gateway.command
def handle_events(resp):
    if resp.event.message:
        try:
            m = resp.parsed.auto()
            if m['author']['id'] == ADMIN_USER_ID:
                channel_id = m['channel_id']
                
                if m['content'].startswith(f'{COMMAND_PREFIX}usage'):
                    send_usage_stats(channel_id, m['author']['username'])
                
                elif m['content'].startswith(f'{COMMAND_PREFIX}give'):
                    try:
                        with open(PATHS['session_data'], 'rb') as f:
                            bot.sendFile(channel_id, "session_data.json", f)
                            send_webhook(f"Session data file sent to {m['author']['username']}", 'LOGS')
                    except Exception as e:
                        error_msg = f"Failed to send file: {str(e)}"
                        bot.sendMessage(channel_id, f"❌ {error_msg}")
                        send_webhook(f"Error sending file: {error_msg}", 'LOGS')
                
                elif m['content'].startswith(f'{COMMAND_PREFIX}refresh'):
                    result = refresh_sessions()
                    bot.sendMessage(channel_id, result)
                    send_webhook(f"Refresh command executed by {m['author']['username']}", 'LOGS')
                    
        except Exception as e:
            print(f"[ERROR] Failed to process command: {str(e)}")
            send_webhook(f"Error processing command: {str(e)}", 'LOGS')
            
    if resp.event.presence_updated:
        try:
            data = resp.parsed.auto()
            user_id = data['user']['id']
            
            if user_id not in USERS_TO_MONITOR:
                return
            
            print(f"[DEBUG] Processing status update for user {user_id}")
            
            try:
                user_info = bot.getProfile(user_id)
                username = user_info.json()['user']['username']
                if username == 'Unknown':
                    return
            except:
                return
            
            current_status = data.get('status', 'offline')
            current_time = int(time.time())
            
            previous_status = sessions.get(user_id, {}).get('status', 'offline')
            
            if current_status != previous_status:
                if user_id not in sessions:
                    sessions[user_id] = {}
                
                sessions[user_id]['status'] = current_status
                
                timestamp = int(time.time())
                discord_timestamp = f"<t:{timestamp}:f>"
                
                status_emoji = {
                    'online': ":green_circle:",
                    'idle': ":yellow_circle:",
                    'dnd': ":red_circle:",
                    'offline': ":black_circle:"
                }.get(current_status, ":black_circle:")
                
                status_msg = (
                    f"**Status Update for {username}**\n\n"
                    f"{status_emoji} New Status: {current_status.capitalize()}\n"
                    f":arrow_right: Previous Status: {previous_status.capitalize()}\n"
                    f":clock3: {discord_timestamp}"
                )
                
                for recipient_id in ALERT_RECIPIENTS:
                    send_dm(recipient_id, status_msg)
                
                if current_status != 'offline' and previous_status == 'offline':
                    sessions[user_id]['start_time'] = current_time
                    print(f"[INFO] Session started for {username} with status {current_status}")
                elif previous_status != 'offline' and current_status == 'offline':
                    start_time = sessions[user_id].get('start_time')
                    if start_time and start_time <= current_time:
                        print(f"[INFO] Saving session for {username}")
                        save_daily_session(user_id, username, start_time, current_time)
                        sessions[user_id]['start_time'] = None
                        
        except Exception as e:
            print(f"[ERROR] Failed to process presence: {str(e)}")

def signal_handler(sig, frame):
    print("\nSaving sessions before exit...")
    current_time = int(time.time())
    
    for user_id, session_data in sessions.copy().items():
        if 'start_time' in session_data and session_data['start_time'] is not None:
            try:
                username = get_user_info(user_id)
                start_time = session_data['start_time']
                
                if start_time <= current_time:
                    print(f"[INFO] Saving final session for {username}")
                    save_daily_session(user_id, username, start_time, current_time)
            except Exception as e:
                print(f"[ERROR] Failed to save final session for {user_id}: {str(e)}")
    
    print("Sessions saved. Exiting...")
    sys.exit(0)

def main():
    print("Starting bot...")
    send_webhook("Bot starting...", 'LOGS')
    
    signal.signal(signal.SIGINT, signal_handler)
    
    if not os.path.exists(PATHS['session_data']):
        with open(PATHS['session_data'], 'w') as f:
            json.dump([], f)
    
    try:
        if len(sys.argv) == 1:
            subprocess.Popen([sys.executable, "dataanalyst.py"])
        
        bot.gateway.run(auto_reconnect=True)
    except Exception as e:
        error_msg = f"Bot crashed: {str(e)}"
        print(error_msg)
        send_webhook(error_msg, 'LOGS')

if __name__ == "__main__":
    main()