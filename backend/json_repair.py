import json
import logging

logger = logging.getLogger("careerlens.json_repair")

def repair_json(raw_json: str) -> str:
    """
    Attempts to repair truncated JSON by closing all open braces and brackets.
    Also handles common issues like trailing commas.
    """
    raw_json = raw_json.strip()
    
    # Remove common conversational padding
    if len(raw_json) > 3 and raw_json.endswith("```"):
        raw_json = raw_json[0:len(raw_json)-3].strip()
    
    # Basic brace balance counting
    stack = []
    in_string = False
    escape = False
    
    # Find the start of the JSON object
    start_index = raw_json.find('{')
    if start_index == -1:
        return raw_json # No object found
    
    cleaned_json = str(raw_json[start_index:])
    
    for i in range(len(cleaned_json)):
        char = cleaned_json[i]
        if char == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if char == '{':
                stack.append('}')
            elif char == '[':
                stack.append(']')
            elif char == '}':
                if stack and stack[-1] == '}':
                    stack.pop()
            elif char == ']':
                if stack and stack[-1] == ']':
                    stack.pop()
        
        if char == '\\':
            escape = not escape
        else:
            escape = False
            
    # If we are inside an unfinished string, close it
    if in_string:
        cleaned_json += '"'
        
    # If we stopped at a comma, remove it
    if cleaned_json.rstrip().endswith(','):
        cleaned_json = cleaned_json.rstrip()[:-1]
        
    # Append the necessary closing characters in reverse order
    for closing_char in reversed(stack):
        cleaned_json += closing_char
        
    return cleaned_json

def try_parse_repaired_json(raw_json: str) -> dict:
    """
    First tries to parse the JSON as is. If it fails, attempts to repair it.
    """
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        logger.warning("Initial JSON parse failed. Attempting repair...")
        repaired = repair_json(raw_json)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            logger.error(f"JSON repair failed: {e}")
            raise e
