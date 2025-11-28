import os
import json
import requests
import pandas as pd
from flask import Flask, request, jsonify
from openai import OpenAI
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
    base_url="https://aipipe.org/openai/v1"
)

# ---------------------------
# Helper: call AI
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
# Fetch quiz (NO PLAYWRIGHT)
# ---------------------------
def fetch_quiz(url):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("Error fetching quiz:", e)
        return None

# ---------------------------
# Download & parse files
# ---------------------------
def download_and_parse_files(files_needed):
    parsed = []
    for f in files_needed:
        try:
            resp = requests.get(f["url"], timeout=30)
            resp.raise_for_status()
            content_bytes = resp.content
            encoded = base64.b64encode(content_bytes).decode()

            preview = None
            try:
                df = pd.read_csv(BytesIO(content_bytes))
                preview = df.head().to_dict(orient="records")
            except:
                try:
                    preview = json.loads(content_bytes.decode("utf-8"))
                except:
                    preview = None

            parsed.append({
                "filename": f.get("filename", "unknown"),
                "content_base64": encoded,
                "type": f.get("type", "unknown"),
                "parsed_preview": preview
            })
        except Exception as e:
            print("File download error:", e)

    return parsed

# ---------------------------
# AI Quiz Solver
# ---------------------------
def solve_quiz_with_ai(quiz_data):
    context = "\n".join(
        [quiz_data.get("text", "")] +
        [f"[{l['type']}] {l['url']}" for l in quiz_data.get("all_links", [])]
    )

    files_needed = quiz_data.get("files_needed", [])
    parsed_files = download_and_parse_files(files_needed)

    files_text = "\n".join([
        f"{f['filename']} (base64): {f['content_base64'][:100]}..., preview: {f['parsed_preview']}"
        for f in parsed_files
    ])

    prompt = f"""
You are an AI that solves IITM LLM quiz questions.
Return JSON ONLY — no markdown or text outside JSON.

{{ 
  "submit_url": "",
  "reasoning": "",
  "answer": "",
  "files_needed": []
}}

Quiz content:
{context}

Files:
{files_text}
"""

    response = call_ai(prompt)
    if not response:
        return None

    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except:
        return None

# ---------------------------
# Main Quiz Endpoint
# ---------------------------
@app.route("/quiz", methods=["POST"])
def quiz():
    start = time.time()
    body = request.json

    if not body:
        return jsonify({"error": "Invalid JSON"}), 400

    if body.get("email") != STUDENT_EMAIL or body.get("secret") != STUDENT_SECRET:
        return jsonify({"error": "Invalid email or secret"}), 403

    url = body.get("url")
    if not url:
        return jsonify({"error": "Missing url"}), 400

    quiz_data = fetch_quiz(url)
    if not quiz_data:
        return jsonify({"error": "Failed to fetch quiz"}), 400

    ai_result = solve_quiz_with_ai(quiz_data)
    if not ai_result:
        return jsonify({"error": "AI failed"}), 500

    if time.time() - start > 180:
        return jsonify({"error": "Timeout > 3 minutes"}), 500

    try:
        submit_resp = requests.post(ai_result["submit_url"], json=ai_result, timeout=30)
        submit_data = submit_resp.json()
    except Exception as e:
        submit_data = {"error": "Submission failed", "details": str(e)}

    return jsonify({
        "status": "completed",
        "quiz_result": submit_data,
        "ai_output": ai_result
    })

@app.route("/")
def home():
    return "Quiz solver is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
