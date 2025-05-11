# db.py

import mysql.connector
from mysql.connector import Error
from config import Config
import logging

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            database=Config.MYSQL_DATABASE,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            port=Config.MYSQL_PORT
        )
        if connection.is_connected():
            return connection
    except Error as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")
        return None


def create_function_and_procedures():
    conn = get_db_connection()
    if not conn:
        print("Ошибка подключения к базе данных")
        return
    cursor = conn.cursor()

    try:
        # Создание функции
        cursor.execute("""
            CREATE FUNCTION get_formatted_author(first_name VARCHAR(100), last_name VARCHAR(100))
            RETURNS VARCHAR(200)
            DETERMINISTIC
            BEGIN
                RETURN CONCAT(last_name, ', ', first_name);
            END;
        """)
        print("Функция get_formatted_author создана.")

        # Создание процедуры
        cursor.execute("""
            CREATE PROCEDURE add_new_book(
                IN book_title VARCHAR(255),
                IN book_author VARCHAR(255),
                IN book_genre VARCHAR(100),
                IN pub_year INT
            )
            BEGIN
                INSERT INTO books (title, author, genre, publication_year)
                VALUES (book_title, book_author, book_genre, pub_year);
            END;
        """)
        print("Процедура add_new_book создана.")

        # Создание триггера
        cursor.execute("""
            CREATE TRIGGER after_book_update
            AFTER UPDATE ON books
            FOR EACH ROW
            BEGIN
                INSERT INTO book_logs (book_id, action, changed_at)
                VALUES (OLD.id, 'UPDATE', NOW());
            END;
        """)
        print("Триггер after_book_update создан.")

    except Exception as e:
        print(f"Ошибка при создании функции/процедуры/триггера: {e}")

    finally:
        cursor.close()
        conn.close()

# Вызов функции для создания структуры базы данных
if __name__ == "__main__":
    create_function_and_procedures()