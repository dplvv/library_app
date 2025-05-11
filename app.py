# app.py

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from config import Config
from db import get_db_connection
from utils import hash_password, check_password
import mysql.connector
from mysql.connector import errorcode
import logging
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

jwt = JWTManager(app)

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# Маршрут для регистрации (API)
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'msg': 'Имя пользователя и пароль обязательны'}), 400

    hashed_pw = hash_password(password)

    conn = get_db_connection()
    if not conn:
        return jsonify({'msg': 'Ошибка подключения к базе данных'}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                       (username, hashed_pw, 'user'))
        conn.commit()
    except mysql.connector.IntegrityError:
        conn.rollback()
        return jsonify({'msg': 'Имя пользователя уже существует'}), 409
    finally:
        cursor.close()
        conn.close()

    return jsonify({'msg': 'Пользователь зарегистрирован успешно'}), 201


# Маршрут для авторизации (API)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    if not conn:
        return jsonify({'msg': 'Ошибка подключения к базе данных'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password(password, user['password']):
        access_token = create_access_token(
            identity={'id': user['id'], 'role': user['role'], 'username': user['username']})
        return jsonify({'access_token': access_token}), 200
    else:
        return jsonify({'msg': 'Неверные учетные данные'}), 401


# Маршрут для получения списка книг с фильтрацией (API)
@app.route('/api/books', methods=['GET'])
@jwt_required()
def get_books():
    title = request.args.get('title')
    author = request.args.get('author')
    genre = request.args.get('genre')
    page = request.args.get('page', default=1, type=int)  # Номер страницы
    limit = request.args.get('limit', default=10, type=int)  # Количество записей на странице

    conn = get_db_connection()
    if not conn:
        return jsonify({'msg': 'Ошибка подключения к базе данных'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.callproc('search_books_proc', [title, author, genre])
        books = []
        for result in cursor.stored_results():
            books = result.fetchall()

        # Пагинация
        start = (page - 1) * limit
        end = start + limit
        paginated_books = books[start:end]

        return jsonify({
            'books': paginated_books,
            'total_books': len(books),
            'page': page,
            'total_pages': (len(books) + limit - 1) // limit
        }), 200
    except Exception as e:
        print(e)
        return jsonify({'msg': 'Ошибка при поиске книг'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(books), 200


# Маршрут для добавления новой книги (API, только для admin)
@app.route('/api/books', methods=['POST'])
@jwt_required()
def add_book():
    current_user = get_jwt_identity()
    if current_user['role'] != 'admin':
        return jsonify({'msg': 'Доступ запрещен'}), 403

    data = request.get_json()
    title = data.get('title')
    author = data.get('author')
    genre = data.get('genre')
    publication_year = data.get('publication_year')
    description = data.get('description')

    if not title or not author:
        return jsonify({'msg': 'Название и автор обязательны'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'msg': 'Ошибка подключения к базе данных'}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO books (title, author, genre, publication_year, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (title, author, genre, publication_year, description))
        conn.commit()
        book_id = cursor.lastrowid
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'msg': 'Ошибка при добавлении книги'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({'msg': 'Книга добавлена', 'book_id': book_id}), 201


# Маршрут для редактирования книги (API, только для admin)
@app.route('/api/books/<int:book_id>', methods=['PUT'])
@jwt_required()
def edit_book(book_id):
    current_user = get_jwt_identity()
    if current_user['role'] != 'admin':
        return jsonify({'msg': 'Доступ запрещен'}), 403

    data = request.get_json()
    title = data.get('title')
    author = data.get('author')
    genre = data.get('genre')
    publication_year = data.get('publication_year')
    description = data.get('description')

    conn = get_db_connection()
    if not conn:
        return jsonify({'msg': 'Ошибка подключения к базе данных'}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE books
            SET title = %s, author = %s, genre = %s, publication_year = %s, description = %s
            WHERE id = %s
        """, (title, author, genre, publication_year, description, book_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'msg': 'Ошибка при обновлении книги'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({'msg': 'Книга обновлена'}), 200


# Маршрут для удаления книги (API, только для admin)
@app.route('/api/books/<int:book_id>', methods=['DELETE'])
@jwt_required()
def delete_book(book_id):
    current_user = get_jwt_identity()
    if current_user['role'] != 'admin':
        return jsonify({'msg': 'Доступ запрещен'}), 403

    conn = get_db_connection()
    if not conn:
        return jsonify({'msg': 'Ошибка подключения к базе данных'}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'msg': 'Ошибка при удалении книги'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({'msg': 'Книга удалена'}), 200


# Маршрут для регистрации (HTML форма)
@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Имя пользователя и пароль обязательны')
            return redirect(url_for('register_page'))

        hashed_pw = hash_password(password)

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных')
            return redirect(url_for('register_page'))
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                           (username, hashed_pw, 'user'))
            conn.commit()
            flash('Пользователь успешно зарегистрирован')
            return redirect(url_for('login_page'))
        except mysql.connector.IntegrityError:
            conn.rollback()
            flash('Имя пользователя уже существует')
            return redirect(url_for('register_page'))
        finally:
            cursor.close()
            conn.close()
    return render_template('register.html')


# Маршрут для авторизации (HTML форма)
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных')
            return redirect(url_for('login_page'))
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password(password, user['password']):
            access_token = create_access_token(
                identity={'id': user['id'], 'role': user['role'], 'username': user['username']})
            session['access_token'] = access_token
            session['user'] = {'id': user['id'], 'role': user['role'], 'username': user['username']}
            flash('Вы успешно вошли в систему')
            return redirect(url_for('index'))
        else:
            flash('Неверные учетные данные')
            return redirect(url_for('login_page'))
    return render_template('login.html')


# Маршрут для выхода
@app.route('/logout')
def logout():
    session.pop('access_token', None)
    session.pop('user', None)
    flash('Вы успешно вышли из системы')
    return redirect(url_for('login_page'))


# Главная страница с отображением книг
@app.route('/')
def index():
    user = session.get('user')
    if not user:
        return redirect(url_for('login_page'))

    title = request.args.get('title')
    author = request.args.get('author')
    genre = request.args.get('genre')
    page = request.args.get('page', default=1, type=int)
    limit = request.args.get('limit', default=10, type=int)

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return render_template('index.html', books=[], current_user=user, page=page, total_pages=1)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.callproc('search_books_proc', [title, author, genre])
        books = []
        for result in cursor.stored_results():
            books = result.fetchall()

        # Пагинация
        start = (page - 1) * limit
        end = start + limit
        paginated_books = books[start:end]
        total_pages = (len(books) + limit - 1) // limit

        return render_template(
            'index.html',
            books=paginated_books,
            current_user=user,
            page=page,
            total_pages=total_pages,
        )
    except Exception as e:
        logging.exception("Error during fetching books.")
        flash('Ошибка при поиске книг')
        return render_template('index.html', books=[], current_user=user, page=page, total_pages=1)
    finally:
        cursor.close()
        conn.close()
        logging.debug("Database connection closed.")


# Маршрут для добавления книги (HTML форма)
@app.route('/add_book', methods=['GET', 'POST'])
def add_book_page():
    user = session.get('user')
    if not user or user['role'] != 'admin':
        flash('У вас нет прав для доступа к этой странице')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        genre = request.form.get('genre')
        publication_year = request.form.get('publication_year')
        description = request.form.get('description')
        quantity = request.form.get('quantity', 1)
        cover_image = request.files.get('cover_image')

        # Обработка загрузки обложки
        cover_image_filename = None
        if cover_image and allowed_file(cover_image.filename):
            cover_image_filename = secure_filename(cover_image.filename)
            cover_image.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_image_filename))
        elif cover_image:
            flash('Недопустимый формат файла для обложки.')
            return redirect(url_for('add_book_page'))

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных')
            return redirect(url_for('add_book_page'))
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO books (title, author, genre, publication_year, description, quantity, cover_image)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (title, author, genre, publication_year, description, quantity, cover_image_filename))
            conn.commit()
            flash('Книга успешно добавлена')
            return redirect(url_for('index'))
        except Exception as e:
            conn.rollback()
            logging.exception("Ошибка при добавлении книги.")
            flash('Ошибка при добавлении книги')
            return redirect(url_for('add_book_page'))
        finally:
            cursor.close()
            conn.close()

    return render_template('add_book.html')


# Маршрут для редактирования книги (HTML форма)
@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
def edit_book_page(book_id):
    user = session.get('user')
    if not user or user['role'] != 'admin':
        flash('У вас нет прав для доступа к этой странице')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        genre = request.form.get('genre')
        publication_year = request.form.get('publication_year')
        description = request.form.get('description')
        quantity = request.form.get('quantity', 1)
        cover_image = request.files.get('cover_image')

        # Обработка загрузки обложки
        cover_image_filename = None
        if cover_image and allowed_file(cover_image.filename):
            cover_image_filename = secure_filename(cover_image.filename)
            cover_image.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_image_filename))
        elif cover_image:
            flash('Недопустимый формат файла для обложки.')
            return redirect(url_for('edit_book_page', book_id=book_id))

        try:
            if cover_image_filename:
                cursor.execute("""
                    UPDATE books
                    SET title = %s, author = %s, genre = %s, publication_year = %s, description = %s, quantity = %s, cover_image = %s
                    WHERE id = %s
                """, (title, author, genre, publication_year, description, quantity, cover_image_filename, book_id))
            else:
                cursor.execute("""
                    UPDATE books
                    SET title = %s, author = %s, genre = %s, publication_year = %s, description = %s, quantity = %s
                    WHERE id = %s
                """, (title, author, genre, publication_year, description, quantity, book_id))
            conn.commit()
            flash('Книга успешно обновлена')
            return redirect(url_for('index'))
        except Exception as e:
            conn.rollback()
            logging.exception("Ошибка при обновлении книги.")
            flash('Ошибка при обновлении книги')
            return redirect(url_for('edit_book_page', book_id=book_id))
        finally:
            cursor.close()
            conn.close()

    # Получение данных книги для предзаполнения формы
    try:
        cursor.execute("SELECT * FROM books WHERE id = %s", (book_id,))
        book = cursor.fetchone()
        if not book:
            flash('Книга не найдена')
            return redirect(url_for('index'))
    except Exception as e:
        logging.exception("Ошибка при получении данных книги.")
        flash('Ошибка при получении данных книги')
        return redirect(url_for('index'))
    finally:
        cursor.close()
        conn.close()

    return render_template('edit_book.html', book=book)


# Маршрут для удаления книги (HTML форма)
@app.route('/delete_book/<int:book_id>', methods=['POST'])
def delete_book_page(book_id):
    user = session.get('user')
    if not user or user['role'] != 'admin':
        flash('У вас нет прав для выполнения этого действия')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('index'))
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))
        conn.commit()
        flash('Книга успешно удалена')
    except Exception as e:
        conn.rollback()
        logging.exception("Error during deleting book.")
        flash('Ошибка при удалении книги')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('index'))


# Маршрут для бронирования книги (HTML форма)
@app.route('/reserve_book/<int:book_id>', methods=['POST'])
def reserve_book(book_id):
    user = session.get('user')
    if not user:
        flash('Пожалуйста, войдите в систему, чтобы бронировать книги.')
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)

    try:
        # Проверка доступности книги
        cursor.execute("SELECT quantity FROM books WHERE id = %s", (book_id,))
        book = cursor.fetchone()
        if not book:
            flash('Книга не найдена.')
            return redirect(url_for('index'))
        if book['quantity'] < 1:
            flash('Нет доступных экземпляров этой книги для бронирования.')
            return redirect(url_for('index'))

        # Уменьшение количества доступных экземпляров
        cursor.execute("UPDATE books SET quantity = quantity - 1 WHERE id = %s", (book_id,))

        # Добавление записи в таблицу reservations
        cursor.execute("""
            INSERT INTO reservations (user_id, book_id)
            VALUES (%s, %s)
        """, (user['id'], book_id))

        conn.commit()
        flash('Книга успешно забронирована.')
    except Exception as e:
        conn.rollback()
        logging.exception("Ошибка при бронировании книги.")
        flash('Ошибка при бронировании книги.')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('index'))


# Маршрут для просмотра своих бронирований
@app.route('/my_reservations')
def my_reservations():
    user = session.get('user')
    if not user:
        flash('Пожалуйста, войдите в систему, чтобы просматривать бронирования.')
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT r.id, b.title, b.author, r.reservation_date, r.status
            FROM reservations r
            JOIN books b ON r.book_id = b.id
            WHERE r.user_id = %s
            ORDER BY r.reservation_date DESC
        """, (user['id'],))
        reservations = cursor.fetchall()
    except Exception as e:
        logging.exception("Ошибка при получении бронирований.")
        reservations = []
        flash('Ошибка при получении бронирований.')
    finally:
        cursor.close()
        conn.close()

    return render_template('my_reservations.html', reservations=reservations, current_user=user)


# Маршрут для отмены бронирования пользователем
@app.route('/cancel_reservation/<int:reservation_id>', methods=['POST'])
def cancel_reservation(reservation_id):
    user = session.get('user')
    if not user:
        flash('Пожалуйста, войдите в систему, чтобы отменить бронирование.')
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('my_reservations'))
    cursor = conn.cursor(dictionary=True)

    try:
        # Проверка, принадлежит ли бронирование текущему пользователю и активно ли оно
        cursor.execute("""
            SELECT book_id, status FROM reservations
            WHERE id = %s AND user_id = %s
        """, (reservation_id, user['id']))
        reservation = cursor.fetchone()
        if not reservation:
            flash('Бронирование не найдено или вы не имеете к нему доступа.')
            return redirect(url_for('my_reservations'))
        if reservation['status'] != 'active':
            flash('Только активные бронирования могут быть отменены.')
            return redirect(url_for('my_reservations'))

        # Обновление статуса бронирования на отменено
        cursor.execute("""
            UPDATE reservations
            SET status = 'canceled'
            WHERE id = %s
        """, (reservation_id,))

        # Увеличение количества доступных экземпляров книги
        cursor.execute("""
            UPDATE books
            SET quantity = quantity + 1
            WHERE id = %s
        """, (reservation['book_id'],))

        conn.commit()
        flash('Бронирование успешно отменено.')
    except Exception as e:
        conn.rollback()
        logging.exception("Ошибка при отмене бронирования.")
        flash('Ошибка при отмене бронирования.')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('my_reservations'))


# Новый маршрут для администраторов: просмотр всех бронирований
@app.route('/admin_reservations')
def admin_reservations():
    user = session.get('user')
    if not user or user['role'] != 'admin':
        flash('У вас нет прав для доступа к этой странице.')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT r.id, u.username, b.title, b.author, r.reservation_date, r.status
            FROM reservations r
            JOIN users u ON r.user_id = u.id
            JOIN books b ON r.book_id = b.id
            ORDER BY r.reservation_date DESC
        """)
        reservations = cursor.fetchall()
    except Exception as e:
        logging.exception("Ошибка при получении всех бронирований.")
        reservations = []
        flash('Ошибка при получении бронирований.')
    finally:
        cursor.close()
        conn.close()

    return render_template('admin_reservations.html', reservations=reservations, current_user=user)


# Новый маршрут для администраторов: отмена любого бронирования
@app.route('/admin_cancel_reservation/<int:reservation_id>', methods=['POST'])
def admin_cancel_reservation(reservation_id):
    user = session.get('user')
    if not user or user['role'] != 'admin':
        flash('У вас нет прав для выполнения этого действия.')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных')
        return redirect(url_for('admin_reservations'))
    cursor = conn.cursor(dictionary=True)

    try:
        # Проверка существования бронирования
        cursor.execute("""
            SELECT book_id, status FROM reservations
            WHERE id = %s
        """, (reservation_id,))
        reservation = cursor.fetchone()
        if not reservation:
            flash('Бронирование не найдено.')
            return redirect(url_for('admin_reservations'))
        if reservation['status'] != 'active':
            flash('Только активные бронирования могут быть отменены.')
            return redirect(url_for('admin_reservations'))

        # Обновление статуса бронирования на отменено
        cursor.execute("""
            UPDATE reservations
            SET status = 'canceled'
            WHERE id = %s
        """, (reservation_id,))

        # Увеличение количества доступных экземпляров книги
        cursor.execute("""
            UPDATE books
            SET quantity = quantity + 1
            WHERE id = %s
        """, (reservation['book_id'],))

        conn.commit()
        flash('Бронирование успешно отменено.')
    except Exception as e:
        conn.rollback()
        logging.exception("Ошибка при отмене бронирования администратором.")
        flash('Ошибка при отмене бронирования.')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_reservations'))


if __name__ == '__main__':
    app.run(debug=True)
