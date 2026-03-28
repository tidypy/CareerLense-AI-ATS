import re
from typing import Optional, List, Any
from pydantic import BaseModel, create_model, Field

def parse_html_to_pydantic(html_content: str) -> type[BaseModel]:
    fields: dict[str, Any] = {}

    # 1. Base scalars: {{ VAR }} and {% if VAR %}
    scalars = set(re.findall(r'\{\{\s*([A-Z0-9_]+)\s*\}\}', html_content))
    conditionals = set(re.findall(r'\{%\s*if\s+([A-Z0-9_]+)\s*%\}', html_content))
    
    for var in scalars | conditionals:
        # Allow missing fields with empty string default for resiliency
        fields[var] = (Optional[str], Field(default=""))

    # 2. Top-level lists: {% for item in LIST_NAME %}
    for match in re.finditer(r'\{%\s*for\s+(\w+)\s+in\s+([A-Z0-9_]+)\s*%\}', html_content):
        item_name = match.group(1)
        list_name = match.group(2)
        
        # Find all {{ item.KEY }} and {% if item.KEY %}
        keys = set(re.findall(r'\{\{\s*' + item_name + r'\.([A-Z0-9_]+)\s*\}\}', html_content))
        item_conds = set(re.findall(r'\{%\s*if\s+' + item_name + r'\.([A-Z0-9_]+)\s*%\}', html_content))
        
        # Find any nested lists like {% for sub in item.SUBLIST %}
        nested_lists = set(re.findall(r'\{%\s*for\s+\w+\s+in\s+' + item_name + r'\.([A-Z0-9_]+)\s*%\}', html_content))
        
        # Exclude list names from scalar keys
        all_inner_keys = (keys | item_conds) - nested_lists
        
        if not all_inner_keys and not nested_lists:
            # It's a simple list - default to empty list
            fields[list_name] = (List[str], Field(default_factory=list))
        else:
            # It's a list of objects - all fields made optional
            inner_fields: dict[str, Any] = {}
            for k in all_inner_keys:
                inner_fields[k] = (Optional[str], Field(default=""))
            for nl in nested_lists:
                inner_fields[nl] = (List[str], Field(default_factory=list))
            
            # Create the inner model with optional fields
            InnerModel = create_model(f'{list_name}Item', **inner_fields)
            fields[list_name] = (List[InnerModel], Field(default_factory=list))

    # Create the top-level dynamically
    return create_model('CareerData', **fields)
