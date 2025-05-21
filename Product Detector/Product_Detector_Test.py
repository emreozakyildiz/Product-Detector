import os
import joblib
import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# Load the saved model
loaded_model = joblib.load('random_forest_product_model.pkl')
print("Loaded the saved model.")

# Helper functions (contains_price, contains_unit, contains_image, is_valid_product, find_minimal_product_containers)

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

# Selenium setup to load the URL
def visit_page(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Optional: Run in headless mode
    service = Service("chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    driver.get(url)
    time.sleep(5)  # Allow time for the page to load
    
    html = driver.page_source
    driver.quit()
    
    return html

# Function to process each URL
def process_url(url):
    html = visit_page(url)
    
    # Parse HTML using BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find minimal product containers
    products = find_minimal_product_containers(soup)
    
    return products

# Function to extract product details as HTML for grid display
def extract_product_html(product):
    # Here, we extract the inner HTML of the product to display it
    product_html = str(product)
    
    return product_html

# Function to create an HTML page with the grid layout
def create_html_grid(products):
    # Create the header of the HTML page with basic styles for grid
    html_content = '''
    <html>
        <head>
            <style>
                .product-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                    gap: 20px;
                    padding: 20px;
                }
                .product-item {
                    border: 1px solid #ddd;
                    padding: 10px;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                }
                .product-item img {
                    max-width: 100%;
                    height: auto;
                }
                .product-item .product-name {
                    font-size: 16px;
                    font-weight: bold;
                    margin-top: 10px;
                }
                .product-item .product-price {
                    font-size: 14px;
                    color: green;
                }
            </style>
        </head>
        <body>
            <h1>True Labeled Products</h1>
            <div class="product-grid">
    '''
    
    # Add product HTML to the grid
    for product in products:
        product_html = extract_product_html(product)
        html_content += f'<div class="product-item">{product_html}</div>'

    # Close the grid and HTML tags
    html_content += '''
            </div>
        </body>
    </html>
    '''
    
    return html_content

# Read URLs from seeds.txt
with open('seeds.txt', 'r') as file:
    urls = file.readlines()

# Process each URL and collect true labeled products
all_true_labeled_products = []

for url in urls:
    url = url.strip()  # Clean up the URL
    print(f"Processing URL: {url}")
    
    # Process URL and get products
    products = process_url(url)
    
    # Here you need to filter the true labeled products (you should have the ground truth label)
    # For now, let's just assume that we are collecting all the products
    all_true_labeled_products.extend(products)

# Create the HTML content with true labeled products
html_grid_content = create_html_grid(all_true_labeled_products)

# Save the HTML to a file
output_html_file = "true_labeled_products.html"
with open(output_html_file, 'w', encoding='utf-8') as f:
    f.write(html_grid_content)

print(f"HTML page with labeled products has been saved to {output_html_file}")
