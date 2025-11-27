from flask import Flask, request, jsonify
import os
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import base64
import traceback
from urllib.parse import urljoin, urlparse
import mimetypes
from io import BytesIO
import PyPDF2
import pandas as pd
from bs4 import BeautifulSoup
from openai import OpenAI

# ---------------- AI PIPE CONFIG ----------------
client = OpenAI(
    api_key=os.environ.get("AIPIPE_TOKEN"),
    base_url="https://aipipe.org/openai/v1"
)

app = Flask(__name__)

YOUR_EMAIL = os.environ.get("STUDENT_EMAIL", "your-email@example.com")
YOUR_SECRET = os.environ.get("STUDENT_SECRET", "your-secret-string")

# ---------------- BROWSER UTIL ----------------
def get_browser():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    paths = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable"
    ]
    
    for path in paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    
    return webdriver.Chrome(options=chrome_options)

# ---------------- HTML & FILE UTIL ----------------
def extract_all_links_from_html(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = []

    for tag in soup.find_all(['a', 'source', 'audio', 'video']):
        href = tag.get('href') or tag.get('src')
        if href:
            full_url = urljoin(base_url, href)
            links.append({
                'url': full_url,
                'text': tag.get_text(strip=True) or tag.name,
                'type': tag.name
            })
    return links

def fetch_quiz_page(url):
    driver = None
    try:
        driver = get_browser()
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
        text = driver.find_element(By.TAG_NAME, "body").text
        links = extract_all_links_from_html(html, url)
        return {"html": html, "text": text, "url": url, "all_links": links}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def detect_file_type(url, content_bytes=None):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    type_map = {
        '.pdf': 'pdf', '.csv': 'csv', '.xlsx': 'excel', '.xls': 'excel',
        '.txt': 'text', '.mp3': 'audio', '.wav': 'audio', '.ogg': 'audio',
        '.mp4': 'video', '.avi': 'video', '.mov': 'video',
        '.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.gif': 'image'
    }
    if ext in type_map: return type_map[ext]
    if content_bytes:
        mime = mimetypes.guess_type(url)[0]
        if mime:
            if 'audio' in mime: return 'audio'
            if 'video' in mime: return 'video'
            if 'image' in mime: return 'image'
            if 'pdf' in mime: return 'pdf'
    return 'unknown'

def process_pdf(pdf_bytes):
    try:
        pdf_file = BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        all_text = [f"[Page {i+1}]\n{p.extract_text()}" for i, p in enumerate(pdf_reader.pages)]
        return "\n\n".join(all_text)
    except Exception as e:
        return None

def process_csv(csv_bytes):
    try:
        df = pd.read_csv(BytesIO(csv_bytes))
        return {
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "head": df.head(10).to_dict('records'),
            "describe": df.describe().to_dict()
        }
    except Exception as e:
        return None

def download_and_process_file(url):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        content = r.content
        ftype = detect_file_type(url, content)
        result = {"url": url, "type": ftype, "size": len(content), "raw_base64": base64.b64encode(content).decode('utf-8')}
        if ftype == 'pdf': result['text'] = process_pdf(content)
        elif ftype == 'csv': result['csv_summary'] = process_csv(content)
        elif ftype == 'text': result['text'] = content.decode('utf-8', errors='ignore')
        return result
    except Exception as e:
        return None

# ---------------- AI UTIL ----------------
def call_ai(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0
            )
            return resp.choices[0].message.content
        except Exception as e:
            if attempt == max_retries - 1: raise
            time.sleep(2)
    return None

def solve_quiz_with_ai(quiz_data):
    context = "\n".join([quiz_data['text']] + [f"[{l['type']}] {l['url']}" for l in quiz_data.get('all_links', [])])
    prompt = f"""
You are a data analyst. Solve the quiz:

{context}

Return JSON ONLY: {{
  "submit_url": "...",
  "reasoning": "...",
  "answer": null,
  "files_needed": ["..."]
}}
"""
    response = call_ai(prompt)
    if not response: return None
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return None

def submit_answer(submit_url, email, secret, quiz_url, answer):
    try:
        r = requests.post(submit_url, json={"email": email, "secret": secret, "url": quiz_url, "answer": answer}, timeout=30)
        return r.json()
    except Exception as e:
        return {"correct": False, "reason": str(e)}

# ---------------- FLASK ENDPOINTS ----------------
@app.route('/quiz', methods=['POST'])
def handle_quiz():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Invalid JSON"}), 400
        if data.get("secret") != YOUR_SECRET: return jsonify({"error": "Invalid secret"}), 403
        if data.get("email") != YOUR_EMAIL: return jsonify({"error": "Invalid email"}), 403
        url = data.get("url")
        if not url: return jsonify({"error": "No URL provided"}), 400

        quiz_data = fetch_quiz_page(url)
        solution = solve_quiz_with_ai(quiz_data)
        if not solution: return jsonify({"error": "Failed AI processing"}), 500

        submit_result = submit_answer(solution["submit_url"], YOUR_EMAIL, YOUR_SECRET, url, solution["answer"])
        return jsonify({"status": "completed", "quiz_result": submit_result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/', methods=['GET'])
def index():
    return jsonify({"service": "LLM Quiz Solver", "status": "running"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
