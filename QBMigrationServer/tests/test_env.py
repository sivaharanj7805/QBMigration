import os
from dotenv import load_dotenv

load_dotenv() # This loads your .env file

db_url = os.getenv('DATABASE_URL')
print(f"--- DEBUG INFO ---")
print(f"Full URL: {db_url}")
if db_url:
    password = db_url.split(':')[2].split('@')[0]
    print(f"Detected Password: {password}")
    print(f"Password Length: {len(password)} characters")
else:
    print("DATABASE_URL not found in .env file!")