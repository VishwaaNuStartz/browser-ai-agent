import os, time, json, re
from dotenv import load_dotenv
import openai
from playwright.sync_api import sync_playwright

# ─────────────── ENV + CONFIG ───────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

user_data = {
    "username": os.getenv("COMMON_APP_ID"),
    "password": os.getenv("COMMON_APP_PASSWORD"),
    "student_year": os.getenv("STUDENT_YEAR"),
    "department": os.getenv("DEPARTMENT"),
}
user_data = {k: v for k, v in user_data.items() if v}

def log_step(icon, msg):
    print(f"{icon} {msg}")

# ─────────────── LLM UTILITIES ───────────────
def call_llm(prompt: str):
    return openai.OpenAI().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

def parse_json_or_selector(text: str):
    m = re.search(r'(\{.*\})', text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m2 = re.search(r"'([^']+)'|\"([^\"]+)\"|(\.[\w\-\[\]='\" ]+|#[\w\-\[\]='\" ]+)", text)
    return m2.group(1) or m2.group(2) or m2.group(3)

# ─────────────── PATTERN 1: CANDIDATE LIST ───────────────
def collect_login_candidates(page, max_cands=15):
    terms = ["login", "sign in", "log in", "account"]
    elems = page.locator("a,button,[role='button']")
    cands = []
    for i in range(min(elems.count(), 200)):
        el = elems.nth(i)
        txt = el.inner_text().strip()
        aria = el.get_attribute("aria-label") or ""
        if any(t in txt.lower() or t in aria.lower() for t in terms):
            sel = el.evaluate(
                "e => e.tagName.toLowerCase() + "
                "(e.id ? '#' + e.id : '') + "
                "(e.className ? '.' + e.className.split(' ').join('.') : '')"
            )
            cands.append({"selector": sel, "text": txt, "aria": aria})
        if len(cands) >= max_cands:
            break
    return cands

def choose_login_selector(candidates):
    prompt = (
        "Here is a JSON list of clickable elements. "
        "Pick **exactly one** selector whose click most likely opens the login form. "
        "Reply with only the selector.\n\n" + json.dumps(candidates)
    )
    resp = call_llm(prompt)
    return resp.choices[0].message.content.strip().strip('"')

# ─────────────── PATTERN 2: CONTEXT-SLICE FORM MAPPING ───────────────
STATIC_PROMPT = """You are given a small HTML snippet and user data.
Identify which input each user_data key should fill, plus which selector to click to submit.
Output ONLY a JSON mapping, mapping missing fields to null."""

def map_form_fields(user_data, form_html):
    prompt = STATIC_PROMPT + f"\n\nUser data: {user_data}\n\nForm HTML:\n{form_html}"
    resp = call_llm(prompt)
    return parse_json_or_selector(resp.choices[0].message.content)

# ─────────────── MAIN FLOW ───────────────
def main():
    site = "https://www.commonapp.org/"  # Change as needed

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        log_step("🌐", f"Navigating to {site}")
        page.goto(site, timeout=60000)
        page.wait_for_load_state("domcontentloaded")

        # 1) Click Login via Pattern 1
        log_step("🔍", "Collecting login button candidates…")
        cands = collect_login_candidates(page)
        log_step("📋", f"{len(cands)} candidates found")

        log_step("💡", "Asking LLM to choose login selector…")
        login_sel = choose_login_selector(cands)
        log_step("➡️", f"Chosen login selector: {login_sel!r}")

        if page.locator(login_sel).count():
            log_step("🖱️", f"Clicking login button ({login_sel})")
            page.click(login_sel)
            time.sleep(2)
        else:
            log_step("⚠️", "Candidate selector not found on page; skipping click")

        # 2) Wait for form, extract only that <form> HTML
        log_step("📄", "Waiting for login form to appear…")
        page.wait_for_selector("form")
        form_html = page.locator("form").first.inner_html()
        log_step("✂️", "Extracted form HTML snippet")

        # 3) Map fields via Pattern 2
        log_step("🤖", "Mapping form fields with LLM…")
        mapping = map_form_fields(user_data, form_html)
        log_step("🗺️", f"Field mapping result: {mapping}")

        # 4) Fill fields
        log_step("✏️", "Filling form fields…")
        filled = set()
        for k, v in user_data.items():
            sel = mapping.get(k)
            if sel and page.locator(sel).count():
                page.fill(sel, v)
                filled.add(k)
                log_step("✅", f"Filled {k} → {sel}")
            else:
                log_step("⚠️", f"No selector for {k}; skipped")

        # 5) Heuristic submit detection
        log_step("🔘", "Detecting submit button…")
        submit = None
        for key, sel in mapping.items():
            if key not in filled and sel and page.locator(sel).count():
                tag = page.locator(sel).evaluate("e => e.tagName").lower()
                typ = page.locator(sel).get_attribute("type") or ""
                txt = page.locator(sel).inner_text().lower()
                if (
                    tag == "button"
                    or (tag == "input" and typ.lower() == "submit")
                    or re.search(r"submit|login|continue|next", txt)
                ):
                    submit = sel
                    break
        if submit:
            log_step("🖱️", f"Clicking submit button ({submit})")
            page.click(submit)
        else:
            log_step("⚠️", "No submit button found; exiting without click")

        log_step("🏁", "Automation complete — inspect browser and close to exit")
        page.wait_for_timeout(5000)
        browser.close()

if __name__ == "__main__":
    main()
