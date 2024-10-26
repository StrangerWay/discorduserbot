import discum
import requests
import threading
import time
import json
import os
from datetime import datetime, timedelta

# Bot Configuration
TOKEN = 'YOUR_BOT_TOKEN'  # Replace with your Discord bot token

# Webhook Configuration
WEBHOOK_CONFIG = {
    'SELFBOT': {
        'url': 'YOUR_WEBHOOK_URL',  # Replace with your webhook URL for selfbot
        'avatar': 'https://cdn-icons-png.flaticon.com/512/1246/1246884.png'
    },
    'LOGS': {
        'url': 'YOUR_WEBHOOK_URL',  # Replace with your webhook URL for logs
        'avatar': 'https://cdn-icons-png.flaticon.com/512/4725/4725478.png'
    }
}

# Users to track (Discord User IDs)
USERS_TO_MONITOR = [
    "USER_ID_1",  # Replace with Discord user IDs to monitor
    "USER_ID_2",
    "USER_ID_3",
]

# Users who will receive status alerts
ALERT_RECIPIENTS = [
    "RECIPIENT_ID_1",  # Replace with Discord user IDs to receive alerts
    # Add more user IDs as needed
]

# Initialize Discord client
bot = discum.Client(token=TOKEN, log={"console":False, "file":False})

# Global session tracking
sessions = {}

def send_webhook(content, webhook_type='LOGS', username=None):
    """
    Send a message through Discord webhook
    
    Args:
        content: Message to send
        webhook_type: Type of webhook (LOGS or SELFBOT)
        username: Optional custom username for the webhook
    """
    if username is None:
        username = "Session Monitor" if webhook_type == 'SELFBOT' else "Error Log"
    
    payload = {
        "username": username,
        "avatar_url": WEBHOOK_CONFIG[webhook_type]['avatar'],
        "content": content if "```" in content else f"```\n{content}\n```"
    }
    
    try:
        requests.post(WEBHOOK_CONFIG[webhook_type]['url'], json=payload)
    except Exception as e:
        print(f"Webhook error: {str(e)}")

def save_session_data(user_id, username, start_time, end_time):
    """
    Save session data with multi-day handling
    
    Splits sessions that span across midnight into separate daily records
    """
    try:
        current_time = int(time.time())
        print(f"[DEBUG] Saving session: user={username}, start={start_time}, end={end_time}, current={current_time}")
        
        if start_time > current_time or end_time > current_time:
            print(f"[ERROR] Invalid timestamps detected")
            return
        
        # Convert timestamps to datetime for comparison
        start_dt = datetime.fromtimestamp(start_time)
        end_dt = datetime.fromtimestamp(end_time)
        
        print(f"[DEBUG] Session dates: start={start_dt}, end={end_dt}")
        
        # Handle sessions spanning multiple days
        if start_dt.date() != end_dt.date():
            print(f"[INFO] Session spans multiple days for {username}")
            save_daily_session(user_id, username, start_time, end_time)
        else:
            # Single day session
            save_daily_session(user_id, username, start_time, end_time)
            
    except Exception as e:
        print(f"[ERROR] Failed to save session: {str(e)}")
        send_webhook(f"[ERROR] Failed to save session: {str(e)}", 'LOGS')

def save_daily_session(user_id, username, start_time, end_time):
    """
    Save a session for a specific day
    
    Handles session merging if sessions are close together
    """
    try:
        current_time = int(time.time())
        print(f"[DEBUG] Saving session: {username} from {start_time} to {end_time}")
        
        # Validate timestamps
        if start_time > current_time or end_time > current_time:
            print(f"[ERROR] Invalid timestamps detected")
            return
            
        # Calculate duration
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

        filename = 'session_data.json'
        
        try:
            # Read or create session file
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    all_sessions = json.load(f)
            else:
                all_sessions = []
                
            print(f"[DEBUG] Loaded {len(all_sessions)} existing sessions")
            
            # Look for recent sessions to merge
            SESSION_MERGE_THRESHOLD = 60  # Seconds between sessions to merge
            merged = False
            
            # Check recent sessions for possible merging
            for i in range(len(all_sessions) - 1, -1, -1):
                session = all_sessions[i]
                if (session['user_id'] == user_id and 
                    session['date'] == date and 
                    abs(start_time - session['end_time']) <= SESSION_MERGE_THRESHOLD):
                    
                    # Merge sessions
                    all_sessions[i]['end_time'] = end_time
                    all_sessions[i]['duration'] = end_time - session['start_time']
                    merged = True
                    print(f"[INFO] Merged session for {username} (Duration: {all_sessions[i]['duration']}s)")
                    break
            
            # Add new session if no merge occurred
            if not merged:
                all_sessions.append(new_session)
                print(f"[INFO] Added new session for {username} (Duration: {duration}s)")
            
            # Save to file
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(all_sessions, f, indent=4)
                print(f"[INFO] Successfully saved to {filename}")
            
        except Exception as e:
            print(f"[ERROR] Failed to handle file operations: {str(e)}")
            
    except Exception as e:
        print(f"[ERROR] Failed to save session: {str(e)}")

