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

# ---------------------------
# Load environment variables
# ---------------------------
STUDENT_EMAIL = os.environ.get("STUDENT_EMAIL")
STUDENT_SECRET = os.environ.get("STUDENT_SECRET")
API_KEY = os.environ.get("AIPIPE_TOKEN")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://aipipe.org/openai/v1"  # For AIPipe
)

# ---------------------------
# Helper: call the AI model
# ---------------------------
def call_ai(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        print("AI ERROR:", e)
        return None

# ---------------------------
# Fetch JS-rendered quiz page
# ---------------------------
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
                print("Failed to parse JSON from page content")
                return None
    except Exception as e:
        print("Error fetching quiz:", e)
        return None

# ---------------------------
# Download & parse files
# ---------------------------
def download_and_parse_files(files_needed):
    parsed_files = []
    for f in files_needed:
        try:
            resp = requests.get(f["url"], timeout=30)
            resp.raise_for_status()
            content_bytes = resp.content
            encoded = base64.b64encode(content_bytes).decode("utf-8")

            parsed_data = None
            # Attempt CSV parsing
            try:
                df = pd.read_csv(BytesIO(content_bytes))
                parsed_data = df.head(10).to_dict(orient="records")  # Limit preview for AI
            except Exception:
                # Attempt JSON parsing
                try:
                    parsed_data = json.loads(content_bytes.decode("utf-8"))
                except Exception:
                    parsed_data = None

            parsed_files.append({
                "filename": f.get("filename", "unknown"),
                "content_base64": encoded,
                "type": f.get("type", "unknown"),
                "parsed_preview": parsed_data
            })
        except Exception as e:
            print(f"Failed to download {f['url']}: {e}")
    return parsed_files

# ---------------------------
# AI Quiz Solver
# ---------------------------
def solve_quiz_with_ai(quiz_data):
    context = "\n".join(
        [quiz_data.get('text', '')] +
        [f"[{l['type']}] {l['url']}" for l in quiz_data.get('all_links', [])]
    )

    files_needed = quiz_data.get("files_needed", [])
    parsed_files = download_and_parse_files(files_needed)

    files_text = "\n".join([
        f"{f['filename']} (base64): {f['content_base64'][:100]}..., preview: {f['parsed_preview']}"
        for f in parsed_files
    ])

    prompt = f"""
You are an AI that solves IITM LLM quiz questions.
Return JSON ONLY — no markdown, no explanation outside JSON.

STRICT RULES:
- "answer" must NEVER be null.
- Include all required fields.
- Use parsed preview data from files to compute answers.
- Return ONLY valid JSON.

Quiz content:
{context}

Files included:
{files_text}

Return JSON in EXACTLY this structure:

{{
  "submit_url": "",
  "reasoning": "",
  "answer": "your best guess",
  "files_needed": []
}}
"""

    response = call_ai(prompt)
    if not response:
        return None

    print("\n--------- RAW AI RESPONSE ---------")
    print(response)
    print("-----------------------------------\n")

    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception as e:
        print("JSON PARSE ERROR:", e)
        return None

# ---------------------------
# Main quiz endpoint
# ---------------------------
@app.route("/quiz", methods=["POST"])
def quiz():
    start_time = time.time()
    body = request.json

    if not body:
        return jsonify({"error": "Invalid JSON"}), 400

    if body.get("email") != STUDENT_EMAIL or body.get("secret") != STUDENT_SECRET:
        return jsonify({"error": "Invalid email or secret"}), 403

    url = body.get("url")
    if not url:
        return jsonify({"error": "Missing field url"}), 400

    quiz_data = fetch_quiz(url)
    if not quiz_data:
        return jsonify({"error": "Failed to fetch quiz"}), 400

    ai_result = solve_quiz_with_ai(quiz_data)
    if not ai_result:
        return jsonify({"error": "AI failed to solve quiz"}), 500

    elapsed = time.time() - start_time
    if elapsed > 180:
        return jsonify({"error": "Timeout exceeded 3 minutes"}), 500

    try:
        submit_resp = requests.post(
            ai_result["submit_url"],
            json=ai_result,
            timeout=30
        )
        submit_data = submit_resp.json()
    except Exception as e:
        submit_data = {"error": "Submission failed", "details": str(e)}

    return jsonify({
        "status": "completed",
        "quiz_result": submit_data,
        "ai_output": ai_result
    })

# ---------------------------
# Root
# ---------------------------
@app.route("/")
def home():
    return "Quiz solver is running."

# ---------------------------
# Run server
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
