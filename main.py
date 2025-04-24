import os
import time
import json
import re
from dotenv import load_dotenv
import openai
from playwright.sync_api import sync_playwright

# ─────────────── ENV/CONFIG ───────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Read all non-empty env values into user_data
user_data = {
    "username": os.getenv("COMMON_APP_ID"),
    "password": os.getenv("COMMON_APP_PASSWORD"),
    "student_year": os.getenv("STUDENT_YEAR"),
    "department": os.getenv("DEPARTMENT"),
}
user_data = {k: v for k, v in user_data.items() if v}

USD_INR_RATE = 85.42
PRICE_INPUT  = 1.100
PRICE_OUTPUT = 4.400

# ─────────────── UTILS ───────────────

def call_llm(prompt):
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp

def parse_selector_response(content):
    match = re.search(r'(\{.*\})', content, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    sel = re.search(r"'([^']+)'|\"([^\"]+)\"|(\.[\w\-\[\]='\" ]+|#[\w\-\[\]='\" ]+)", content)
    return sel.group(1) or sel.group(2) or sel.group(3)

def log_cost(usage):
    pt = usage.prompt_tokens
    ct = usage.completion_tokens
    cost_usd_prompt  = pt/1e6 * PRICE_INPUT
    cost_usd_output  = ct/1e6 * PRICE_OUTPUT
    total_usd = cost_usd_prompt + cost_usd_output
    total_inr = total_usd * USD_INR_RATE
    print(f"Tokens → prompt: {pt}, completion: {ct}")
    print(f"Cost → USD ${total_usd:.6f}, INR ₹{total_inr:.2f}")

# ─────────────── SMART LOGIN BUTTON SEARCH ───────────────

def find_login_elements(page):
    login_terms = ["login", "sign in", "log in", "account", "signin", "sign-in"]
    selectors = ["a", "button", "[role='button']", "[tabindex]"]
    elements = page.locator(",".join(selectors))
    html_snippets = []
    for i in range(elements.count()):
        text = elements.nth(i).inner_text().lower()
        aria = elements.nth(i).get_attribute("aria-label") or ""
        if any(term in text or term in aria.lower() for term in login_terms):
            html = elements.nth(i).evaluate("el => el.outerHTML")
            html_snippets.append(html)
    return html_snippets

def get_best_login_selector(html_snippets):
    if not html_snippets:
        return None, 0, 0
    prompt = (
        "Given this list of clickable HTML elements, pick the best selector to click to start the login process. "
        "Output ONLY the selector string (e.g., .login-btn, #sign-in-link).\n\n"
        f"Elements:\n{json.dumps(html_snippets)}"
    )
    resp = call_llm(prompt)
    selector = resp.choices[0].message.content.strip().strip('"').strip("'")
    usage = resp.usage
    return selector, usage.prompt_tokens, usage.completion_tokens

# ─────────────── FORM FILLING/LOGIN FLOW ───────────────

STATIC_PROMPT = """You are given an HTML snippet and user data.
Identify the best selectors for each provided user data key (e.g., username, password, student_year, department)
and the best selector for the submit button.
Output a JSON mapping with these keys (map any missing field to null).
Do not output anything else."""

def get_form_selectors(user_data, form_html):
    prompt = (
        STATIC_PROMPT +
        f"\n\nUser data: {user_data}\n\nForm HTML:\n{form_html}"
    )
    resp = call_llm(prompt)
    mapping = parse_selector_response(resp.choices[0].message.content)
    usage = resp.usage
    return mapping, usage.prompt_tokens, usage.completion_tokens

def main():
    site_url = "https://www.saucedemo.com/"  # Change to your actual site!

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(site_url, timeout=60000)
        page.wait_for_load_state("domcontentloaded")

        # 1. Try to find all likely login buttons/links on the whole page
        login_htmls = find_login_elements(page)
        login_selector, login_pt, login_ct = get_best_login_selector(login_htmls)
        if login_selector:
            print(f"Clicking login: {login_selector}")
            try:
                page.click(login_selector)
                time.sleep(2)
            except Exception as e:
                print(f"Could not click login button: {e}")
        else:
            print("No login button found, trying direct form detection...")

        print(f"Login selector LLM tokens: prompt={login_pt}, completion={login_ct}")
        print(f"Login selector cost: USD ${((login_pt/1e6)*PRICE_INPUT + (login_ct/1e6)*PRICE_OUTPUT):.6f}, INR ₹{((login_pt/1e6)*PRICE_INPUT + (login_ct/1e6)*PRICE_OUTPUT)*USD_INR_RATE:.2f}")

        # 2. Wait for login form/modal to appear
        page.wait_for_selector("form")
        form_html = page.locator("form").first.inner_html()

        # 3. Ask LLM for selectors for all user fields + submit
        mapping, pt, ct = get_form_selectors(user_data, form_html)
        print("Field mapping:", mapping)
        print(f"Form fill LLM tokens: prompt={pt}, completion={ct}")
        print(f"Form fill cost: USD ${((pt/1e6)*PRICE_INPUT + (ct/1e6)*PRICE_OUTPUT):.6f}, INR ₹{((pt/1e6)*PRICE_INPUT + (ct/1e6)*PRICE_OUTPUT)*USD_INR_RATE:.2f}")

        # 4. Fill and click as appropriate
        for field, value in user_data.items():
            sel = mapping.get(field)
            if sel:
                try:
                    page.fill(sel, value)
                    print(f"Filled {field} into {sel}")
                except Exception as e:
                    print(f"Could not fill {field}: {e}")
            else:
                print(f"⚠️ No selector for {field}")

        if mapping.get("submit"):
            try:
                page.click(mapping["submit"])
                print(f"Clicked submit ({mapping['submit']})")
            except Exception as e:
                print(f"Could not click submit: {e}")
        else:
            print("⚠️ No submit button found in mapping")

        print("▶ Automation complete — inspect browser. Close window to exit.")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            pass

        browser.close()

if __name__ == "__main__":
    main()
