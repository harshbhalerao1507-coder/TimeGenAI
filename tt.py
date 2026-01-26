# =========================
# CONFIG
# =========================

BREAK_PERIODS = set()
BREAK_PERIODS={2,4}


# =========================
# TABLE GENERATION
# =========================

def table_creation(div, working_days, no_of_period):
    table = [[[] for _ in range(working_days + 1)]
             for _ in range(no_of_period + 1)]

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][:working_days]

    table[0][0] = f"Div-{div}"
    for j in range(1, working_days + 1):
        table[0][j] = days[j - 1]

    for i in range(1, no_of_period + 1):
        table[i][0] = f"P{i}"

    return table


def timegen(no_of_div, working_days, no_of_period):
    return [
        table_creation(div, working_days, no_of_period)
        for div in range(1, no_of_div + 1)
    ]


# =========================
# HOURS → PERIODS
# =========================

def convert_hours_to_periods(subjects, lecture_duration, practical_duration):
    for s in subjects:
        total_lecture_hours = (
            s.get("theory_hours", 0) +
            s.get("tutorial_hours", 0)
        )

        s["theory_per_week"] = (total_lecture_hours * 60) // lecture_duration
        s["practical_per_week"] = (s.get("practical_hours", 0) * 60) // practical_duration


# =========================
# PRACTICAL CHECK
# =========================

def can_place_practical(table, day, period, no_of_period):
    if period >= no_of_period:
        return False
    if period in BREAK_PERIODS or (period + 1) in BREAK_PERIODS:
        return False
    return (
        len(table[period][day]) == 0 and
        len(table[period + 1][day]) == 0
    )


# =========================
# FACULTY STATE HELPERS
# =========================

def can_use_faculty(faculty, faculty_state, faculty_cooldown, faculty_availability, day, period, is_practical=False):
    if faculty_cooldown.get(faculty, 0) > 0:
        return False
    
    state = faculty_state.get(faculty, {"continuous": 0})
    if state["continuous"] >= 2:
        return False
    
    occupied = faculty_availability.get(faculty, {}).get(day, set())
    if is_practical:
        if period in occupied or (period + 1) in occupied:
            return False
    else:
        if period in occupied:
            return False
    
    return True


def update_faculty_state(faculty, faculty_state, faculty_cooldown, faculty_availability, day, period, is_practical=False):
    state = faculty_state.setdefault(faculty, {"continuous": 0})
    state["continuous"] += 1
    
    avail = faculty_availability.setdefault(faculty, {})
    day_occ = avail.setdefault(day, set())
    day_occ.add(period)
    if is_practical:
        day_occ.add(period + 1)
    
    if state["continuous"] == 2 or is_practical:
        faculty_cooldown[faculty] = 1
        state["continuous"] = 0


def tick_cooldowns(faculty_cooldown):
    for f in list(faculty_cooldown):
        faculty_cooldown[f] -= 1
        if faculty_cooldown[f] <= 0:
            del faculty_cooldown[f]


# =========================
# ASSIGNMENT HELPERS
# =========================

def assign_theory(table, div, day, period, subject, faculty):
    table[period][day].append({
        "division": div,
        "subject": subject["subject"],
        "faculty": faculty,
        "type": "theory"
    })


def assign_practical(table, div, day, period, subject, faculty, lab):
    for p in (period, period + 1):
        table[p][day].append({
            "division": div,
            "subject": subject["subject"],
            "faculty": faculty,
            "type": "practical",
            "lab": lab
        })


def has_same_subject_prev(table, day, period, subject_name):
    if period <= 1:
        return False
    for item in table[period - 1][day]:
        if item.get("subject") == subject_name and item.get("type") == "theory":
            return True
    return False


# =========================
# CORE ASSIGNMENT LOGIC
# =========================

