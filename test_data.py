import json
import random
from datetime import datetime, timedelta

def generate_test_data():
    """
    Generate realistic test data for session tracking
    
    Creates 30 days of session data for test users with realistic patterns:
    - More activity during normal waking hours
    - Random inactive days
    - Variable session lengths
    """
    users = [
        {"id": "123456789", "name": "John_Doe"},
        {"id": "987654321", "name": "Alice_Smith"},
        {"id": "456789123", "name": "Bob_Wilson"}
    ]
    
    data = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    current_date = start_date
    while current_date <= end_date:
        # Generate daily sessions for each user
        for user in users:
            # 10% chance user is inactive that day
            if random.random() < 0.1:
                continue
                
            num_sessions = random.randint(5, 15)
            
            for _ in range(num_sessions):
                # Realistic hour distribution (more activity 8AM-11PM)
                hour = random.choices(
                    range(24),
                    weights=[1,1,1,1,1,1,3,5,8,10,10,8,8,10,10,8,8,10,10,8,5,3,2,1]
                )[0]
                minute = random.randint(0, 59)
                
                # Create session start time
                start_time = current_date.replace(hour=hour, minute=minute)
                
                # Random session duration (15 mins to 4 hours)
                duration = random.randint(15, 240) * 60  # in seconds
                end_time = start_time + timedelta(seconds=duration)
                
                session = {
                    "user_id": user["id"],
                    "username": user["name"],
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "duration": duration,
                    "date": start_time.strftime("%Y-%m-%d")
                }
                data.append(session)
        
        current_date += timedelta(days=1)
    
    # Save generated data
    with open('session_data.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Generated {len(data)} sessions for {len(users)} users over 30 days")

if __name__ == "__main__":
    generate_test_data()
