from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_session import Session
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import os
import time
import re
from bs4 import BeautifulSoup
import mysql.connector
import secrets
from mysql.connector import Error
from datetime import timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Session configuration
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_NAME='product_detector_session',
    SESSION_TYPE='filesystem',
    SESSION_FILE_DIR='./flask_session',
    SESSION_FILE_THRESHOLD=500
)

Session(app)

db_config = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '',
    'database': 'product_detecting',
    'autocommit': False,
    'pool_name': 'product_pool',
    'pool_size': 5,
    'pool_reset_session': True
}

CURRENCY_SYMBOLS = {"$", "€", "£", "¥", "₺"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "JPY", "TRY", "TL"}

def create_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        print("Database connection established")
        return connection
    except Error as e:
        print(f"Database connection failed: {e}")
        return None

def contains_price_canceled(text):
    text = text.strip()
    
    if re.search(r"[\d]+(?:[.,]\d+)?", text):
        match = re.search(r"([\d]+(?:[.,]\d+)?)", text)

        if match:
            number = match.group(1)
            start, end = match.span()
            
            before_text = text[:start].strip()
            after_text = text[end:].strip()
            
            for symbol in CURRENCY_SYMBOLS:
                if symbol in before_text or symbol in after_text:
                    return True
            
            for code in CURRENCY_CODES:
                if code in before_text.split() or code in after_text.split():
                    return True
    return False

def contains_price(text):
    text = text.strip()
    price_pattern = r"""
        (?:  
            (?:€|\$|₺|£|¥|TL)\s?[\d]+(?:[.,]\d+)?  
            |  
            [\d]+(?:[.,]\d+)?\s?(?:€|\$|₺|£|¥|TL)  
            |  
            [\d]+(?:[.,]\d+)(?:\s?[^\w\s])?  
        )
    """
    if re.search(price_pattern, text, re.VERBOSE | re.IGNORECASE):
        return True
    words = text.split()
    for i, word in enumerate(words):
        if word.replace(",", "").replace(".", "").isdigit():
            if i + 1 < len(words) and words[i + 1] in ['€', '$', '₺', '£', '¥', 'TL']:
                return True
    return False

def contains_unit(text):
    return bool(re.search(r"\b\d+(\.\d+)?\s?(g|kg|ml|l|pcs|unit|x)?\b", text, re.IGNORECASE))

def contains_image(element):
    return element.find("img") is not None

def is_valid_product(element):
    text_content = element.get_text().lower()
    has_price = contains_price(text_content)
    has_unit = contains_unit(text_content)
    has_image = contains_image(element)
    return has_price and has_unit and has_image

def find_minimal_product_containers(soup):
    product_candidates = [el for el in soup.find_all(True) if is_valid_product(el)]
    minimal_products = []
    for candidate in product_candidates:
        if not any(is_valid_product(child) for child in candidate.find_all(True, recursive=False)):
            minimal_products.append(candidate)
    return minimal_products

def fetch_page_with_js(url):
    chrome_options = Options()
    #chrome_options.add_argument("--headless")  # run in headless mode
    service = Service("chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(url)
    
    time.sleep(10)
    
    html = driver.page_source
    driver.quit()
    return html

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form["url"]
        try:
            html_content = fetch_page_with_js(url)
            products = find_minimal_product_containers(BeautifulSoup(html_content, "html.parser"))
            
            session.clear()
            session.permanent = True
            session['url'] = url
            session['products_count'] = len(products)
            
            os.makedirs('temp_data', exist_ok=True)
            
            with open(f'temp_data/{session.sid}_content.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            products_html = []
            for i, product in enumerate(products):
                product_html = str(product)
                products_html.append(product_html)
                with open(f'temp_data/{session.sid}_product_{i}.html', 'w', encoding='utf-8') as f:
                    f.write(product_html)
            
            flash("Products fetched successfully!", "success")
            return render_template("index.html", 
                                products=products_html,
                                url=url)
            
        except Exception as e:
            flash(f"Error fetching products: {str(e)}", "error")
    
    return render_template("index.html", products=[], url="")

@app.route("/save_labels", methods=["POST"])
def save_labels():
    if 'products_count' not in session:
        flash("Session expired. Please fetch again.", "error")
        return redirect(url_for('index'))

    try:
        with open(f'temp_data/{session.sid}_content.html', 'r', encoding='utf-8') as f:
            html_content = f.read()

        products = []
        for i in range(session['products_count']):
            with open(f'temp_data/{session.sid}_product_{i}.html', 'r', encoding='utf-8') as f:
                products.append(f.read())

        labels = [int(request.form.get(f"label_{i+1}", 0)) for i in range(session['products_count'])]

        conn = None
        cursor = None
        try:
            conn = create_db_connection()
            if not conn:
                raise Exception("Could not connect to database")

            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    url VARCHAR(255) NOT NULL,
                    html_content LONGTEXT NOT NULL,
                    product_detected TEXT,
                    label INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            insert_query = """
                INSERT INTO train_data 
                (url, html_content, product_detected, label) 
                VALUES (%s, %s, %s, %s)
            """
            
            for product, label in zip(products, labels):
                cursor.execute(insert_query, 
                             (session['url'], html_content, product, label))
                print(f"Inserted product with label {label}")
            
            conn.commit()
            print("Transaction committed successfully")
            flash("Labels saved successfully!", "success")

        except Error as e:
            if conn:
                conn.rollback()
            print(f"Database error: {e}")
            flash(f"Database error: {str(e)}", "error")
            return redirect(url_for('index'))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Unexpected error: {e}")
            flash(f"Error saving labels: {str(e)}", "error")
            return redirect(url_for('index'))
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        for i in range(session['products_count']):
            try:
                os.remove(f'temp_data/{session.sid}_product_{i}.html')
            except FileNotFoundError:
                pass
                
        try:
            os.remove(f'temp_data/{session.sid}_content.html')
        except FileNotFoundError:
            pass

        session.clear()
        return redirect(url_for('index'))

    except Exception as e:
        print(f"Overall error: {e}")
        flash(f"Error processing labels: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route("/session_test")
def session_test():
    session['test_key'] = 'test_value'
    session.modified = True
    return f"Session test - contains: {list(session.keys())}"

@app.route("/db_test")
def db_test():
    conn = create_db_connection()
    if conn:
        conn.close()
        return "Database connection works"
    return "Database connection failed"

if __name__ == "__main__":
    os.makedirs('flask_session', exist_ok=True)
    os.makedirs('temp_data', exist_ok=True)
    
    test_conn = create_db_connection()
    if test_conn:
        test_conn.close()
        print("Database connection verified")
    else:
        print("Could not verify database connection")
    
    app.run(debug=True)