def assign_faculty(
    table,
    div,
    day,
    period,
    subjects,
    labs,
    lab_usage,
    no_of_period,
    faculty_state,
    faculty_cooldown,
    faculty_availability,
    division_subject_faculty,
    subject_count_per_day,
    practical_batches
):
    for subject in subjects:
        if not subject.get("faculty"):
            continue

        key = (div, subject["subject"])
        allowed_faculty = (
            [division_subject_faculty[key]]
            if key in division_subject_faculty
            else subject["faculty"]
        )

        current_count = subject_count_per_day.get((div, day, subject["subject"]), 0)
        if current_count >= 2:
            continue

        # THEORY
        if subject["theory_per_week"] > 0 and len(table[period][day]) == 0:
            if has_same_subject_prev(table, day, period, subject["subject"]):
                continue

            for fac in allowed_faculty:
                if can_use_faculty(fac, faculty_state, faculty_cooldown, faculty_availability, day, period):
                    division_subject_faculty[key] = fac
                    assign_theory(table, div, day, period, subject, fac)
                    update_faculty_state(fac, faculty_state, faculty_cooldown, faculty_availability, day, period)
                    subject["theory_per_week"] -= 1
                    subject_count_per_day[(div, day, subject["subject"])] = current_count + 1
                    return

        # PRACTICAL (ALL batches or NONE)
        if subject["practical_per_week"] > 0 and can_place_practical(table, day, period, no_of_period):

            if practical_batches > len(labs):
                return

            temp = []
            used_labs = set()
            used_faculty = set()

            for _ in range(practical_batches):
                lab = None
                fac = None

                for l in labs:
                    occ = lab_usage.get(l, {}).get(day, set())
                    if l not in used_labs and period not in occ and (period + 1) not in occ:
                        lab = l
                        break
                if not lab:
                    return

                for f in allowed_faculty:
                    if f not in used_faculty and can_use_faculty(
                        f, faculty_state, faculty_cooldown, faculty_availability, day, period, True
                    ):
                        fac = f
                        break
                if not fac:
                    return

                temp.append((fac, lab))
                used_labs.add(lab)
                used_faculty.add(fac)

            for fac, lab in temp:
                division_subject_faculty[key] = fac
                assign_practical(table, div, day, period, subject, fac, lab)
                update_faculty_state(
                    fac, faculty_state, faculty_cooldown, faculty_availability, day, period, True
                )
                lab_usage.setdefault(lab, {}).setdefault(day, set()).update({period, period + 1})

            subject["practical_per_week"] -= 1
            subject_count_per_day[(div, day, subject["subject"])] = current_count + 1
            return


# =========================
# ASSIGN ALL DIVISIONS
# =========================

import copy

def assign_all_faculty(tables, working_days, no_of_period, subjects, lab_count, practical_batches):
    labs = [f"Lab-{i}" for i in range(1, lab_count + 1)]

    faculty_state = {}
    faculty_cooldown = {}
    faculty_availability = {}
    lab_usage = {}

    for div, table in enumerate(tables, start=1):
        subs = copy.deepcopy(subjects)
        division_subject_faculty = {}
        subject_count_per_day = {}

        for day in range(1, working_days + 1):
            for period in range(1, no_of_period + 1):
                assign_faculty(
                    table,
                    div,
                    day,
                    period,
                    subs,
                    labs,
                    lab_usage,
                    no_of_period,
                    faculty_state,
                    faculty_cooldown,
                    faculty_availability,
                    division_subject_faculty,
                    subject_count_per_day,
                    practical_batches
                )
                tick_cooldowns(faculty_cooldown)

        for sub in subs:
            if sub.get("theory_per_week", 0) > 0 or sub.get("practical_per_week", 0) > 0:
                raise ValueError(
                    f"No valid timetable possible for Division {div}: "
                    f"{sub['subject']} not fully scheduled"
                )


# =========================
# DEBUG PRINT
# =========================

def faculty_initials(name):
    return "".join(p[0].upper() for p in name.split() if p)


def pretty_print_tables(tables):
    for d, table in enumerate(tables, start=1):
        print(f"\n========== Division {d} ==========")
        for row in table:
            out = []
            for cell in row:
                if isinstance(cell, list):
                    if not cell:
                        out.append("")
                    else:
                        cell_strs = []
                        for item in cell:
                            fac = faculty_initials(item["faculty"])
                            lab = f"({item.get('lab')})" if item.get("lab") else ""
                            cell_strs.append(f"{item['subject']}[{fac}]{lab}({item['type'][0].upper()})")
                        out.append(", ".join(cell_strs))
                else:
                    out.append(str(cell))
            print("\t".join(out))
