"""
The Medicine Timeline: when each medicine is taken, as the prescription says.

One function builds it, and both the analysis screen and the PDF render its output, so they cannot disagree.

Rules (nothing is invented):
  - only IDENTIFIED medicines (matched by the matcher or confirmed by the person) appear by name; a line that is not
    identified is listed apart as "not included until identified", with what was read from it;
  - the times of day come from the schedule the prescription wrote ("1-0-1" = morning and night). A line with no schedule
    but a frequency ("twice daily", "OD") is listed under "time of day not written"; "as needed" and "once weekly" have
    their own groups;
  - a schedule that was only POSSIBLY read (digits that ran together, "100") is shown with that caveat, never as fact;
  - a duration is shown as written ("5 days"); a duration whose number could not be read says so; a missing one says
    "not written". Nothing is defaulted.
"""

SLOT_ORDER = ("morning", "afternoon", "evening", "night")
SLOT_LABELS = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening", "night": "Night"}
GROUP_LABELS = {
    "time_not_written": "Time of day not written",
    "as_needed": "Only when needed",
    "weekly": "Once a week",
}


def _amount_label(value, form):
    if value == 0.5:
        number = "½"
    elif value == int(value):
        number = str(int(value))
    else:
        number = str(value)
    unit = (form or "").lower()
    if "tablet" in unit:
        unit = "tablet" if value <= 1 else "tablets"
    elif "capsule" in unit:
        unit = "capsule" if value <= 1 else "capsules"
    else:
        unit = "dose" if value <= 1 else "doses"
    return f"{number} {unit}"


def _duration_text(ins):
    if ins.get("duration"):
        return f"for {ins['duration']}"
    if ins.get("duration_unreadable"):
        return "number of days could not be read"
    return "duration not written"


def build_timeline(entries):
    """
    entries: [{"pm_id", "raw_text", "name" (or None), "form", "identified" (bool), "instructions" (dict or None)}]
    Returns {"slots": [{"slot", "label", "items": [...]}], "groups": [{"group", "label", "items": [...]}],
             "not_identified": [...], "has_content": bool}
    where an item is {"pm_id", "medicine", "amount", "timing", "duration", "possible", "schedule", "source_text"}.
    """
    slots = {name: [] for name in SLOT_ORDER}
    groups = {name: [] for name in GROUP_LABELS}
    not_identified = []

    for entry in entries:
        ins = entry.get("instructions") or {}
        has_schedule = bool(ins.get("schedule") and ins.get("slots"))
        frequency = ins.get("frequency")
        readable = has_schedule or frequency or ins.get("duration") or ins.get("duration_unreadable") or ins.get("dose") or ins.get("timing")
        if not entry.get("identified"):
            if readable:
                not_identified.append({
                    "pm_id": entry.get("pm_id"), "source_text": entry.get("raw_text"),
                    "read_as": ins.get("text") or frequency, "duration": _duration_text(ins),
                    "possible": ins.get("schedule_certainty") == "digits_run_together",
                })
            continue

        base = {
            "pm_id": entry.get("pm_id"), "medicine": entry.get("name") or entry.get("raw_text"), "timing": ins.get("timing"),
            "duration": _duration_text(ins), "possible": ins.get("schedule_certainty") == "digits_run_together",
            "schedule": ins.get("schedule"), "source_text": entry.get("raw_text"),
        }
        if frequency == "As needed":
            groups["as_needed"].append({**base, "amount": ins.get("dose")})
        elif frequency == "Once weekly":
            groups["weekly"].append({**base, "amount": ins.get("dose")})
        elif has_schedule:
            for slot, value in ins["slots"].items():
                if value:
                    slots[slot].append({**base, "amount": ins.get("dose") if ins.get("dose") and value == 1 else _amount_label(value, entry.get("form"))})
        elif frequency == "At night":
            slots["night"].append({**base, "amount": ins.get("dose") or _amount_label(1, entry.get("form"))})
        elif frequency or ins.get("duration") or ins.get("dose"):
            groups["time_not_written"].append({**base, "amount": ins.get("dose"), "frequency": frequency})

    slot_list = [{"slot": name, "label": SLOT_LABELS[name], "items": slots[name]} for name in SLOT_ORDER if slots[name]]
    group_list = [{"group": name, "label": GROUP_LABELS[name], "items": items} for name, items in groups.items() if items]
    return {
        "slots": slot_list, "groups": group_list, "not_identified": not_identified,
        "has_content": bool(slot_list or group_list or not_identified),
    }


def entries_from_detected(detected_medicines):
    """The timeline's entries from the detected_medicines of the upload / detail response (both response shapes)."""
    entries = []
    for m in detected_medicines:
        medicine = m.get("medicine") or {}
        status = m.get("match_status") or m.get("status")
        medicine_id = m.get("medicine_id") if m.get("medicine_id") is not None else medicine.get("medicine_id")
        entries.append({
            "pm_id": m.get("pm_id"), "raw_text": m.get("raw_text"),
            "name": m.get("medicine_name") or medicine.get("medicine_name") or (m.get("user_entered") or {}).get("name"),
            "form": m.get("form") or medicine.get("form"),
            "identified": status in ("matched", "user_confirmed") and medicine_id is not None,
            "instructions": m.get("instructions"),
        })
    return entries


def entries_from_report_lines(lines):
    """The same entries from the PDF's report lines."""
    return [{
        "pm_id": ln["pm"]["pm_id"], "raw_text": ln["pm"]["raw_text"], "name": ln["pm"].get("medicine_name"), "form": ln["pm"].get("form"),
        "identified": ln["identified"], "instructions": (ln["safety"] or {}).get("instructions"),
    } for ln in lines]
