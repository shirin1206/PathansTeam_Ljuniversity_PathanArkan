"""
Decision Reversal Analyzer
--------------------------
Reads a chronological list of choices, finds the places where the user
changed their mind, and prints a report with a text timeline.

It only describes what happened. It does not guess why.

Run it:
    python decision_reversal.py              type the decisions in
    python decision_reversal.py --demo       run the example from the problem
    python decision_reversal.py --test       run the built-in test cases
    python decision_reversal.py --mermaid    print a graph you can paste into README.md
    python decision_reversal.py data.txt     read decisions from a file

Accepted input formats (one per line, or all on one line):
    Stage 1: Python
    Python -> Java -> Python
    Python, Java, Python
    [{"stage": 1, "choice": "Python"}, {"stage": 2, "choice": "Java"}]
"""

import json
import re
import sys

# Rules used for classifying the pattern. Change them here if needed.
MIN_REVERSALS_REPEATED = 2    # this many returns = "Repeated Reversal"
FREQUENT_RATIO = 0.75         # changes at 75%+ of the steps ...
FREQUENT_MIN_CHANGES = 4      # ... and at least 4 changes = "Frequent Switching"

LINE = "=" * 44
THIN = "-" * 44


# ---------------------------------------------------------------
# Step 1: reading and checking the input
# ---------------------------------------------------------------

def normalize(text):
    """Lowercase and tidy spaces so Python, python and PYTHON match."""
    return " ".join(text.strip().lower().split())


def parse_input(raw_text):
    """
    Turn raw text into a list of {"stage": int, "choice": str}.
    Returns (decisions, errors). If errors is not empty the input is bad.
    """
    errors = []
    entries = []          # (stage, choice, position) before validation
    text = raw_text.strip()

    if text == "":
        return [], ["The input is empty. Enter at least one decision."]

    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [], ["The JSON could not be read. Check commas and quotes."]
        for position, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                errors.append("Entry %d is not an object with stage and choice." % position)
                continue
            entries.append((item.get("stage"), item.get("choice"), position))
    else:
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # a single line like "A -> B -> A" or "A, B, A"
        if len(lines) == 1 and re.search(r"->|→|,", lines[0]):
            lines = [p for p in re.split(r"\s*(?:->|→|,)\s*", lines[0]) if p]

        for position, line in enumerate(lines, start=1):
            match = re.match(r"^(?:stage\s*)?([^:\s]+)\s*:\s*(.*)$", line, re.IGNORECASE)
            if match:
                entries.append((match.group(1), match.group(2), position))
            else:
                # no stage number given, so use the line number
                entries.append((position, line, position))

    decisions = []
    seen_stages = set()

    for stage, choice, position in entries:
        try:
            stage = int(stage)
        except (TypeError, ValueError):
            errors.append("Entry %d: '%s' is not a valid stage number." % (position, stage))
            continue
        if stage < 1:
            errors.append("Entry %d: stage numbers start at 1." % position)
            continue

        choice = "" if choice is None else str(choice).strip()
        if choice == "":
            errors.append("Stage %d: the choice is missing." % stage)
            continue

        if stage in seen_stages:
            errors.append("Stage %d appears more than once." % stage)
            continue

        seen_stages.add(stage)
        decisions.append({"stage": stage, "choice": choice})

    decisions.sort(key=lambda d: d["stage"])
    return decisions, errors


# ---------------------------------------------------------------
# Step 2: finding changes and reversals
# ---------------------------------------------------------------

def analyze(decisions):
    """Go through the decisions once and collect everything we need."""
    display_name = {}      # normalized key -> first spelling we saw
    times_selected = {}
    times_dropped = {}     # how often a choice was left for something else
    times_returned = {}    # how often a dropped choice was picked again

    changes = []
    reversals = []
    already_seen = set()
    previous_key = None

    for d in decisions:
        key = normalize(d["choice"])
        d["key"] = key

        if key not in display_name:
            display_name[key] = d["choice"].strip()
        d["name"] = display_name[key]

        times_selected[key] = times_selected.get(key, 0) + 1

        if previous_key is not None and key != previous_key:
            # the choice changed
            times_dropped[previous_key] = times_dropped.get(previous_key, 0) + 1
            event = {
                "stage": d["stage"],
                "from": display_name[previous_key],
                "to": d["name"],
                "is_reversal": False,
            }
            # picked before and not the one right before = it was dropped earlier
            if key in already_seen:
                event["is_reversal"] = True
                times_returned[key] = times_returned.get(key, 0) + 1
                reversals.append(event)
            changes.append(event)

        already_seen.add(key)
        previous_key = key

    total = len(decisions)
    change_ratio = len(changes) / (total - 1) if total > 1 else 0.0

    # longest streak of the same choice
    longest_run = 0
    current_run = 0
    last = None
    for d in decisions:
        if d["key"] == last:
            current_run += 1
        else:
            current_run = 1
        last = d["key"]
        longest_run = max(longest_run, current_run)

    # a choice returned to more than once counts extra
    repeated_returns = sum(max(0, n - 1) for n in times_returned.values())

    top_choice = "-"
    if times_selected:
        top_key = max(times_selected, key=times_selected.get)
        top_choice = display_name[top_key]

    pattern = classify(len(changes), len(reversals), change_ratio)

    return {
        "decisions": decisions,
        "names": display_name,
        "changes": changes,
        "reversals": reversals,
        "total": total,
        "unique": len(display_name),
        "change_ratio": change_ratio,
        "longest_run": longest_run,
        "repeated_returns": repeated_returns,
        "top_choice": top_choice,
        "times_selected": times_selected,
        "times_dropped": times_dropped,
        "times_returned": times_returned,
        "pattern": pattern,
    }


