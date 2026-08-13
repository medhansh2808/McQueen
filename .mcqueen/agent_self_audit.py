#!/usr/bin/env python3
"""agent_self_audit.py — McQueen agent context-system self-audit (READ-ONLY).

Verifies the agent system is internally consistent:
  1. AGENTS.md exists
  2. required .mcqueen files exist
  3. required headings exist
  4. no required memory file is empty
  5. CURRENT_TASK has exactly one NEXT ACTION
  6. VERIFIED_FACTS has source references
  7. HANDOFF exists
  8. PROJECT_INDEX exists
  9. COMMAND_POLICY exists
 10. startup check exists

This does NOT require all project questions to be solved; it only verifies the
agent context system is healthy. Never modifies files. Exit code 0 = healthy.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MC = os.path.join(ROOT, ".mcqueen")

REQUIRED_MEMORY_FILES = [
    "AGENT_STATE.md",
    "CURRENT_TASK.md",
    "DECISIONS.md",
    "SESSION_LOG.md",
    "VERIFIED_FACTS.md",
    "OPEN_QUESTIONS.md",
    "HANDOFF.md",
]

# file -> list of required headings (regex, case-insensitive, ^ prefix)
REQUIRED_HEADINGS = {
    "AGENT_STATE.md": [r"^#\s+AGENT_STATE"],
    "CURRENT_TASK.md": [
        r"^##\s+OBJECTIVE",
        r"^##\s+CURRENT STATE",
        r"^##\s+BLOCKER",
        r"^##\s+NEXT ACTION",
        r"^##\s+ACCEPTANCE CRITERIA",
        r"^##\s+TEST PLAN",
        r"^##\s+STATUS",
    ],
    "DECISIONS.md": [
        r"^##\s+DECISION \d+",
        r"^- \*\*DATE\*\*:",
        r"^- \*\*QUESTION\*\*:",
        r"^- \*\*EVIDENCE\*\*:",
        r"^- \*\*OPTIONS\*\*:",
        r"^- \*\*DECISION\*\*:",
        r"^- \*\*WHY\*\*:",
        r"^- \*\*CONSEQUENCES\*\*:",
        r"^- \*\*STATUS\*\*:",
    ],
    "SESSION_LOG.md": [r"^#\s+SESSION_LOG"],
    "VERIFIED_FACTS.md": [
        r"^#\s+VERIFIED_FACTS",
        r"SOURCE:",
        r"CONFIDENCE:",
    ],
    "OPEN_QUESTIONS.md": [r"^#\s+OPEN_QUESTIONS"],
    "HANDOFF.md": [r"^#\s+HANDOFF"],
    "PROJECT_INDEX.md": [r"^#\s+PROJECT_INDEX"],
    "COMMAND_POLICY.md": [
        r"^#\s+COMMAND_POLICY",
        r"SAFE_READ",
        r"SAFE_LOCAL_WRITE",
        r"REVIEW_REQUIRED",
        r"HARDWARE_RISK",
        r"REMOTE_RISK",
        r"DESTRUCTIVE",
    ],
}

problems = []
notes = []


def check(cond, msg):
    if cond:
        notes.append("OK  " + msg)
    else:
        problems.append("FAIL " + msg)


def main():
    # 1. AGENTS.md exists
    agents = os.path.join(ROOT, "AGENTS.md")
    check(os.path.isfile(agents) and os.path.getsize(agents) > 0, "AGENTS.md exists and non-empty")

    # 2. required .mcqueen files exist
    for name in REQUIRED_MEMORY_FILES + ["PROJECT_INDEX.md", "COMMAND_POLICY.md",
                                         "agent_startup_check.sh", "agent_self_audit.py"]:
        p = os.path.join(MC, name)
        check(os.path.isfile(p), f"{name} exists")
        if os.path.isfile(p) and os.path.getsize(p) == 0:
            problems.append(f"FAIL {name} is EMPTY (content required)")

    # 3. required headings present
    for name, patterns in REQUIRED_HEADINGS.items():
        p = os.path.join(MC, name)
        if not os.path.isfile(p):
            continue  # already reported above
        text = open(p, encoding="utf-8", errors="replace").read()
        for pat in patterns:
            if not re.search(pat, text, re.IGNORECASE | re.MULTILINE):
                problems.append(f"FAIL {name}: missing required content matching /{pat}/")

    # 5. CURRENT_TASK has exactly one NEXT ACTION
    ct = os.path.join(MC, "CURRENT_TASK.md")
    if os.path.isfile(ct):
        text = open(ct, encoding="utf-8", errors="replace").read()
        # NEXT ACTION section must exist and contain exactly one bolded action line
        m = re.search(r"^##\s+NEXT ACTION\s*$([\s\S]*?)(?=^##\s|\Z)", text, re.MULTILINE)
        if not m:
            problems.append("FAIL CURRENT_TASK.md: missing NEXT ACTION section")
        else:
            section = m.group(1)
            actions = re.findall(r"^\s*(?:-|1\.)\s+.+", section, re.MULTILINE)
            if len(actions) != 1:
                problems.append(
                    f"FAIL CURRENT_TASK.md: NEXT ACTION section must have exactly one action "
                    f"(found {len(actions)})"
                )
            else:
                notes.append(f"OK  CURRENT_TASK has exactly one NEXT ACTION: {actions[0].strip()[:60]}...")

    # 6. VERIFIED_FACTS has source references
    vf = os.path.join(MC, "VERIFIED_FACTS.md")
    if os.path.isfile(vf):
        text = open(vf, encoding="utf-8", errors="replace").read()
        facts = text.count("- FACT:")
        sources = text.count("SOURCE:")
        confs = text.count("CONFIDENCE:")
        check(facts > 0, f"VERIFIED_FACTS has {facts} fact(s)")
        check(sources >= facts, f"VERIFIED_FACTS: source references cover facts ({sources} >= {facts})")
        check(confs >= facts, f"VERIFIED_FACTS: confidence marks cover facts ({confs} >= {facts})")

    # 7-10. existence already covered in loop above; explicit messages
    for name in ["HANDOFF.md", "PROJECT_INDEX.md", "COMMAND_POLICY.md", "agent_startup_check.sh"]:
        check(os.path.isfile(os.path.join(MC, name)), f"{name} present")

    print("McQueen agent context-system self-audit")
    print("=" * 50)
    for n in notes:
        print(n)
    print("-" * 50)
    if problems:
        for p in problems:
            print(p)
        print("=" * 50)
        print(f"RESULT: {len(problems)} problem(s) — context system NOT healthy")
        sys.exit(1)
    print(f"RESULT: healthy ({len(notes)} checks passed, 0 problems)")
    sys.exit(0)


if __name__ == "__main__":
    main()
