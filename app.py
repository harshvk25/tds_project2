import os
import json
import time
import requests
from flask import Flask, request, jsonify
from quiz_solver import solve_quiz_with_ai
from playwright.sync_api import sync_playwright
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# -----------------------------------
# Load environment variables
# -----------------------------------
STUDENT_EMAIL = os.environ.get("STUDENT_EMAIL")
STUDENT_SECRET = os.environ.get("STUDENT_SECRET")

# Validate required environment variables
if not STUDENT_EMAIL or not STUDENT_SECRET:
    logger.error("Missing required environment variables: STUDENT_EMAIL and STUDENT_SECRET must be set")

# -----------------------------------
# Fetch and render quiz page with JavaScript
# -----------------------------------
def fetch_quiz_page(url):
    """
    Use Playwright to render JavaScript-heavy quiz pages
    """
    try:
        with sync_playwright() as p:
            # Launch browser in headless mode for Docker
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set longer timeout for slow pages
            page.set_default_timeout(30000)
            
            # Navigate to the quiz URL
            page.goto(url, wait_until="networkidle")
            
            # Wait for content to load
            page.wait_for_timeout(3000)
            
            # Get the fully rendered HTML
            content = page.content()
            
            browser.close()
            logger.info(f"Successfully fetched quiz page: {url}")
            return content
    except Exception as e:
        logger.error(f"Error fetching quiz page {url}: {e}")
        return None

# -----------------------------------
# Extract quiz instructions and submit URL
# -----------------------------------
def parse_quiz_content(html_content):
    """
    Parse the rendered HTML to extract quiz instructions and submit URL
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract text content - this will contain the quiz instructions
        text_content = soup.get_text(separator='\n', strip=True)
        
        # Look for submit URL in the content (common patterns)
        submit_url = None
        
        # Method 1: Look for JSON payload in the text that contains submit URL
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text_content)
        
        # Prioritize URLs that look like submit endpoints
        for url in urls:
            if 'submit' in url.lower():
                submit_url = url
                break
        
        # If no submit URL found, use the first URL that's not the quiz URL
        if not submit_url and urls:
            submit_url = urls[0]
        
        return {
            "instructions": text_content,
            "submit_url": submit_url,
            "html_content": html_content
        }
    except Exception as e:
        logger.error(f"Error parsing quiz content: {e}")
        return None

# -----------------------------------
# Submit answer to the target URL
# -----------------------------------
def submit_answer(submit_url, answer_data):
    """
    Submit the final answer to the specified endpoint
    """
    try:
        response = requests.post(
            submit_url,
            json=answer_data,
            timeout=30
        )
        logger.info(f"Submitted answer to {submit_url}, status: {response.status_code}")
        return response.json()
    except Exception as e:
        logger.error(f"Error submitting answer to {submit_url}: {e}")
        return {"error": str(e)}

# -----------------------------------
# Main Quiz Endpoint
# -----------------------------------
@app.route("/quiz", methods=["POST"])
def quiz():
    start_time = time.time()
    
    # Validate request
    if not request.is_json:
        return jsonify({"error": "Invalid JSON"}), 400
    
    body = request.get_json()
    
    # Validate required fields
    required_fields = ["email", "secret", "url"]
    for field in required_fields:
        if field not in body:
            return jsonify({"error": f"Missing field: {field}"}), 400
    
    # Authenticate
    if body["email"] != STUDENT_EMAIL or body["secret"] != STUDENT_SECRET:
        return jsonify({"error": "Invalid email or secret"}), 403
    
    quiz_url = body["url"]
    logger.info(f"Processing quiz URL: {quiz_url}")
    
    try:
        # Step 1: Fetch and render the quiz page
        html_content = fetch_quiz_page(quiz_url)
        if not html_content:
            return jsonify({"error": "Failed to fetch quiz page"}), 500
        
        # Step 2: Parse quiz content
        quiz_data = parse_quiz_content(html_content)
        if not quiz_data:
            return jsonify({"error": "Failed to parse quiz content"}), 500
        
        # Step 3: Use AI to solve the quiz
        ai_solution = solve_quiz_with_ai(quiz_data)
        if not ai_solution:
            return jsonify({"error": "AI failed to solve quiz"}), 500
        
        # Step 4: Prepare answer payload
        answer_payload = {
            "email": STUDENT_EMAIL,
            "secret": STUDENT_SECRET,
            "url": quiz_url,
            "answer": ai_solution.get("answer")
        }
        
        # Add any additional fields the AI might have generated
        if "additional_fields" in ai_solution:
            answer_payload.update(ai_solution["additional_fields"])
        
        # Step 5: Submit answer
        submit_url = quiz_data.get("submit_url") or ai_solution.get("submit_url")
        if not submit_url:
            return jsonify({"error": "No submit URL found"}), 500
        
        submission_result = submit_answer(submit_url, answer_payload)
        
        # Check if we're within time limit
        elapsed_time = time.time() - start_time
        if elapsed_time > 170:  # 170 seconds for safety margin
            return jsonify({"error": "Approaching timeout limit", "elapsed_time": elapsed_time}), 500
        
        return jsonify({
            "status": "completed",
            "submission_result": submission_result,
            "time_elapsed": round(elapsed_time, 2),
            "quiz_instructions_preview": quiz_data["instructions"][:200] + "..." if len(quiz_data["instructions"]) > 200 else quiz_data["instructions"]
        })
        
    except Exception as e:
        logger.error(f"Unexpected error in quiz endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/")
def home():
    return "Quiz solver is running."

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "quiz_solver"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