def get_daily_stats(user_id, date):
    """
    Get statistics for a specific day
    
    Returns dict with session count, total duration, and average session length
    """
    try:
        with open('session_data.json', 'r', encoding='utf-8') as f:
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
    """Format daily statistics for display"""
    if not stats:
        return f"No data for {username} on {date}"
    
    return (
        f":bar_chart: Stats for {username} on {date}\n"
        f"Sessions: {stats['sessions']}\n"
        f"Total time: {format_duration(stats['total_duration'])}\n"
        f"Average/session: {format_duration(stats['average_session'])}"
    )

def format_duration(seconds):
    """Format duration in HH:MM:SS"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_user_info(user_id):
    """Get Discord user information"""
    try:
        user_info = bot.getProfile(user_id)
        return user_info.json()['user']['username']
    except:
        return 'Unknown'

# Add this new function to send DMs
def send_dm(user_id, content):
    """Send a direct message to a user"""
    try:
        # First, create/open a DM channel
        dm_channel = bot.createDM([user_id]).json()
        channel_id = dm_channel['id']
        print(f"[DEBUG] Opening DM channel: {channel_id}")
        
        # Send the message
        response = bot.sendMessage(channel_id, content)
        print(f"[DEBUG] Message sent: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to send message: {response.text}")
            
    except Exception as e:
        print(f"[ERROR] Failed to send DM: {str(e)}")

@bot.gateway.command
def handle_events(resp):
    """
    Handle Discord presence update events
    
    Tracks when users go online/offline and saves session data
    """
    if resp.event.presence_updated:
        try:
            data = resp.parsed.auto()
            user_id = data['user']['id']
            
            if user_id not in USERS_TO_MONITOR:
                return
            
            print(f"[DEBUG] Processing status update for user {user_id}")
            
            # Get username reliably
            try:
                user_info = bot.getProfile(user_id)
                username = user_info.json()['user']['username']
                if username == 'Unknown':
                    return
            except:
                return
            
            current_status = data.get('status', 'offline')
            current_time = int(time.time())
            
            # Handle status change
            previous_status = sessions.get(user_id, {}).get('status', 'offline')
            
            if current_status != previous_status:
                if user_id not in sessions:
                    sessions[user_id] = {}
                
                sessions[user_id]['status'] = current_status
                
                # Use Discord timestamp format
                timestamp = int(time.time())
                discord_timestamp = f"<t:{timestamp}:f>"  # 'f' gives full date/time format
                
                if current_status == 'online':
                    status_emoji = ":green_circle:"
                elif current_status == 'offline':
                    status_emoji = ":black_circle:"
                elif current_status == 'idle':
                    status_emoji = ":yellow_circle:"
                elif current_status == 'dnd':
                    status_emoji = ":red_circle:"
                
                # New cleaner format without the "+" prefix
                status_msg = (
                    f"**Status Update for {username}**\n\n"  # Bold text instead of "+"
                    f"{status_emoji} New Status: {current_status.capitalize()}\n"
                    f":arrow_right: Previous Status: {previous_status.capitalize()}\n"
                    f":clock3: {discord_timestamp}"
                )
                
                # Send to all alert recipients
                for recipient_id in ALERT_RECIPIENTS:
                    send_dm(recipient_id, status_msg)
                
                # Handle session tracking
                if current_status == 'online' and previous_status != 'online':
                    sessions[user_id]['start_time'] = current_time
                    print(f"[INFO] Session started for {username}")
                elif previous_status == 'online' and current_status != 'online':
                    start_time = sessions[user_id].get('start_time')
                    if start_time and start_time <= current_time:
                        print(f"[INFO] Saving session for {username}")
                        save_daily_session(user_id, username, start_time, current_time)
                        sessions[user_id]['start_time'] = None
                        
        except Exception as e:
            print(f"[ERROR] Failed to process presence: {str(e)}")

def main():
    """Main bot execution"""
    print("Starting bot...")
    send_webhook("Bot starting...", 'LOGS')
    
    if not os.path.exists('session_data.json'):
        with open('session_data.json', 'w') as f:
            json.dump([], f)
    
    try:
        bot.gateway.run(auto_reconnect=True)
    except Exception as e:
        error_msg = f"Bot crashed: {str(e)}"
        print(error_msg)
        send_webhook(error_msg, 'LOGS')

if __name__ == "__main__":
    main()
