"""Build a portable HTML contact sheet for final PNG evidence."""

from __future__ import annotations

import argparse
import html
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    images = sorted(root.rglob("*.png"))
    cards = []
    for image in images:
        relative = image.relative_to(output.parent).as_posix()
        label = image.relative_to(root).as_posix()
        cards.append(
            '<figure><a href="{src}"><img src="{src}" alt="{alt}"></a>'
            "<figcaption>{label}</figcaption></figure>".format(
                src=html.escape(relative, quote=True),
                alt=html.escape(label, quote=True),
                label=html.escape(label),
            )
        )
    document = """<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Final visual evidence contact sheet</title>
<style>
body {{ margin: 24px; font-family: system-ui, sans-serif; background: #f5f7fa; color: #172b4d; }}
h1 {{ margin: 0 0 8px; }}
p {{ margin: 0 0 24px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
figure {{ margin: 0; padding: 10px; background: white; border: 1px solid #d9e2ec; border-radius: 8px; }}
img {{ display: block; width: 100%; height: auto; border: 1px solid #e4e7eb; }}
figcaption {{ margin-top: 8px; font-size: 13px; overflow-wrap: anywhere; }}
</style>
</head>
<body>
<h1>Final visual evidence contact sheet</h1>
<p>{count} PNG captures. Select an image for full resolution.</p>
<main>{cards}</main>
</body>
</html>
""".format(count=len(images), cards="\n".join(cards))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"Wrote contact sheet with {len(images)} images to {output}")


if __name__ == "__main__":
    main()
