import json
import base64
import requests
import pandas as pd
from io import BytesIO, StringIO
import os
import re
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

# -----------------------------------
# AIPIPE Configuration
# -----------------------------------
AIPIPE_TOKEN = os.environ.get("AIPIPE_TOKEN")

if not AIPIPE_TOKEN:
    raise ValueError("AIPIPE_TOKEN environment variable is required")

client = OpenAI(
    api_key=AIPIPE_TOKEN,
    base_url="https://aipipe.org/openai/v1"
)

# -----------------------------------
# Call AI model with better error handling
# -----------------------------------
def call_ai(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model="gpt-4",  # Using GPT-4 for better reasoning
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"AIPIPE API error (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                return None
            import time
            time.sleep(2)

# -----------------------------------
# Extract information from quiz instructions
# -----------------------------------
def parse_quiz_instructions(instructions):
    """
    Extract key information from quiz instructions
    """
    # Look for file URLs to download
    file_urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+\.(csv|json|pdf|txt|xlsx|xls)', instructions, re.IGNORECASE)
    
    # Look for submit URL
    submit_urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+submit[^\s<>"{}|\\^`\[\]]*', instructions, re.IGNORECASE)
    submit_url = submit_urls[0] if submit_urls else None
    
    # Look for question type
    question_type = "unknown"
    if any(word in instructions.lower() for word in ["sum", "total", "add", "calculate", "average", "count"]):
        question_type = "calculation"
    elif any(word in instructions.lower() for word in ["download", "file", "extract", "parse"]):
        question_type = "file_processing"
    elif any(word in instructions.lower() for word in ["scrape", "extract", "find", "what", "where"]):
        question_type = "information_extraction"
    elif any(word in instructions.lower() for word in ["visualize", "chart", "graph", "plot"]):
        question_type = "visualization"
    
    return {
        "file_urls": file_urls,
        "submit_url": submit_url,
        "question_type": question_type,
        "cleaned_instructions": instructions
    }

# -----------------------------------
# Download and process files based on instructions
# -----------------------------------
def process_files_from_instructions(instructions):
    """
    Download and parse files mentioned in quiz instructions
    """
    file_urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+\.(csv|json|pdf|txt|xlsx|xls)', instructions, re.IGNORECASE)
    
    processed_files = []
    
    for url in file_urls[:3]:  # Limit to first 3 files to avoid timeouts
        try:
            logger.info(f"Downloading file: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            content = response.content
            file_info = {
                "url": url,
                "content_type": response.headers.get('content-type', 'unknown'),
                "size": len(content),
                "base64_preview": base64.b64encode(content).decode('utf-8')[:200] + "..." if len(content) > 200 else base64.b64encode(content).decode('utf-8')
            }
            
            # Try to parse based on file type
            if url.endswith('.csv'):
                try:
                    df = pd.read_csv(BytesIO(content))
                    file_info["preview"] = df.head(3).to_dict(orient='records')
                    file_info["columns"] = df.columns.tolist()
                    file_info["shape"] = df.shape
                    file_info["dtypes"] = df.dtypes.astype(str).to_dict()
                except Exception as e:
                    file_info["parse_error"] = str(e)
                    file_info["preview"] = "Could not parse CSV"
                    
            elif url.endswith('.json'):
                try:
                    data = response.json()
                    if isinstance(data, list):
                        file_info["preview"] = data[:3] if len(data) > 3 else data
                    elif isinstance(data, dict):
                        file_info["preview"] = {k: data[k] for k in list(data.keys())[:3]}
                    else:
                        file_info["preview"] = str(data)[:500]
                    file_info["type"] = type(data).__name__
                except:
                    file_info["preview"] = "Invalid JSON"
            
            elif url.endswith('.txt'):
                try:
                    text_content = response.text[:1000]  # First 1000 chars
                    file_info["preview"] = text_content
                except:
                    file_info["preview"] = "Could not read text"
            
            processed_files.append(file_info)
            
        except Exception as e:
            logger.error(f"Error processing file {url}: {e}")
            processed_files.append({"url": url, "error": str(e)})
    
    return processed_files

# -----------------------------------
# Solve different types of quizzes
# -----------------------------------
def solve_with_ai(instructions, files, question_type, submit_url):
    """
    Unified AI solver with specific prompting for different question types
    """
    
    if question_type == "calculation":
        task_specific = """
You are solving a DATA CALCULATION question. Carefully analyze any data files provided and perform the required calculations.
Focus on numerical accuracy and ensure you're calculating exactly what's asked (sum, average, count, etc.).
"""
    elif question_type == "file_processing":
        task_specific = """
You are solving a FILE PROCESSING question. Extract and process information from the provided files.
Pay attention to file formats and extract the specific information requested.
"""
    elif question_type == "visualization":
        task_specific = """
You are solving a VISUALIZATION question. While you can't generate actual images, describe what visualization would answer the question.
Provide the data or parameters needed for the visualization.
"""
    else:
        task_specific = """
You are solving an INFORMATION EXTRACTION question. Find the specific information requested in the instructions.
Be precise and provide exact answers.
"""

    prompt = f"""
You are an expert quiz solver for IITM TDS LLM Analysis project. {task_specific}

QUIZ INSTRUCTIONS:
{instructions}

AVAILABLE DATA FILES:
{json.dumps(files, indent=2)}

SUBMIT URL: {submit_url}

Analyze the instructions and available data carefully. Provide your answer in the exact format required.

Return ONLY a valid JSON object with this exact structure:
{{
    "answer": "the calculated answer (number, string, boolean, or base64 for files)",
    "reasoning": "brief explanation of how you arrived at the answer",
    "submit_url": "{submit_url if submit_url else 'extract from instructions if missing'}"
}}

IMPORTANT GUIDELINES:
1. If the answer is a number, return it as a number (not string)
2. If the answer requires file processing, provide the extracted information
3. For visualization questions, provide the key insight or data needed
4. Always include the submit_url
5. Be precise and accurate in your calculations

Think step by step but return only the JSON.
"""

    return call_ai(prompt)

# -----------------------------------
# Main AI Solver
# -----------------------------------
def solve_quiz_with_ai(quiz_data):
    """
    Main function to solve quizzes using AI
    """
    try:
        instructions = quiz_data.get("instructions", "")
        html_content = quiz_data.get("html_content", "")
        submit_url = quiz_data.get("submit_url", "")
        
        logger.info(f"Solving quiz with instructions: {instructions[:200]}...")
        
        # Parse instructions to understand what's needed
        parsed_info = parse_quiz_instructions(instructions)
        
        # Use extracted submit URL if available
        if not submit_url and parsed_info["submit_url"]:
            submit_url = parsed_info["submit_url"]
        
        # Process any files mentioned in instructions
        processed_files = process_files_from_instructions(instructions)
        
        # Solve with AI
        ai_response = solve_with_ai(
            instructions, 
            processed_files, 
            parsed_info["question_type"],
            submit_url
        )
        
        if not ai_response:
            logger.error("AIPIPE returned no response")
            return None
        
        # Parse AI response
        try:
            # Extract JSON from response
            start = ai_response.find('{')
            end = ai_response.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = ai_response[start:end]
                result = json.loads(json_str)
                
                # Ensure submit_url is included
                if not result.get("submit_url") and submit_url:
                    result["submit_url"] = submit_url
                
                logger.info(f"AI solution: {result}")
                return result
            else:
                logger.error(f"No JSON found in AI response: {ai_response}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"AI response was: {ai_response}")
            
            # Fallback: try to extract just the answer
            try:
                return {
                    "answer": ai_response.strip(),
                    "reasoning": "Fallback - could not parse JSON",
                    "submit_url": submit_url
                }
            except:
                return None
            
    except Exception as e:
        logger.error(f"Error in solve_quiz_with_ai: {e}")
        return None

# -----------------------------------
# Fallback solver for simple cases
# -----------------------------------
def simple_solver(instructions):
    """
    Simple rule-based solver as fallback
    """
    instructions_lower = instructions.lower()
    
    # Simple pattern matching for demo purposes
    if "demo" in instructions_lower and "sum" in instructions_lower:
        return {
            "answer": 42,  # Example answer for demo
            "reasoning": "Used simple solver for demo question",
            "submit_url": "https://tds-llm-analysis.s-anand.net/submit"
        }
    
    return None
