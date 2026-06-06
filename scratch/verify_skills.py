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
