# Add these lines at the very top of the file, before other imports
import matplotlib
matplotlib.use('Agg')  # Set backend to non-interactive 'Agg'

# Rest of the imports
import matplotlib.pyplot as plt
import pandas as pd
import json
import os
import requests
import threading
import time
import discum
from datetime import datetime
from datetime import timedelta
from io import BytesIO

# Bot Configuration
TOKEN = 'YOUR_BOT_TOKEN'  # Replace with your Discord bot token
GUILD_ID = "YOUR_GUILD_ID"  # Replace with your Discord server ID
COMMAND_PREFIX = "!"

# Webhook Configuration
WEBHOOK_CONFIG = {
    'DATA_ANALYST': {
        'url': 'YOUR_WEBHOOK_URL',  # Replace with your webhook URL for data analysis
        'avatar': 'https://cdn-icons-png.flaticon.com/512/1925/1925173.png'
    },
    'LOGS': {
        'url': 'YOUR_WEBHOOK_URL',  # Replace with your webhook URL for logs
        'avatar': 'https://cdn-icons-png.flaticon.com/512/4725/4725478.png'
    }
}

# Initialize Discord bot
bot = discum.Client(token=TOKEN, log=False)

def send_webhook(content, webhook_type='LOGS', username=None):
    """
    Send a message through Discord webhook
    
    Args:
        content: Message to send
        webhook_type: Type of webhook (LOGS or DATA_ANALYST)
        username: Optional custom username for the webhook
    """
    if username is None:
        username = "Data Analyst" if webhook_type == 'DATA_ANALYST' else "System Log"
    
    payload = {
        "username": username,
        "avatar_url": WEBHOOK_CONFIG[webhook_type]['avatar'],
        "content": content if "```" in content else f"```\n{content}\n```"
    }
    
    try:
        response = requests.post(WEBHOOK_CONFIG[webhook_type]['url'], json=payload)
        if response.status_code != 204:
            print(f"Webhook error: {response.status_code}")
    except Exception as e:
        print(f"Webhook error: {str(e)}")

def analyze_data():
    """
    Analyze session data and generate statistics/graphs
    
    Returns:
        bool: True if analysis was successful, False otherwise
    """
    try:
        # Check for data file
        if not os.path.exists('session_data.json'):
            send_webhook("No session data found", 'LOGS')
            return False
            
        # Load and validate data
        with open('session_data.json', 'r') as f:
            data = json.load(f)
            
        if not data:
            send_webhook("Session data is empty", 'LOGS')
            return False
            
        # Create DataFrame and convert date column to datetime
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df['duration_hours'] = df['duration'] / 3600
        
        # Sort DataFrame by date first
        df = df.sort_values('date')
        
        # Log filtered data for debugging
        send_webhook(f"Processing data:\n{df[['username', 'date', 'duration_hours']].to_string()}", 'LOGS')
        
        # Prepare statistics
        stats = {
            'users': [],
            'total_sessions': len(df)
        }
        
        graphs = []
        
        plt.figure(figsize=(12, 6))
        plt.clf()
        
        # Process data for each user
        for user in df['username'].unique():
            user_data = df[df['username'] == user]
            
            # Group by date and ensure dates are sorted
            daily_time = user_data.groupby('date')['duration_hours'].sum()
            daily_time.index = pd.to_datetime(daily_time.index)  # Ensure index is datetime
            daily_time = daily_time.sort_index()  # Sort by date index
            
            # Create x-axis dates in proper order
            dates = daily_time.index.strftime('%Y-%m-%d')
            
            # Plot with sorted dates
            plt.plot(range(len(dates)), daily_time.values, label=user, marker='o')
            
            # Set x-axis ticks and labels
            plt.xticks(range(len(dates)), dates, rotation=45, ha='right')
            
            # Calculate user statistics
            total_hours = user_data['duration_hours'].sum()
            avg_hours = total_hours / len(user_data['date'].unique())
            
            stats['users'].append({
                'username': user,
                'total_hours': round(total_hours, 1),
                'daily_avg': round(avg_hours, 1),
                'sessions': len(user_data)
            })
        
        # Configure graph appearance
        plt.title('Daily Online Time by User')
        plt.xlabel('Date')
        plt.ylabel('Hours Online')
        plt.legend()
        plt.grid(True)
        plt.tight_layout(pad=2)  # Add padding to prevent label cutoff
        
        # Save graph to memory
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        plt.close('all')
        buf.seek(0)
        graphs.append(buf.getvalue())
        
        # Send results
        send_analysis_webhook(stats, graphs)
        return True
        
    except Exception as e:
        send_webhook(f"Analysis failed: {str(e)}", 'LOGS')
        return False

