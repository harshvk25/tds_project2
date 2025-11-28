import os
import json
import requests
import pandas as pd
from flask import Flask, request, jsonify
from openai import OpenAI
from playwright.sync_api import sync_playwright
import time
import base64
from io import BytesIO

app = Flask(__name__)

# --------------------------------------
# Load environment variables from Render
# --------------------------------------
STUDENT_EMAIL = os.environ.get("STUDENT_EMAIL")
STUDENT_SECRET = os.environ.get("STUDENT_SECRET")
API_KEY = os.environ.get("AIPIPE_TOKEN")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://aipipe.org/openai/v1"
)

# --------------------------------------
# AI call
# --------------------------------------
def call_ai(prompt):
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception as e:
        print("AI ERROR:", e)
        return None

# --------------------------------------
# Fetch JS-rendered quiz page
# --------------------------------------
def fetch_quiz(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")
            content = page.evaluate("() => document.body.innerText")
            browser.close()

            try:
                return json.loads(content)
            except json.JSONDecodeError:
                print("Failed to parse JSON from page")
                return None

    except Exception as e:
        print("Playwright ERROR:", e)
        return None

# --------------------------------------
# Download needed files & prepare them
# --------------------------------------
def download_and_parse_files(files_needed):
    parsed_files = []
    for f in files_needed:
        try:
            r = requests.get(f["url"], timeout=30)
            r.raise_for_status()
            content_bytes = r.content
            encoded = base64.b64encode(content_bytes).decode("utf-8")

            parsed_preview = None
            # Try CSV
            try:
                df = pd.read_csv(BytesIO(content_bytes))
                parsed_preview = df.head(10).to_dict(orient="records")
            except:
                # Try JSON
                try:
                    parsed_preview = json.loads(content_bytes.decode())
                except:
                    parsed_preview = None

            parsed_files.append({
                "filename": f.get("filename", "unknown"),
                "type": f.get("type", "unknown"),
                "content_base64": encoded,
                "parsed_preview": parsed_preview
            })

        except Exception as e:
            print(f"File download failed: {f['url']}", e)

    return parsed_files

# --------------------------------------
# Solve quiz using AI
# --------------------------------------
def solve_quiz_with_ai(quiz):
    context = quiz.get("text", "")
    links = "\n".join(f"{l['type']}: {l['url']}" for l in quiz.get("all_links", []))

    files_needed = quiz.get("files_needed", [])
    parsed = download_and_parse_files(files_needed)

    files_text = "\n".join([
        f"{f['filename']} (preview: {f['parsed_preview']})"
        for f in parsed
    ])

    prompt = f"""
Solve the IITM LLM quiz. Return JSON only.

Quiz text:
{context}

Links:
{links}

Files:
{files_text}

Return JSON with EXACTLY these fields:

{{
  "answer": "your final answer",
  "reasoning": "why you chose it",
  "files_used": []
}}
"""

    ai = call_ai(prompt)
    if not ai:
        return None

    # Extract JSON fragment
    try:
        start = ai.find("{")
        end = ai.rfind("}") + 1
        return json.loads(ai[start:end])
    except Exception as e:
        print("JSON Parse ERROR:", e)
        return None

# --------------------------------------
# /quiz endpoint
# --------------------------------------
@app.route("/quiz", methods=["POST"])
def quiz():
    start_time = time.time()

    body = request.json
    if not body:
        return jsonify({"error": "Invalid JSON"}), 400

    # Authentication
    if body.get("email") != STUDENT_EMAIL or body.get("secret") != STUDENT_SECRET:
        return jsonify({"error": "Invalid email or secret"}), 403

    quiz_url = body.get("url")
    if not quiz_url:
        return jsonify({"error": "Missing URL"}), 400

    # Step 1: Fetch quiz
    quiz = fetch_quiz(quiz_url)
    if not quiz:
        return jsonify({"error": "Quiz fetch failed"}), 400

    # Step 2: Solve quiz
    result = solve_quiz_with_ai(quiz)
    if not result:
        return jsonify({"error": "AI solver failed"}), 500

    # Time limit
    if time.time() - start_time > 180:
        return jsonify({"error": "Timeout (3 minutes exceeded)"}), 500

    # Return final AI result only (no external submission!)
    return jsonify({
        "status": "completed",
        "ai_output": result
    })

# --------------------------------------
# Root
# --------------------------------------
@app.route("/")
def home():
    return "Quiz solver is running."

# --------------------------------------
# Run server
# --------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
