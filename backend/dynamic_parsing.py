import re
from typing import Optional, List
from pydantic import BaseModel, create_model, Field

def parse_html_to_pydantic(html_content: str) -> type[BaseModel]:
    fields = {}

    # 1. Base scalars: {{ VAR }}
    for var in re.findall(r'\{\{\s*([A-Z0-9_]+)\s*\}\}', html_content):
        # Make all template variables required to force LLM completion
        fields[var] = (str, Field(...))

    # 2. Top-level lists: {% for item in LIST_NAME %}
    for match in re.finditer(r'\{%\s*for\s+(\w+)\s+in\s+([A-Z0-9_]+)\s*%\}', html_content):
        item_name = match.group(1)
        list_name = match.group(2)
        
        # Find all {{ item.KEY }} inside the template
        keys = set(re.findall(r'\{\{\s*' + item_name + r'\.([A-Z0-9_]+)\s*\}\}', html_content))
        
        # Find any nested lists like {% for sub in item.SUBLIST %}
        nested_lists = set(re.findall(r'\{%\s*for\s+\w+\s+in\s+' + item_name + r'\.([A-Z0-9_]+)\s*%\}', html_content))
        
        if not keys and not nested_lists:
            # It's a simple list of strings - mark as required
            fields[list_name] = (List[str], Field(...))
        else:
            # It's a list of objects - mark as required
            inner_fields = {}
            for k in keys:
                inner_fields[k] = (str, Field(...))
            for nl in nested_lists:
                inner_fields[nl] = (List[str], Field(...))
            
            InnerModel = create_model(f'{list_name}Item', **inner_fields)
            fields[list_name] = (List[InnerModel], Field(...))

    # Create the top-level dynamically
    return create_model('CareerData', **fields)
