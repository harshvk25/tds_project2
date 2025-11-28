import os
import json
import time
import requests
from flask import Flask, request, jsonify
from quiz_solver import solve_quiz_with_ai

app = Flask(__name__)

# -----------------------------------
# Load environment variables
# -----------------------------------
STUDENT_EMAIL = os.environ.get("STUDENT_EMAIL")
STUDENT_SECRET = os.environ.get("STUDENT_SECRET")

# -----------------------------------
# Fetch quiz JSON (correct method)
# -----------------------------------
def fetch_quiz(url):
    try:
        resp = requests.post(
            "https://tds-llm-analysis.s-anand.net/submit",
            json={
                "email": STUDENT_EMAIL,
                "secret": STUDENT_SECRET,
                "url": url,
                "answer": "init"
            },
            timeout=30
        )
        return resp.json()
    except Exception as e:
        print("QUIZ FETCH ERROR:", e)
        return None

# -----------------------------------
# Main Quiz Endpoint
# -----------------------------------
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
        return jsonify({"error": "Missing field url"}), 400

    quiz_data = fetch_quiz(url)
    if not quiz_data:
        return jsonify({"error": "Quiz fetch failed"}), 400

    ai_output = solve_quiz_with_ai(quiz_data)
    if not ai_output:
        return jsonify({"error": "AI failed"}), 500

    # Ensure under 3 minutes
    if time.time() - start > 180:
        return jsonify({"error": "Timeout exceeded"}), 500

    # Submit final answer
    try:
        submit_resp = requests.post(
            ai_output["submit_url"],
            json=ai_output,
            timeout=20
        )
        submit_data = submit_resp.json()
    except Exception as e:
        submit_data = {"error": "Submission failed", "details": str(e)}

    return jsonify({
        "status": "completed",
        "quiz_result": submit_data,
        "ai_output": ai_output
    })


@app.route("/")
def home():
    return "Quiz solver is running."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
