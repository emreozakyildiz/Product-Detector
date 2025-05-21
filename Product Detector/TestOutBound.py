import os
import uuid
import requests
from bs4 import BeautifulSoup
import joblib
import numpy as np
import scipy.sparse as sp

# Load vectorizer and models
vectorizer = joblib.load('tfidf_vectorizer.pkl')
models = {
    'Random Forest': joblib.load('random_forest_product_model.pkl'),
    'AdaBoost': joblib.load('adaboost_product_model.pkl'),
    'Linear SVC': joblib.load('linear_svc_product_model.pkl'),
    'XGBoost': joblib.load('xgboost_product_model.pkl'),
}

def get_html_from_url(url):
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    return response.text if response.status_code == 200 else ''

def get_all_segments(soup):
    segments = []

    def recurse(tag):
        if isinstance(tag, str):
            return
        html = str(tag)
        text = tag.get_text(strip=True)
        if text:
            segments.append((html, text))
        for child in tag.children:
            recurse(child)

    recurse(soup.body or soup)
    return segments

def classify_segments(segments, full_page_text):
    results = {name: [] for name in models}

    # Transform the full page text once
    X_page = vectorizer.transform([full_page_text])
    X_page_repeated = sp.vstack([X_page] * len(segments))

    # Transform each tag text
    tag_texts = [text for _, text in segments]
    X_product = vectorizer.transform(tag_texts)

    # Combine like in training
    X_combined = sp.hstack([X_page_repeated, X_product])

    # Predict for each model
    for model_name, model in models.items():
        preds = model.predict(X_combined)
        results[model_name] = [html for (html, _), label in zip(segments, preds) if label == 1]

    return results

def save_results(results, output_dir='data/test_results'):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.html"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('''
<html>
<head>
<meta charset="utf-8">
<title>Model Results</title>
<style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .model-section { margin-bottom: 20px; }
    .toggle-btn {
        background: #007BFF; color: white; padding: 10px 15px;
        border: none; border-radius: 5px; cursor: pointer;
        margin-bottom: 10px;
    }
    .product-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 10px;
        display: none;
    }
    .product-card {
        border: 1px solid #ccc;
        border-radius: 10px;
        padding: 10px;
        background: #f9f9f9;
    }
</style>
<script>
function toggleGrid(id) {
    const grid = document.getElementById(id);
    grid.style.display = grid.style.display === 'grid' ? 'none' : 'grid';
}
</script>
</head>
<body>
<h1>Detected Products by Model</h1>
''')

        for i, (model, items) in enumerate(results.items()):
            section_id = f"grid_{i}"
            f.write(f'''
<div class="model-section">
    <button class="toggle-btn" onclick="toggleGrid('{section_id}')">
        {model} Found Products ({len(items)})
    </button>
    <div class="product-grid" id="{section_id}">
''')
            for item in items:
                f.write(f'<div class="product-card">{item}</div>\n')
            f.write('</div></div>\n')

        f.write('</body></html>')

def save_page_html(content, output_dir='data/test'):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}_page.html"
    path = os.path.join(output_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Page HTML saved at: {path}")
    return path

if __name__ == "__main__":
    url = input("Enter URL: ").strip()
    html = get_html_from_url(url)
    soup = BeautifulSoup(html, 'html.parser')
    save_page_html(html)
    segments = get_all_segments(soup)
    full_page_text = soup.get_text(" ", strip=True)
    results = classify_segments(segments, full_page_text)
    save_results(results)
    print("Results saved to model_results.html")

