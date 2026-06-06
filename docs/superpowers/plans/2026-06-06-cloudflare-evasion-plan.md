# Cloudflare Bypass & Evasions for crawl-book Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add comprehensive Cloudflare Bypass & Evasion guidelines to the crawl-book skill files.

**Architecture:** We will modify the three skill markdown files (`.agent/skills/crawl-book/SKILL.md`, `.claude/skills/crawl-book/SKILL.md`, and `.opencode/skill/oc-crawl-book/SKILL.md`) to include a new section "Handling Cloudflare, Anti-Bot & Evasions". We will also write and run a python verification script to check that all three files contain the new instructions and links.

**Tech Stack:** Markdown, Python (for verification).

---

### Task 1: Update Main Agent crawl-book Skill

**Files:**
- Modify: `.agent/skills/crawl-book/SKILL.md`

- [ ] **Step 1: Modify `.agent/skills/crawl-book/SKILL.md` to add the evasion guidelines**

Update `.agent/skills/crawl-book/SKILL.md` after section 2 ("Handle Profile Validation & Repair") to include the Cloudflare evasion guidelines.

Code change:
```diff
@@ -35,2 +35,22 @@
 
+3. **Handling Cloudflare, Anti-Bot & Evasions**:
+   If the target site employs Cloudflare or other anti-bot protection (e.g., www.69shuba.com):
+   - **Automation Flag Bypass**: Launch Chromium with evasion flags such as `--disable-blink-features=AutomationControlled` to prevent detection.
+   - **Remove webdriver Property**: Ensure `navigator.webdriver` is removed or overwritten (`Object.defineProperty(navigator, 'webdriver', {get: () => undefined})`) before navigation starts.
+   - **Session Cookie Pre-Fetching**: Prior to extracting chapter contents, visit the book index/catalog page (e.g., `https://www.69shuba.com/book/<book_id>/`) in the browser context. This allows Cloudflare to set necessary security session cookies (like `cf_clearance`).
+   - **Self-Healing Loop for Challenge Pages**: Implement a loop that checks the page title for challenge text (e.g., "Just a moment...", "Attention Required!"). If detected, poll every 1 second for up to 10 seconds to allow background verification processes to complete instead of failing immediately.
+   - **Validation Overrides**: When short author notice chapters or status updates (e.g., 70-80 characters) trigger chapter length warnings, edit the local `crawl-profile.yaml` inside the workspace to lower `min_chapter_characters` (e.g., set to `20`) to allow these chapters to pass validation.
+
 3. **Verify and Audit the Report**:
```

---

### Task 2: Update Claude Code crawl-book Skill Mirror

**Files:**
- Modify: `.claude/skills/crawl-book/SKILL.md`

- [ ] **Step 1: Modify `.claude/skills/crawl-book/SKILL.md` to add the evasion guidelines**

Update `.claude/skills/crawl-book/SKILL.md` after section 2 to include the Cloudflare evasion guidelines.

Code change:
```diff
@@ -35,2 +35,22 @@
 
+3. **Handling Cloudflare, Anti-Bot & Evasions**:
+   If the target site employs Cloudflare or other anti-bot protection (e.g., www.69shuba.com):
+   - **Automation Flag Bypass**: Launch Chromium with evasion flags such as `--disable-blink-features=AutomationControlled` to prevent detection.
+   - **Remove webdriver Property**: Ensure `navigator.webdriver` is removed or overwritten (`Object.defineProperty(navigator, 'webdriver', {get: () => undefined})`) before navigation starts.
+   - **Session Cookie Pre-Fetching**: Prior to extracting chapter contents, visit the book index/catalog page (e.g., `https://www.69shuba.com/book/<book_id>/`) in the browser context. This allows Cloudflare to set necessary security session cookies (like `cf_clearance`).
+   - **Self-Healing Loop for Challenge Pages**: Implement a loop that checks the page title for challenge text (e.g., "Just a moment...", "Attention Required!"). If detected, poll every 1 second for up to 10 seconds to allow background verification processes to complete instead of failing immediately.
+   - **Validation Overrides**: When short author notice chapters or status updates (e.g., 70-80 characters) trigger chapter length warnings, edit the local `crawl-profile.yaml` inside the workspace to lower `min_chapter_characters` (e.g., set to `20`) to allow these chapters to pass validation.
+
 3. **Verify and Audit the Report**:
```

---

### Task 3: Update OpenCode crawl-book Skill Mirror

**Files:**
- Modify: `.opencode/skill/oc-crawl-book/SKILL.md`

- [ ] **Step 1: Modify `.opencode/skill/oc-crawl-book/SKILL.md` to add the evasion guidelines**

Update `.opencode/skill/oc-crawl-book/SKILL.md` after section 2 to include the Cloudflare evasion guidelines.

Code change:
```diff
@@ -35,2 +35,22 @@
 
+3. **Handling Cloudflare, Anti-Bot & Evasions**:
+   If the target site employs Cloudflare or other anti-bot protection (e.g., www.69shuba.com):
+   - **Automation Flag Bypass**: Launch Chromium with evasion flags such as `--disable-blink-features=AutomationControlled` to prevent detection.
+   - **Remove webdriver Property**: Ensure `navigator.webdriver` is removed or overwritten (`Object.defineProperty(navigator, 'webdriver', {get: () => undefined})`) before navigation starts.
+   - **Session Cookie Pre-Fetching**: Prior to extracting chapter contents, visit the book index/catalog page (e.g., `https://www.69shuba.com/book/<book_id>/`) in the browser context. This allows Cloudflare to set necessary security session cookies (like `cf_clearance`).
+   - **Self-Healing Loop for Challenge Pages**: Implement a loop that checks the page title for challenge text (e.g., "Just a moment...", "Attention Required!"). If detected, poll every 1 second for up to 10 seconds to allow background verification processes to complete instead of failing immediately.
+   - **Validation Overrides**: When short author notice chapters or status updates (e.g., 70-80 characters) trigger chapter length warnings, edit the local `crawl-profile.yaml` inside the workspace to lower `min_chapter_characters` (e.g., set to `20`) to allow these chapters to pass validation.
+
 3. **Verify and Audit the Report**:
```

---

### Task 4: Verify Skill Updates

**Files:**
- Create: `scratch/verify_skills.py`

- [ ] **Step 1: Create the verification script**

Create `scratch/verify_skills.py` to check that the phrase "Handling Cloudflare, Anti-Bot & Evasions" is present in all three target markdown files.

Code content of `scratch/verify_skills.py`:
```python
import os
import sys

def main():
    files = [
        ".agent/skills/crawl-book/SKILL.md",
        ".claude/skills/crawl-book/SKILL.md",
        ".opencode/skill/oc-crawl-book/SKILL.md"
    ]
    target_phrase = "Handling Cloudflare, Anti-Bot & Evasions"
    
    success = True
    for f in files:
        if not os.path.exists(f):
            print(f"FAIL: File {f} does not exist.")
            success = False
            continue
            
        with open(f, "r", encoding="utf-8") as file:
            content = file.read()
            if target_phrase not in content:
                print(f"FAIL: Phrase not found in {f}.")
                success = False
            else:
                print(f"PASS: Phrase found in {f}.")
                
    if not success:
        sys.exit(1)
    print("All checks completed successfully!")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the verification script**

Run: `uv run python scratch/verify_skills.py`
Expected output:
```
PASS: Phrase found in .agent/skills/crawl-book/SKILL.md.
PASS: Phrase found in .claude/skills/crawl-book/SKILL.md.
PASS: Phrase found in .opencode/skill/oc-crawl-book/SKILL.md.
All checks completed successfully!
```
