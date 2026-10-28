#!/usr/bin/env python3
"""Ghost Load storyteller (v2).

A LOCAL open-weight model (Gemma via Ollama) writes a short ghost story for each
finding. Small models like to invent details, so the code CHECKS every story:
  - every number must come from the verified facts,
  - key numbers must appear,
  - no invented places or objects (kitchen, bed, ...),
and retries if the check fails. The "Real advice" line is added by code.
"""
import argparse
import json
import re
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM = (
    "You write very short, spooky-but-warm ghost stories about household electricity. "
    "Write 3 or 4 sentences, maximum 60 words. Use ONLY the facts you are given. "
    "Write all numbers as digits, exactly as given. Do NOT mention any room, furniture, "
    "appliance, weather, person or time that is not in the facts. Do NOT give advice. "
    "Describe ONLY the meter, the electricity, the numbers and the time of day. Use no other objects or scenery. "
    "Do NOT use headings or lists."
)

# Words that mean the model invented a place or object.
BANNED = ["kitchen", "bedroom", "bed", "room", "living", "garage", "attic", "basement",
          "week", "twice", "flicker", "wiring", "outlet", "window", "door", "fridge",
          "television", "tv", "lamp", "bulb", "light", "candle", "shadow", "whisper"]

# Spelled-out numbers are rejected: the model must use digits (it once wrote "Eighty-sixteen").
NUMBER_WORDS = {"two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
                "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
                "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
                "ninety", "hundred", "thousand"}

# Phrases that change the meaning (checked per kind of finding).
BAD_PHRASES = {
    "one_off_surge": ["forever", "always", "again", "keeps", "continu", "endless", "eternal", "still", "every night",
                      "each night", "repeat", "constant"],
    "recurring_hour": ["always", "forever", "every single", "never missed", "each and every", "every night", "each night", "nightly",
                       "in a row", "consecutive", "straight", "without fail", "without exception"],
    "baseload_step": ["occasionally", "once ", "briefly", "one time", "one-time",
                      " rise", " rising", " grew", "growing", "increas", "escalat", "climb"],
}

ADVICE = {
    "baseload_step": "Real advice: unplug devices one by one at night and watch your meter. "
                     "Look for something added around the first day above, such as a new device, charger or router.",
    "recurring_hour": "Real advice: check what switches on automatically at that hour, "
                      "such as a water heater, pump, timer or scheduled device.",
    "one_off_surge": "Real advice: think about what was running at that time. "
                     "A one-time surge often means a heavy appliance, a fault, or a visitor using many devices.",
}


def describe(finding, cur):
    """Plain-sentence facts + the numbers the story must contain."""
    f, kind = finding["facts"], finding["kind"]
    if kind == "baseload_step":
        text = (f"Since {f['first_day_noticed']}, something in the house has drawn about "
                f"{f['constant_extra_draw_watts']} watts all day and night, even when everything seems off. "
                f"In {f['days_since']} days it used an extra {f['extra_energy_kwh']} kWh, costing about "
                f"{f['extra_cost']} {cur}. If it continues, that is about "
                f"{f['projected_extra_cost_per_30_days']} {cur} more every 30 days.")
        must = [str(f["constant_extra_draw_watts"]), str(f["days_since"]), f"{f['extra_cost']} {cur}"]
    elif kind == "recurring_hour":
        text = (f"Almost every night at {f['hour']}, usage jumps to about {f['typical_usage_kwh']} kWh, while the "
                f"hours around it use about {f['usual_usage_in_neighbouring_hours_kwh']} kWh. "
                f"This happened on {f['nights_it_appeared']} of {f['out_of_days']} nights and used an extra "
                f"{f['extra_energy_kwh']} kWh, about {f['extra_cost']} {cur}.")
        must = [f["hour"], str(f["nights_it_appeared"]), str(f["extra_energy_kwh"]), f"{f['extra_cost']} {cur}"]
    else:
        text = (f"On {f['when']}, the house used {f['usage_kwh']} kWh in a single hour. That hour normally uses "
                f"about {f['normal_for_that_hour_kwh']} kWh. That is {f['extra_energy_kwh']} kWh extra, "
                f"about {f['extra_cost']} {cur}.")
        must = [str(f["usage_kwh"]), str(f["extra_energy_kwh"]), f"{f['extra_cost']} {cur}"]
    return text, must


def numbers_in(text):
    return set(re.findall(r"\d+(?:[.:]\d+)*", text))


