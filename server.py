from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import json
import re
import hashlib
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive"
}
    
def extract_json_section(text, key):
    """Extracts a JSON-like section from text based on the provided key."""
    match = re.search(rf'"{key}"\s*:\s*\{{', text)
    if not match:
        return None
    
    start, brace_count, end = match.start(), 0, match.start()
    for i in range(start, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    return text[start:end]

@app.route('/scrape', methods=['GET'])
def scrape():
    url = request.args.get('url')
    if not url:
        logging.warning("⚠️ No URL provided in request")
        return jsonify({'error': 'No URL provided'}), 400
    
    logging.info(f"🔄 Processing URL: {url}")
    
    try:
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        product_title = soup.select_one("#productTitle").get_text(strip=True)
        
        price_div = soup.select_one('.priceToPay')
        price = (price_div.select_one('.a-price-symbol').get_text(strip=True) +
                 price_div.select_one('.a-price-whole').get_text(strip=True) +
                 ('.' + price_div.select_one('.a-price-fraction').get_text(strip=True) if price_div.select_one('.a-price-fraction') else ''))
        
        discount = soup.select_one('.savingsPercentage')
        discount_text = discount.get_text(strip=True) if discount else "No discount"
        
        mrp = soup.select_one('.basisPrice span.a-offscreen')
        mrp_text = mrp.get_text(strip=True) if mrp else "MRP not found"

        script_tag = next((script.text for script in soup.find_all("script") if "var data" in script.text), None)
        if script_tag:
            match = re.search(r'var data = (\{.*?\});', script_tag, re.DOTALL)
            if match:
                json_text = match.group(1)
                json_text = json_text.replace("'", '"')
                json_text = re.sub(r"(\{|,)\s*'([^']+)'\s*:", r'\1 "\2":', json_text)
                json_text = re.sub(r",\s*([}\]])", r"\1", json_text)
                json_text = extract_json_section(json_text, "colorImages")
                json_text = "{" + json_text + "}"
                try:
                    data = json.loads(json_text)
                    color_images = data.get("colorImages", {}).get("initial", [])
                    image_urls = [img.get("hiRes") for img in color_images if "hiRes" in img]
                    logging.info(f"✅ Successfully scraped product: {product_title}")
                    return jsonify({'title': product_title, 'price': 'price', 'discount': discount_text, 'mrp': mrp_text, 'images': image_urls})
                except json.JSONDecodeError:
                    logging.error("❌ JSON parsing error, returning product details with default image")
        else:
            logging.error("❌ No valid JSON data found in script tag")
    
    except Exception as e:
        logging.exception("❌ Unexpected error occurred")
    
    logging.info("⚠️ Returning product details with default image due to errors")
    return jsonify({'title': product_title, 'price': price, 'discount': discount_text, 'mrp': mrp_text, 'images': []})
    
if __name__ == '__main__':
    logging.info("🚀 Scraper server is starting...")
    app.run(host="0.0.0.0", port=5000, debug=True)
