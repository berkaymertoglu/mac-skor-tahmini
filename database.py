import os
import psycopg2
import psycopg2.extras
import sqlite3
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        self.is_postgres = bool(self.database_url)
        
    def get_connection(self):
        """PostgreSQL veya SQLite bağlantısı"""
        if self.is_postgres:
            return psycopg2.connect(self.database_url)
        else:
            # Local development için SQLite
            return sqlite3.connect('tahminler.db')
    
    def execute_query(self, query, params=None, fetch=False):
        """Query çalıştırma helper"""
        conn = self.get_connection()
        
        if self.is_postgres:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cursor = conn.cursor()
            
        try:
            cursor.execute(query, params or ())
            
            if fetch:
                if fetch == 'one':
                    result = cursor.fetchone()
                else:
                    result = cursor.fetchall()
                conn.close()
                return result
            else:
                conn.commit()
                conn.close()
                return cursor.rowcount
                
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

# Global instance
db = DatabaseManager()