# ---------------------------------------------------------------
# Step 3: classifying the pattern
# ---------------------------------------------------------------

def classify(change_count, reversal_count, change_ratio):
    """
    The rules are checked top to bottom, the first match wins.

    The "one reversal" rule sits after the Frequent Switching rule on
    purpose: A -> B -> A has one clear return and should count as a
    reversal, but A -> B -> C -> D -> B changes at every step and is
    better described as switching.
    """
    if reversal_count >= MIN_REVERSALS_REPEATED:
        return "Repeated Reversal"
    if change_count >= FREQUENT_MIN_CHANGES and change_ratio >= FREQUENT_RATIO:
        return "Frequent Switching"
    if reversal_count == 1:
        return "Repeated Reversal"
    if change_count > 0:
        return "Occasional Change"
    return "Stable"


def explain(result):
    """One or two plain sentences about what was observed."""
    pattern = result["pattern"]
    total = result["total"]
    changes = len(result["changes"])
    reversals = result["reversals"]

    if total == 0:
        return "There are no decisions to look at."
    if total == 1:
        return "Only one decision was made, so there is nothing to compare."

    returned_to = ", ".join(result["names"][k] for k in result["times_returned"])
    stages = ", ".join(str(r["stage"]) for r in reversals)

    if pattern == "Stable":
        return "The same choice was kept at every stage. No changes were seen."
    if pattern == "Occasional Change":
        return ("The choice changed %d time(s), but no earlier choice was "
                "picked again after being dropped." % changes)
    if pattern == "Frequent Switching":
        text = "The choice changed at %d of %d steps. " % (changes, total - 1)
        if reversals:
            text += ("Only one change was a return (to %s), so the pattern is "
                     "mostly moving on to new options." % returned_to)
        else:
            text += "None of the changes went back to an earlier choice."
        return text
    return ("A dropped choice was selected again %d time(s), at stage %s. "
            "Returned to: %s." % (len(reversals), stages, returned_to))


# ---------------------------------------------------------------
# Step 4: printing the report and the text visuals
# ---------------------------------------------------------------

def print_flow(result):
    """Vertical list of the decisions with the kind of step between them."""
    print("Decision History:\n")
    decisions = result["decisions"]
    reversal_stages = {r["stage"] for r in result["reversals"]}

    for i, d in enumerate(decisions):
        print("[%d] %s" % (d["stage"], d["name"]))
        if i < len(decisions) - 1:
            nxt = decisions[i + 1]
            if nxt["key"] == d["key"]:
                label = "Same"
            elif nxt["stage"] in reversal_stages:
                label = "Reversal"
            else:
                label = "Changed"
            print("       | %s" % label)


def print_grid(result):
    """
    One row per choice, one column per stage.
        O = chosen     R = chosen again after being dropped     . = not chosen
    """
    decisions = result["decisions"]
    reversal_stages = {r["stage"] for r in result["reversals"]}
    name_width = max(len(n) for n in result["names"].values())
    name_width = max(name_width, 6)

    header = "Stage".ljust(name_width) + "  " + "".join(str(d["stage"]).rjust(4) for d in decisions)
    print(header)
    print("-" * len(header))

    for key, name in result["names"].items():
        row = name.ljust(name_width) + "  "
        for d in decisions:
            if d["key"] != key:
                mark = "."
            elif d["stage"] in reversal_stages:
                mark = "R"
            else:
                mark = "O"
            row += mark.rjust(4)
        print(row)
    print("\nO = chosen   R = returned to a dropped choice   . = not chosen")


def print_report(result):
    print(LINE)
    print("     DECISION REVERSAL ANALYZER")
    print(LINE)
    print()

    if result["total"] == 0:
        print("No decisions to analyze.")
        return

    print_flow(result)
    print()
    print(THIN)
    print("TIMELINE")
    print(THIN)
    print_grid(result)
    print()
    print(THIN)
    print("ANALYSIS")
    print(THIN)
    print("Total decisions       : %d" % result["total"])
    print("Unique choices        : %d" % result["unique"])
    print("Decision changes      : %d" % len(result["changes"]))
    print("Reversal events       : %d" % len(result["reversals"]))
    print("Repeated returns      : %d" % result["repeated_returns"])
    print("Longest run, no change: %d" % result["longest_run"])
    print("Most selected choice  : %s" % result["top_choice"])
    print()
    print("Times each choice was selected / dropped / returned to:")
    for key, name in result["names"].items():
        print("  %-12s %d / %d / %d" % (
            name,
            result["times_selected"].get(key, 0),
            result["times_dropped"].get(key, 0),
            result["times_returned"].get(key, 0),
        ))
    print()
    print("Pattern detected:")
    print("  " + result["pattern"].upper())
    print()
    print("Explanation:")
    print("  " + explain(result))
    print()
    print("Reversal stages:")
    if result["reversals"]:
        for r in result["reversals"]:
            print("  Stage %d: %s -> %s" % (r["stage"], r["from"], r["to"]))
    else:
        print("  none")
    print(LINE)


