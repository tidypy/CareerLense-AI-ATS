import re

def generate_model():
    with open('Template4.html', 'r', encoding='utf-8') as f:
        html_content = f.read()

    placeholders = sorted(list(set(re.findall(r'\{\{([^}]+)\}\}', html_content))))
    
    # Generate Pydantic model
    model_code = "from pydantic import BaseModel, Field\n\n"
    model_code += "class CareerData(BaseModel):\n"
    for ph in placeholders:
        model_code += f"    {ph}: str = Field(description='Extracted text for {ph}')\n"
        
    with open('backend/models.py', 'w', encoding='utf-8') as f:
        f.write(model_code)
    
    print(f"Generated models.py with {len(placeholders)} fields.")

if __name__ == "__main__":
    generate_model()
