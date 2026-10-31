"""
Check every relative link and #anchor in the repository's Markdown files.

    python scripts/check_doc_links.py      # exit 1 on any missing file or anchor

External (http/https) links are not checked.
"""
import re, sys, pathlib, unicodedata
root = pathlib.Path('.').resolve()
files = [p for p in root.rglob('*.md') if '.git' not in p.parts and 'node_modules' not in p.parts and '.pytest_cache' not in p.parts]
def slug(h):
    h = h.strip().lower()
    h = re.sub(r'[`*_~]', '', h)
    h = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', h)
    out = ''.join(c for c in h if c.isalnum() or c in ' -' or unicodedata.category(c).startswith('L'))
    return out.replace(' ', '-')
anchors = {}
for f in files:
    s = f.read_text()
    s_nocode = re.sub(r'```.*?```', '', s, flags=re.S)
    anchors[f] = {slug(m.group(2)) for m in re.finditer(r'^(#{1,6})\s+(.*)$', s_nocode, flags=re.M)}
bad = 0; n = 0
for f in files:
    s = re.sub(r'```.*?```', '', f.read_text(), flags=re.S)
    for m in re.finditer(r'(?<!!)\[[^\]]*\]\(([^)\s]+)\)|<img src="([^"]+)"|!\[[^\]]*\]\(([^)\s]+)\)', s):
        link = m.group(1) or m.group(2) or m.group(3)
        if link.startswith(('http://', 'https://', 'mailto:')): continue
        n += 1
        path, _, frag = link.partition('#')
        target = (f.parent / path).resolve() if path else f
        if not target.exists():
            print(f'MISSING  {f.relative_to(root)} -> {link}'); bad += 1; continue
        if frag and target.suffix == '.md' and frag not in anchors.get(target, set()):
            print(f'ANCHOR   {f.relative_to(root)} -> {link}'); bad += 1
print(f'{n} internal links checked, {bad} problems')
sys.exit(1 if bad else 0)