def to_mermaid(result):
    """
    Build a Mermaid flowchart of the decisions. GitHub and VS Code draw
    it automatically when it is pasted into a README.md.
    Plain arrows are changes, red dashed arrows are reversals.
    """
    decisions = result["decisions"]
    reversal_stages = {r["stage"] for r in result["reversals"]}
    lines = ["flowchart LR"]

    for d in decisions:
        label = "Stage %d<br/>%s" % (d["stage"], d["name"])
        lines.append('    S%d["%s"]' % (d["stage"], label))

    link_number = 0
    reversal_links = []
    for before, after in zip(decisions, decisions[1:]):
        a, b = "S%d" % before["stage"], "S%d" % after["stage"]
        if after["stage"] in reversal_stages:
            lines.append("    %s -. reversal .-> %s" % (a, b))
            reversal_links.append(link_number)
        elif after["key"] == before["key"]:
            lines.append("    %s -- same --> %s" % (a, b))
        else:
            lines.append("    %s -- changed --> %s" % (a, b))
        link_number += 1

    for n in reversal_links:
        lines.append("    linkStyle %d stroke:#c2255c,stroke-width:3px" % n)
    for d in decisions:
        if d["stage"] in reversal_stages:
            lines.append("    style S%d stroke:#c2255c,stroke-width:3px" % d["stage"])

    return "\n".join(lines)


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------

TEST_CASES = [
    ("Stable",                 "Python, Python, Python, Python",   "Stable"),
    ("Simple change",          "Python, Java",                     "Occasional Change"),
    ("Reversal",               "Python, Java, Python",             "Repeated Reversal"),
    ("Multiple reversals",     "Python, Java, Python, C++, Python", "Repeated Reversal"),
    ("Frequent switching",     "Python, Java, C++, JavaScript, Java", "Frequent Switching"),
    ("Alternating",            "Python, Java, Python, Java, Python", "Repeated Reversal"),
    ("Different letter case",  "Python, python, PYTHON",           "Stable"),
    ("No return",              "Python, Java, C++",                "Occasional Change"),
    ("Single decision",        "Python",                           "Stable"),
]


def run_tests():
    passed = 0
    for name, sequence, expected in TEST_CASES:
        decisions, errors = parse_input(sequence)
        got = analyze(decisions)["pattern"]
        ok = (got == expected) and not errors
        passed += ok
        print("%-6s %-22s expected %-18s got %s" % ("PASS" if ok else "FAIL", name, expected, got))

    # input validation checks
    bad_inputs = [
        ("Empty input", ""),
        ("Duplicate stage", "Stage 1: A\nStage 1: B"),
        ("Invalid stage", "Stage x: A"),
        ("Missing choice", "Stage 1:   "),
    ]
    for name, text in bad_inputs:
        _, errors = parse_input(text)
        ok = len(errors) > 0
        passed += ok
        print("%-6s %-22s rejected with an error" % ("PASS" if ok else "FAIL", name))

    total = len(TEST_CASES) + len(bad_inputs)
    print("\n%d of %d tests passed." % (passed, total))
    return passed == total


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def read_from_keyboard():
    print("Enter the decisions in order, one per line, e.g. 'Stage 1: Python'")
    print("or all on one line, e.g. 'Python -> Java -> Python'.")
    print("Press Enter on an empty line when you are done.\n")
    lines = []
    while True:
        try:
            line = input("> ")
        except EOFError:
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    files = [a for a in args if not a.startswith("--")]

    if "--test" in args:
        sys.exit(0 if run_tests() else 1)

    if "--demo" in args:
        raw = "Stage 1: Python\nStage 2: Java\nStage 3: Python\nStage 4: C++\nStage 5: Python"
    elif files:
        try:
            with open(files[0], encoding="utf-8") as f:
                raw = f.read()
        except OSError as err:
            print("Could not open file:", err)
            sys.exit(1)
    else:
        raw = read_from_keyboard()

    decisions, errors = parse_input(raw)
    if errors:
        print("\nThere is a problem with the input:")
        for e in errors:
            print("  - " + e)
        sys.exit(1)

    result = analyze(decisions)

    if "--mermaid" in args:
        print(to_mermaid(result))
        return

    print()
    print_report(result)


if __name__ == "__main__":
    main()
