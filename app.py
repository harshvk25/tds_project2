import os
import json
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# ---------------------------
# Load environment variables
# ---------------------------
STUDENT_EMAIL = os.environ.get("STUDENT_EMAIL")
STUDENT_SECRET = os.environ.get("STUDENT_SECRET")
API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("AIPIPE_TOKEN")

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
# AI Quiz Solver
# ---------------------------
def solve_quiz_with_ai(quiz_data):
    context = "\n".join(
        [quiz_data['text']] +
        [f"[{l['type']}] {l['url']}" for l in quiz_data.get('all_links', [])]
    )

    prompt = f"""
You are an AI that solves IITM LLM quiz questions.
Return JSON ONLY — no markdown, no explanation outside JSON.

STRICT RULES:
- "answer" must NEVER be null.
- If unsure, guess the best answer.
- Always include all required fields.
- Return ONLY valid JSON.

Quiz content:
{context}

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

    # Extract JSON
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception as e:
        print("JSON PARSE ERROR:", e)
        return None


# ---------------------------
# Fetch quiz from URL
# ---------------------------
def fetch_quiz(url):
    try:
        resp = requests.get(url)
        data = resp.json()
        return data
    except:
        return None


# ---------------------------
# Main quiz endpoint
# ---------------------------
@app.route("/quiz", methods=["POST"])
def quiz():
    body = request.json

    # Validate student identity
    if body.get("email") != STUDENT_EMAIL or body.get("secret") != STUDENT_SECRET:
        return jsonify({"error": "Invalid email or secret"}), 401

    url = body.get("url")
    if not url:
        return jsonify({"error": "Missing field url"}), 400

    quiz_data = fetch_quiz(url)
    if not quiz_data:
        return jsonify({"error": "Failed to fetch quiz"}), 400

    ai_result = solve_quiz_with_ai(quiz_data)
    if not ai_result:
        return jsonify({"error": "AI failed to solve quiz"}), 500

    # Submit quiz answer
    try:
        submit_resp = requests.post(
            ai_result["submit_url"],
            json=ai_result
        )
        submit_data = submit_resp.json()
    except:
        submit_data = {"error": "submission failed"}

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
