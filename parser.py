def extract_courses(text):
    if not text:
        return []

    lines = text.splitlines()
    courses = []

    started = False
    entered_block = False

    for line in lines:
        line = line.strip()

        if not started:
            if "دونكم مقرر اليوم" in line:
                started = True
            continue

        if line == "":
            if entered_block:
                break
            continue

        entered_block = True

        if line == "+":
            continue

        if "+" in line:
            parts = [part.strip() for part in line.split("+") if part.strip()]
            courses.extend(parts)
        else:
            courses.append(line)

    return courses
