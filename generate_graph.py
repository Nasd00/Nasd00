import subprocess
import html

cmd = [
    "git",
    "log",
    "--all",
    "--graph",
    "--pretty=format:%h %s",
    "--abbrev-commit",
    "--date-order",
    "-n",
    "40",
]

graph = subprocess.check_output(cmd, text=True)

lines = graph.splitlines()

line_height = 22
width = 900
height = max(120, len(lines) * line_height + 40)

escaped = [html.escape(line) for line in lines]

text_elements = []
for i, line in enumerate(escaped):
    y = 30 + i * line_height
    text_elements.append(
        f'<text x="20" y="{y}" class="line">{line}</text>'
    )

svg = f"""<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{width}"
    height="{height}"
    viewBox="0 0 {width} {height}"
>
<style>
    .background {{
        fill: #0d1117;
    }}

    .line {{
        fill: #c9d1d9;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        font-size: 14px;
        white-space: pre;
    }}
</style>

<rect class="background" width="100%" height="100%" rx="8"/>

{"".join(text_elements)}

</svg>
"""

with open("assets/git-graph.svg", "w") as f:
    f.write(svg)
