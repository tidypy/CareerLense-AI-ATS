import re
from typing import Optional, List
from pydantic import BaseModel, create_model, Field

def parse_html_to_pydantic(html_content: str) -> type[BaseModel]:
    fields = {}

    # 1. Base scalars: {{ VAR }}
    for var in re.findall(r'\{\{\s*([A-Z0-9_]+)\s*\}\}', html_content):
        if var in ["CANDIDATE_NAME", "CANDIDATE_LOCATION", "CANDIDATE_EMAIL", "CANDIDATE_LINKEDIN"]:
            fields[var] = (str, Field(...))
        else:
            fields[var] = (Optional[str], Field(default=None))

    # 2. Top-level lists: {% for item in LIST_NAME %}
    for match in re.finditer(r'\{%\s*for\s+(\w+)\s+in\s+([A-Z0-9_]+)\s*%\}', html_content):
        item_name = match.group(1)
        list_name = match.group(2)
        
        # Find all {{ item.KEY }} inside the template
        keys = set(re.findall(r'\{\{\s*' + item_name + r'\.([A-Z0-9_]+)\s*\}\}', html_content))
        
        # Find any nested lists like {% for sub in item.SUBLIST %}
        nested_lists = set(re.findall(r'\{%\s*for\s+\w+\s+in\s+' + item_name + r'\.([A-Z0-9_]+)\s*%\}', html_content))
        
        if not keys and not nested_lists:
            # It's a simple list of strings
            fields[list_name] = (Optional[List[str]], Field(default=None))
        else:
            # It's a list of objects
            inner_fields = {}
            for k in keys:
                inner_fields[k] = (Optional[str], Field(default=None))
            for nl in nested_lists:
                inner_fields[nl] = (Optional[List[str]], Field(default=None))
            
            InnerModel = create_model(f'{list_name}Item', **inner_fields)
            fields[list_name] = (Optional[List[InnerModel]], Field(default=None))

    # Create the top-level dynamically
    return create_model('CareerData', **fields)
