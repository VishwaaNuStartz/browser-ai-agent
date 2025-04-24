import os
import time
import json
import re
from dotenv import load_dotenv
import openai
from playwright.sync_api import sync_playwright

# Load API key from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Sample user data (adjust based on form fields)
user_data = {
    "username": "standard_user",
    "password": "secret_sauce"
}

def get_field_mapping(form_html: str, user_data: dict) -> dict:
    client = openai.OpenAI()
    prompt = (
        "Given the following HTML form and this user data:\n"
        f"User data: {user_data}\n"
        "Form HTML:\n"
        f"{form_html}\n"
        "For each user data key, output a JSON mapping from the user field name to the best CSS selector or id of the corresponding input element in the form. "
        "Only output the JSON mapping. Example: {\"username\": \"#username\", \"password\": \"#password\"}"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    match = re.search(r'(\{.*\})', response.choices[0].message.content, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in LLM response.")
    field_map = json.loads(match.group(1))
    print("Field mapping:", field_map)
    return field_map

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Open a sample form (can be replaced with your target form)
        page.goto("https://www.saucedemo.com/", timeout=60000)
        page.wait_for_selector("form")

        # Extract the form HTML for LLM processing
        form_html = page.locator("form").inner_html()
        print("Extracted Form HTML (truncated):\n", form_html[:500])

        # Get selector mapping from LLM
        field_map = get_field_mapping(form_html, user_data)

        # Fill the form using the mapping
        for field, selector in field_map.items():
            if field in user_data:
                page.fill(selector, user_data[field])
                print(f"Filled {field} into {selector}")

        # Optional: wait before closing browser
        time.sleep(3)
        browser.close()

if __name__ == "__main__":
    main()
