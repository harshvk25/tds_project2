import json
import base64
import requests
import pandas as pd
from io import BytesIO
import os
from openai import OpenAI

API_KEY = os.environ.get("AIPIPE_TOKEN")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://aipipe.org/openai/v1"
)

# -----------------------------------
# Call AI model
# -----------------------------------
def call_ai(prompt):
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return resp.choices[0].message.content
    except Exception as e:
        print("AI ERROR:", e)
        return None

# -----------------------------------
# Download and parse files
# -----------------------------------
def download_and_parse_files(files_needed):
    parsed = []

    for f in files_needed:
        try:
            r = requests.get(f["url"], timeout=20)
            r.raise_for_status()

            raw = r.content
            encoded = base64.b64encode(raw).decode("utf-8")

            preview = None
            try:
                df = pd.read_csv(BytesIO(raw))
                preview = df.head(10).to_dict(orient="records")
            except:
                try:
                    preview = json.loads(raw.decode("utf-8"))
                except:
                    preview = None

            parsed.append({
                "filename": f["filename"],
                "content_base64": encoded,
                "type": f["type"],
                "preview": preview
            })

        except Exception as e:
            print("FILE ERROR:", f["url"], e)

    return parsed

# -----------------------------------
# Main AI Solver
# -----------------------------------
def solve_quiz_with_ai(quiz):
    files_needed = quiz.get("files_needed", [])
    parsed_files = download_and_parse_files(files_needed)

    context = quiz.get("text", "")
    link_list = quiz.get("all_links", [])

    links_str = "\n".join([f"- {x['type']}: {x['url']}" for x in link_list])

    files_text = "\n".join([
        f"{f['filename']} (base64 first 100 chars): {f['content_base64'][:100]} preview={f['preview']}"
        for f in parsed_files
    ])

    prompt = f"""
You solve IITM TDS LLM quizzes. Return ONLY valid JSON. No markdown.

Quiz text:
{context}

Links:
{links_str}

Files:
{files_text}

Return JSON exactly as:

{{
  "submit_url": "{quiz.get('submit_url', '')}",
  "reasoning": "",
  "answer": "your best answer",
  "files_needed": []
}}
"""

    raw = call_ai(prompt)
    if not raw:
        return None

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        print("JSON PARSE ERROR", e)
        return None
