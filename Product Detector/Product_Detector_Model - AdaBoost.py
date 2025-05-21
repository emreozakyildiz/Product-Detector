import mysql.connector
import pandas as pd
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
import os
import scipy.sparse as sp
from sklearn.model_selection import train_test_split
from sklearn.ensemble import AdaBoostClassifier
from sklearn.metrics import accuracy_score, classification_report
from tqdm import tqdm
import joblib
from concurrent.futures import ThreadPoolExecutor

db_config = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': 'anan123',
    'database': 'product_detecting',
    'autocommit': False,
}

def fetch_data_from_db():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    query = "SELECT url, page_path, product_path, label, created_at FROM train_Data;"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(rows)

def read_html_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return ""

def extract_text_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    return " ".join([element.get_text() for element in soup.find_all(['h1', 'h2', 'p', 'span', 'a'])])

def process_row(row):
    page_file = os.path.join('./data/pages', row['page_path'].split("\\")[-1])
    product_file = os.path.join('./data/products', row['product_path'].split("\\")[-1])
    page_text = extract_text_from_html(read_html_file(page_file))
    product_text = extract_text_from_html(read_html_file(product_file))
    return page_text, product_text

df = fetch_data_from_db()

print("Starting parallel HTML parsing...")
with ThreadPoolExecutor() as executor:
    results = list(tqdm(executor.map(process_row, [row for _, row in df.iterrows()]), 
                        total=len(df), 
                        desc="Processing rows",
                        unit="row"))

df['page_text'], df['product_text'] = zip(*results)
print("Parallel parsing completed.")

vectorizer = TfidfVectorizer(max_features=1000)
X_page = vectorizer.fit_transform(df['page_text'])
X_product = vectorizer.transform(df['product_text'])
X_combined = sp.hstack([X_page, X_product])

X_train, X_test, y_train, y_test = train_test_split(X_combined, df['label'], test_size=0.2, random_state=42)
model = AdaBoostClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
print("Model training complete.")

model_filename = 'adaboost_product_model.pkl'
joblib.dump(model, model_filename)
print(f"Model saved as {model_filename}")
vectorizer_filename = 'tfidf_vectorizer.pkl'
joblib.dump(vectorizer, vectorizer_filename)
print(f"Vectorizer saved as {vectorizer_filename}")

y_pred = model.predict(X_test)
print(f"Accuracy: {accuracy_score(y_test, y_pred)}")
print(f"Classification Report:\n{classification_report(y_test, y_pred)}")
