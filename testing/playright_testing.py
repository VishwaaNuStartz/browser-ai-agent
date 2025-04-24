import os
from dotenv import load_dotenv
import openai
from playwright.sync_api import sync_playwright

# Load .env file
load_dotenv()

# Set up OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_field_mapping(form_html, user_data):
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
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    import json
    import re
    match = re.search(r'(\{.*\})', response.choices[0].message.content, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in LLM response.")
    field_map = json.loads(match.group(1))
    print("Field mapping:", field_map)
    return field_map

def main():
    user_data = {
        "username": "vishwaa",
        "password": "secretpass"
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/howto/howto_css_login_form.asp", timeout=60000)
        page.wait_for_selector("form")
        form_html = page.locator("form").inner_html()
        print("Extracted Form HTML (truncated):\n", form_html[:500])

        # Get field mapping from LLM
        field_map = get_field_mapping(form_html, user_data)
        browser.close()

if __name__ == "__main__":
    main()
