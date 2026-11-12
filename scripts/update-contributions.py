#!/usr/bin/env python3
"""Refresh the Matrix contribution grid from GitHub's public contribution calendar."""
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import re
import sys

USERNAME = "vinn-devv"
SVG_PATH = Path("assets/matrix-contributions.svg")
WEEKS = 46
COLORS = {
    0: "#0a1f10",
    1: "#0e4429",
    2: "#00843d",
    3: "#2fd35a",
    4: "#39ff14",
}


def attributes(tag):
    return dict(re.findall(r'([\w:-]+)=["\']([^"\']*)["\']', tag))


def main():
    today = date.today()
    url = f"https://github.com/users/{USERNAME}/contributions?to={today.isoformat()}"
    request = Request(url, headers={
        "User-Agent": "vinn-devv-contribution-graph/1.0",
        "Accept": "image/svg+xml",
    })
    with urlopen(request, timeout=30) as response:
        source = response.read().decode("utf-8")

    daily = {}
    for tag in re.findall(r"<rect\b[^>]*>", source):
        attrs = attributes(tag)
        day = attrs.get("data-date")
        count = attrs.get("data-count")
        if day and count is not None:
            try:
                daily[date.fromisoformat(day)] = int(count)
            except ValueError:
                continue

    if len(daily) < 300:
        raise RuntimeError(
            f"GitHub returned only {len(daily)} contribution days; refusing to overwrite the graph."
        )

    # The supplied design has 46 columns. Keep its exact cell geometry and show
    # the most recent 46 Sunday-to-Saturday weeks.
    sunday_this_week = today - timedelta(days=(today.weekday() + 1) % 7)
    first_sunday = sunday_this_week - timedelta(weeks=WEEKS - 1)
    grid = [[0 for _ in range(7)] for _ in range(WEEKS)]
    total = 0

    for day, count in daily.items():
        if first_sunday <= day <= today:
            week = (day - first_sunday).days // 7
            weekday = (day.weekday() + 1) % 7  # Sunday = row 0
            if 0 <= week < WEEKS:
                grid[week][weekday] = count
                total += count

    values = sorted(count for week in grid for count in week if count > 0)
    if values:
        # Keep five readable levels while adapting to the account's real activity.
        q1 = values[max(0, (len(values) - 1) // 4)]
        q2 = values[max(0, (len(values) - 1) // 2)]
        q3 = values[max(0, (3 * (len(values) - 1)) // 4)]
        thresholds = (q1, q2, q3)
    else:
        thresholds = (1, 2, 3)

    def level(count):
        if count <= 0:
            return 0
        q1, q2, q3 = thresholds
        if count <= q1:
            return 1
        if count <= q2:
            return 2
        if count <= q3:
            return 3
        return 4

    content = SVG_PATH.read_text(encoding="utf-8")
    x_positions = {34 + 14 * column: column for column in range(WEEKS)}
    y_positions = {58 + 14 * row: row for row in range(7)}
    updated = 0

    def update_cell(match):
        nonlocal updated
        tag = match.group(0)
        attrs = attributes(tag)
        try:
            x = int(float(attrs.get("x", "-1")))
            y = int(float(attrs.get("y", "-1")))
        except ValueError:
            return tag
        if x not in x_positions or y not in y_positions:
            return tag
        column = x_positions[x]
        row = y_positions[y]
        fill = COLORS[level(grid[column][row])]
        tag = re.sub(r'\bfill="[^"]*"', f'fill="{fill}"', tag, count=1)
        updated += 1
        return tag

    content = re.sub(r"<rect\b[^>]*>", update_cell, content)
    expected = WEEKS * 7
    if updated != expected:
        raise RuntimeError(f"Expected to update {expected} grid cells, updated {updated}.")

    label = f"{total} contributions in the last {WEEKS} weeks"
    label_pattern = r'(<text\b[^>]*x="34"[^>]*y="184"[^>]*>).*?(</text>)'
    content, replacements = re.subn(
        label_pattern, lambda match: match.group(1) + label + match.group(2),
        content, count=1, flags=re.S
    )
    if replacements != 1:
        raise RuntimeError("Could not find the contribution total label in the supplied SVG.")

    SVG_PATH.write_text(content, encoding="utf-8")
    print(f"Updated {updated} cells from {len(daily)} GitHub dates: {label}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Contribution graph update failed: {error}", file=sys.stderr)
        raise
