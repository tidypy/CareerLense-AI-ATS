from backend.json_repair import repair_json, try_parse_repaired_json
import json

def test_repair():
    # Test case 1: Truncated JSON object
    truncated = '{"name": "John", "age": 30, "skills": ["Python", "Dart"'
    repaired = repair_json(truncated)
    print(f"Original: {truncated}")
    print(f"Repaired: {repaired}")
    assert json.loads(repaired) == {"name": "John", "age": 30, "skills": ["Python", "Dart"]}
    
    # Test case 2: Truncated inside a string
    truncated_str = '{"bio": "I am a developer who loves'
    repaired_str = repair_json(truncated_str)
    print(f"Original: {truncated_str}")
    print(f"Repaired: {repaired_str}")
    # Note: simple repair might just close the string and braces
    parsed = json.loads(repaired_str)
    assert "bio" in parsed
    
    # Test case 3: Trailing comma before truncation
    truncated_comma = '{"data": [1, 2, 3],'
    repaired_comma = repair_json(truncated_comma)
    print(f"Original: {truncated_comma}")
    print(f"Repaired: {repaired_comma}")
    assert json.loads(repaired_comma) == {"data": [1, 2, 3]}

    print("\nAll repair tests passed!")

if __name__ == "__main__":
    test_repair()
