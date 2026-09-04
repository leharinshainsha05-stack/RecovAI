import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

try:
    conn = psycopg2.connect(
        host="localhost",
        user="postgres",
        password="12345678"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE recovai;")
    print("? Database recovai created successfully!")
    cursor.close()
    conn.close()
except psycopg2.Error as e:
    print(f"PostgreSQL Error: {e}")
except Exception as e:
    print(f"Error: {e}")
