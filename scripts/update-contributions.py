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

    def level(count):
        if count <= 0:
            return 0
        if count <= 1:
            return 1
        if count <= 3:
            return 2
        if count <= 6:
            return 3
        return 4

    content = SVG_PATH.read_text(encoding="utf-8")
    x_positions = {34 + 14 * column: column for column in range(WEEKS)}
    y_positions = {58 + 14 * row: row for row in range(7)}
    updated = 0

    def update_cell(match):
        nonlocal updated
        attrs_text = match.group(1)
        inner = match.group(2)
        attrs = attributes("<rect" + attrs_text + ">")
        try:
            x = int(float(attrs.get("x", "-1")))
            y = int(float(attrs.get("y", "-1")))
        except ValueError:
            return match.group(0)
        if x not in x_positions or y not in y_positions:
            return match.group(0)

        column = x_positions[x]
        row = y_positions[y]
        intensity = level(grid[column][row])
        fill = COLORS[intensity]
        attrs_text = re.sub(r'\bfill="[^"]*"', f'fill="{fill}"', attrs_text, count=1)
        attrs_text = re.sub(r'\s+filter="[^"]*"', "", attrs_text)
        inner = re.sub(
            r'<animate\b(?=[^>]*attributeName="fill")[^>]*/>', "", inner
        )
        if intensity == 4:
            attrs_text += ' filter="url(#glow)"'
            inner += (
                '<animate attributeName="fill" '
                'values="#39ff14;#b6ffa8;#39ff14" '
                'dur="3.5s" begin="0s" repeatCount="indefinite"/>'
            )

        updated += 1
        return "<rect" + attrs_text + ">" + inner + "</rect>"

    content = re.sub(
        r"<rect\b((?:(?!/>)[^>])*)>(.*?)</rect>", update_cell, content, flags=re.S
    )
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
