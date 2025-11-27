import json
import re
import requests
from typing import Dict, Any, Optional
import os

class QuizSolver:
    """Advanced quiz solving using AI Pipe (OpenAI-compatible proxy)"""
    
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    def solve_quiz(self, quiz_content: Dict[str, Any], files_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Main method to solve a quiz"""
        prompt = self._build_prompt(quiz_content, files_data)
        response = self._call_aipipe(prompt)
        solution = self._parse_response(response)
        return solution
    
    def _build_prompt(self, quiz_content: Dict, files_data: Optional[Dict] = None) -> str:
        """Build a comprehensive prompt for the model"""
        prompt_parts = [
            "You are an expert data analyst solving a quiz. Analyze carefully and provide accurate answers.",
            "",
            "=== QUIZ CONTENT ===",
            quiz_content.get('text', ''),
            "",
            "=== QUIZ HTML ===",
            quiz_content.get('html', '')[:3000],
        ]
        
        if files_data:
            prompt_parts.extend([
                "",
                "=== DOWNLOADED FILES ===",
                f"Available files: {list(files_data.keys())}",
            ])
        
        prompt_parts.extend([
            "",
            "=== YOUR TASK ===",
            "1. Identify what the question is asking",
            "2. Extract the submission URL from the quiz page",
            "3. If files are mentioned, list their URLs in 'files_needed'",
            "4. If you have file data, analyze it to answer the question",
            "5. Calculate/derive the answer",
            "6. Format your response as JSON",
            "",
            "=== RESPONSE FORMAT ===",
            "You MUST respond with ONLY a valid JSON object (no other text):",
            "{",
            '  "reasoning": "brief explanation of your approach",',
            '  "submit_url": "URL where answer should be posted",',
            '  "answer": <the answer - could be number, string, boolean, or object>,',
            '  "files_needed": ["list of file URLs if any are needed"]',
            "}",
            "",
            "CRITICAL RULES:",
            "- answer must match the expected data type",
            "- extract submit_url exactly as shown",
            "- if files are needed but not yet provided, list them in files_needed",
            "- if files are provided, analyze them and give the final answer",
            "- return ONLY valid JSON"
        ])
        
        return "\n".join(prompt_parts)
    
    def _call_aipipe(self, prompt: str, max_retries: int = 2) -> str:
        """Call AI Pipe API (OpenAI-compatible) with retries"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-5-nano",
            "input": prompt
        }
        
        for attempt in range(max_retries):
            try:
                resp = requests.post(f"{self.base_url}/responses", headers=headers, json=data, timeout=180)
                resp.raise_for_status()
                result = resp.json()
                
                # Extract text from AI Pipe response
                output_text = ""
                if "output" in result:
                    for item in result["output"]:
                        for c in item.get("content", []):
                            output_text += c.get("text", "")
                return output_text
            
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"AI Pipe API error (attempt {attempt + 1}): {e}")
                continue
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse model's response into structured JSON"""
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start == -1 or end == 0:
                return {"error": "No JSON found", "raw_response": response}
            
            json_str = response[start:end]
            result = json.loads(json_str)
            
            if 'submit_url' not in result:
                result['error'] = "Missing submit_url"
            if 'answer' not in result and 'files_needed' not in result:
                result['error'] = "Missing both answer and files_needed"
            
            return result
        
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse error: {str(e)}", "raw_response": response}
    
    def analyze_files(self, quiz_content: Dict, files_data: Dict) -> Dict[str, Any]:
        """Analyze downloaded files to answer the quiz"""
        prompt_parts = [
            "You are analyzing files to answer a data quiz.",
            "",
            "=== ORIGINAL QUESTION ===",
            quiz_content.get('text', ''),
            "",
            "=== FILES PROVIDED ===",
        ]
        for file_url, file_info in files_data.items():
            prompt_parts.extend([
                "",
                f"File: {file_url}",
                f"Type: {file_info.get('type', 'unknown')}",
                f"Content preview: {str(file_info.get('content', ''))[:1000]}",
            ])
        
        prompt_parts.extend([
            "",
            "=== YOUR TASK ===",
            "Analyze the file(s) and answer the question precisely.",
            "Respond with ONLY valid JSON:",
            "{",
            '  "reasoning": "how you analyzed the data",',
            '  "submit_url": "submission URL from original quiz",',
            '  "answer": <precise answer>',
            "}"
        ])
        
        response = self._call_aipipe("\n".join(prompt_parts))
        return self._parse_response(response)
    
    def handle_visualization(self, data: Any, viz_type: str) -> str:
        """Generate visualization if needed"""
        prompt = f"""Generate a {viz_type} visualization for this data:

{json.dumps(data, indent=2)}

Return a JSON object with:
{{
  "chart_type": "{viz_type}",
  "data_for_chart": {{"x": [...], "y": [...]}},
  "base64_image": "data:image/png;base64,..."
}}

If you cannot generate the image, describe what the chart should show.
"""
        response = self._call_aipipe(prompt)
        return self._parse_response(response)
    
    def validate_answer(self, answer: Any, expected_type: str) -> bool:
        """Validate answer matches expected type"""
        type_mapping = {
            'number': (int, float),
            'string': str,
            'boolean': bool,
            'object': dict,
            'array': list
        }
        expected = type_mapping.get(expected_type)
        if expected is None:
            return True
        return isinstance(answer, expected)