def send_analysis_webhook(data, graphs):
    """
    Send analysis results via webhook with embedded formatting
    
    Args:
        data: Dictionary containing analysis results
        graphs: List of graph images as bytes
    """
    embed = {
        "title": ":bar_chart: Activity Analysis",
        "color": 0x3498db,
        "fields": [
            {
                "name": "Overview",
                "value": f"```\nTotal Users: {len(data['users'])}\nTotal Sessions: {data['total_sessions']}\n```",
                "inline": False
            }
        ],
        "timestamp": datetime.now().isoformat()
    }
    
    # Add individual user statistics
    for user in data['users']:
        embed["fields"].append({
            "name": f":bust_in_silhouette: {user['username']}",
            "value": (
                f"```\n"
                f"Total Time: {user['total_hours']:.1f}h\n"
                f"Daily Average: {user['daily_avg']:.1f}h\n"
                f"Sessions: {user['sessions']}\n"
                f"```"
            ),
            "inline": True
        })

    # Prepare webhook payload
    payload = {
        "username": "Data Analyst",
        "avatar_url": WEBHOOK_CONFIG['DATA_ANALYST']['avatar'],
        "embeds": [embed]
    }

    try:
        # Send statistics embed
        requests.post(WEBHOOK_CONFIG['DATA_ANALYST']['url'], json=payload)
        
        # Send graphs as attachments
        files = [('graph', ('activity.png', graph, 'image/png')) for graph in graphs]
        requests.post(
            WEBHOOK_CONFIG['DATA_ANALYST']['url'],
            files=files,
            data={"username": "Data Analyst", "avatar_url": WEBHOOK_CONFIG['DATA_ANALYST']['avatar']}
        )
    except Exception as e:
        print(f"[ERROR] Failed to send analysis: {e}")

@bot.gateway.command
def on_ready(resp):
    """Handle bot ready event"""
    if resp.event.ready_supplemental:
        print("Bot connected!")
        send_webhook("Data Analyst bot connected and ready!", 'LOGS')

@bot.gateway.command
def on_message(resp):
    """
    Handle incoming messages
    
    Processes commands starting with the configured prefix
    """
    if resp.event.message:
        m = resp.parsed.auto()
        
        # Ignore self messages
        if m['author']['id'] == bot.gateway.session.user['id']:
            return
            
        # Process commands
        if m['content'].startswith(COMMAND_PREFIX):
            command = m['content'][1:].lower().strip()
            channel_id = m['channel_id']
            
            if command == "analyze":
                bot.sendMessage(channel_id, ":arrows_counterclockwise: Running analysis...")
                if analyze_data():
                    bot.sendMessage(channel_id, ":white_check_mark: Analysis complete!")
                else:
                    bot.sendMessage(channel_id, ":x: Analysis failed")

def main():
    """Main bot execution"""
    print("Starting Data Analyst bot...")
    send_webhook("Data Analyst bot starting...", 'LOGS')
    
    # Ensure data file exists
    if not os.path.exists('session_data.json'):
        with open('session_data.json', 'w') as f:
            json.dump([], f)
    
    # Setup automatic daily analysis
    def auto_analyze():
        while True:
            # Calculate time until next midnight
            now = datetime.now()
            next_run = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run = next_run + timedelta(days=1)
            
            sleep_seconds = (next_run - now).total_seconds()
            time.sleep(sleep_seconds)
            
            try:
                analyze_data()
            except Exception as e:
                send_webhook(f"Automatic analysis failed: {str(e)}", 'LOGS')
    
    # Start automatic analysis thread
    analyze_thread = threading.Thread(target=auto_analyze, daemon=True)
    analyze_thread.start()
    
    # Start bot
    try:
        bot.gateway.run()
    except Exception as e:
        print(f"Bot error: {str(e)}")
        send_webhook(f"Critical bot error: {str(e)}", 'LOGS')

if __name__ == "__main__":
    main()