def check(story, facts_text, must, kind=None):
    """Return a list of problems (empty list = story is OK)."""
    problems = []
    allowed = numbers_in(facts_text)
    bad = [n for n in numbers_in(story) if n not in allowed]
    if bad:
        problems.append(f"numbers not in facts: {bad}")
    missing = [m for m in must if m not in story]
    if missing:
        problems.append(f"missing key numbers: {missing}")
    words = set(re.findall(r"[a-z]+", story.lower()))
    stems = [b for b in BANNED if any(w.startswith(b) for w in words)]
    if stems:
        problems.append(f"invented details: {stems}")
    low = story.lower()
    meaning = [p for p in BAD_PHRASES.get(kind, []) if p in low]
    if meaning:
        problems.append(f"wrong meaning, do not use: {meaning}")
    spelled = sorted(words & NUMBER_WORDS)
    if spelled:
        problems.append(f"numbers written as words (use digits): {spelled}")
    return problems


def ask_model(model, name, facts_text, feedback="", temperature=0.4, must=None):
    prompt = (f"Ghost name: {name}\nVerified facts:\n{facts_text}\n\n"
              "Write the ghost story now (3 or 4 sentences, no advice)."
              + (f"\nYou MUST include these exact figures, written as digits: {', '.join(must)}." if must else ""))
    if feedback:
        prompt += f"\n\nYour previous story was REJECTED because: {feedback}. Fix this and write a new story."
    body = json.dumps({
        "model": model, "system": SYSTEM, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_predict": 200},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["response"].strip()


def fallback_story(finding, cur):
    """Plain story written by code, used only if the model keeps failing the checks."""
    f, kind = finding["facts"], finding["kind"]
    if kind == "baseload_step":
        return (f"Since {f['first_day_noticed']}, a quiet presence has drawn about "
                f"{f['constant_extra_draw_watts']} watts, day and night, never resting. In {f['days_since']} days "
                f"it has taken an extra {f['extra_energy_kwh']} kWh, about {f['extra_cost']} {cur}.")
    if kind == "recurring_hour":
        return (f"Almost every night, a visitor arrives at {f['hour']}. It came on {f['nights_it_appeared']} of "
                f"{f['out_of_days']} nights and took an extra {f['extra_energy_kwh']} kWh, about {f['extra_cost']} {cur}.")
    return (f"On {f['when']}, the house suddenly used {f['usage_kwh']} kWh in one hour, when "
            f"{f['normal_for_that_hour_kwh']} kWh was normal. The surge cost about {f['extra_cost']} {cur}.")


def tell(model, finding, cur, tries=4):
    facts_text, must = describe(finding, cur)
    feedback = ""
    for attempt in range(1, tries + 1):
        temp = 0.4 + 0.15 * (attempt - 1)
        story = ask_model(model, finding["title"], facts_text, feedback, temp, must)
        problems = check(story, facts_text, must, finding["kind"])
        if not problems:
            return story, False
        feedback = "; ".join(problems)
        print(f"   attempt {attempt} rejected: {feedback}")
    return fallback_story(finding, cur), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("findings", nargs="?", default="findings.json")
    ap.add_argument("--model", default="gemma3:4b", help="gemma3:4b (better) or gemma3:1b (faster)")
    ap.add_argument("--currency", default="AED")
    ap.add_argument("--out", default="ghost_report.md")
    args = ap.parse_args()

    with open(args.findings) as f:
        data = json.load(f)

    report = ["# Ghost Load report", "",
              f"_Stories by {args.model}, running locally. Numbers are checked by code. "
              f"Cost rate: {data['rate_per_kwh']} {args.currency}/kWh (assumed)._", ""]

    for finding in data["findings"]:
        print(f"\n=== {finding['id']}. {finding['title']} ===")
        try:
            story, used_fallback = tell(args.model, finding, args.currency)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise SystemExit(f"\nCould not reach Ollama ({e}).\nOpen the Ollama app and run: ollama pull {args.model}")
        facts_text, _ = describe(finding, args.currency)
        if used_fallback:
            story += "  [written by code: the model's attempts failed the checks]"
        advice = ADVICE[finding["kind"]]
        print(story, "\n" + advice)
        report += [f"## {finding['id']}. {finding['title']}", "", story, "", f"**{advice}**", "",
                   f"_Verified facts (from code): {facts_text}_", ""]

    with open(args.out, "w") as f:
        f.write("\n".join(report))
    print(f"\nSaved report to {args.out}")


if __name__ == "__main__":
    main()
