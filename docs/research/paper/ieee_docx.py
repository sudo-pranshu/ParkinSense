"""Minimal IEEE-style two-column DOCX helpers (python-docx).

Features: continuous 1-/2-column sections (for full-width figures and tables), Roman-numbered
section headings, native Word equations (LaTeX -> OMML via pandoc), auto-numbered figures,
tables, equations, and numbered-by-first-use citations with {fig:x} {tab:x} {eq:x} {sec:x}
{c:key} cross-reference tokens resolved in a second pass.
"""
import html
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from lxml import etree

FONT = "Times New Roman"
BODY_PT = 9.5
COL_W = 3.45          # inches
FULL_W = 7.1


def roman(n):
    out = ""
    for v, s in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


class Paper:
    def __init__(self, refs_prev=None, cites_prev=None):
        self.doc = Document()
        self.refs_prev = refs_prev or {}        # label -> display (from pass 1)
        self.cites_prev = cites_prev or {}      # key -> number (from pass 1)
        self.refs = {}
        self.cite_order = []
        self.nfig = self.ntab = self.neq = self.nsec = 0
        self.unresolved = set()
        self._styles()
        s = self.doc.sections[0]
        s.page_width, s.page_height = Inches(8.5), Inches(11)
        s.left_margin = s.right_margin = Inches(0.7)
        s.top_margin, s.bottom_margin = Inches(0.75), Inches(0.8)
        self._set_cols(s, 1)
        self._footer(s)

    # ------------------------------------------------------------------ setup
    def _styles(self):
        st = self.doc.styles["Normal"]
        st.font.name = FONT
        st.font.size = Pt(BODY_PT)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        st.paragraph_format.space_after = Pt(0)
        st.paragraph_format.space_before = Pt(0)
        st.paragraph_format.line_spacing = 1.0

    def _footer(self, sec):
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run()
        r.font.size = Pt(8)
        for tag, txt in (("begin", None), (None, "PAGE"), ("end", None)):
            if tag:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), tag)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = txt
            r._r.append(el)

    @staticmethod
    def _set_cols(section, n, space=0.2):
        sp = section._sectPr
        for c in sp.findall(qn("w:cols")):
            sp.remove(c)
        c = OxmlElement("w:cols")
        c.set(qn("w:num"), str(n))
        c.set(qn("w:space"), str(int(space * 1440)))
        sp.append(c)

    def two_columns(self):
        s = self.doc.add_section(WD_SECTION.CONTINUOUS)
        self._set_cols(s, 2)

    def one_column(self):
        s = self.doc.add_section(WD_SECTION.CONTINUOUS)
        self._set_cols(s, 1)

    # ------------------------------------------------------------------ text
    def _resolve(self, text):
        def sub(m):
            kind, key = m.group(1), m.group(2)
            if kind == "c":
                nums = []
                for k in key.split(","):
                    k = k.strip()
                    if k not in self.cite_order:
                        self.cite_order.append(k)
                    nums.append(self.cites_prev.get(k) or self.cite_order.index(k) + 1)
                nums = sorted(set(nums))
                parts, i = [], 0
                while i < len(nums):
                    j = i
                    while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
                        j += 1
                    parts.append(f"[{nums[i]}]–[{nums[j]}]" if j - i >= 2 else ", ".join(f"[{n}]" for n in nums[i:j + 1]))
                    i = j + 1
                return ", ".join(parts)
            v = self.refs_prev.get(f"{kind}:{key}")
            if v is None:
                self.unresolved.add(f"{kind}:{key}")
                return "??"
            return v
        return re.sub(r"\{(fig|tab|eq|sec|c):([^}]+)\}", sub, text)

    TOKEN = re.compile(r"(<i>|</i>|<b>|</b>|<sub>|</sub>|<sup>|</sup>|<bi>|</bi>|<tt>|</tt>)")

    def runs(self, p, text, size=None, italic=False, bold=False, color=None):
        text = self._resolve(text)
        st = dict(i=italic, b=bold, sub=False, sup=False, tt=False)
        for tok in self.TOKEN.split(text):
            if tok in ("<i>", "</i>"):
                st["i"] = tok == "<i>" or italic
            elif tok in ("<b>", "</b>"):
                st["b"] = tok == "<b>" or bold
            elif tok in ("<bi>", "</bi>"):
                st["i"] = st["b"] = tok == "<bi>"
            elif tok in ("<sub>", "</sub>"):
                st["sub"] = tok == "<sub>"
            elif tok in ("<sup>", "</sup>"):
                st["sup"] = tok == "<sup>"
            elif tok in ("<tt>", "</tt>"):
                st["tt"] = tok == "<tt>"
            elif tok:
                r = p.add_run(html.unescape(tok))
                r.italic, r.bold = st["i"], st["b"]
                r.font.subscript, r.font.superscript = st["sub"], st["sup"]
                r.font.name = "Courier New" if st["tt"] else FONT
                r._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
                if size or st["tt"]:
                    r.font.size = Pt((size or BODY_PT) - (1.0 if st["tt"] else 0))
                if color:
                    r.font.color.rgb = RGBColor.from_string(color)
        return p

    def para(self, text, align="j", size=None, italic=False, bold=False, after=3, before=0, indent=0.0,
             first=0.0, keep_next=False, color=None):
        p = self.doc.add_paragraph()
        p.alignment = {"j": WD_ALIGN_PARAGRAPH.JUSTIFY, "c": WD_ALIGN_PARAGRAPH.CENTER,
                       "l": WD_ALIGN_PARAGRAPH.LEFT, "r": WD_ALIGN_PARAGRAPH.RIGHT}[align]
        pf = p.paragraph_format
        pf.space_after, pf.space_before = Pt(after), Pt(before)
        pf.left_indent = Inches(indent)
        pf.first_line_indent = Inches(first)
        pf.keep_with_next = keep_next
        pf.widow_control = True
        self.runs(p, text, size=size, italic=italic, bold=bold, color=color)
        return p

    def body(self, text):
        return self.para(text, first=0.17, after=3)

    def sec(self, title, label=None):
        self.nsec += 1
        self.nsub = 0
        if label:
            self.refs[f"sec:{label}"] = f"Section {roman(self.nsec)}"
        p = self.para(f"{roman(self.nsec)}. {title.upper()}", align="c", size=9, bold=True, before=7, after=3, keep_next=True)
        return p

    def sub(self, title, label=None):
        self.nsub += 1
        letter = chr(64 + self.nsub)
        if label:
            self.refs[f"sec:{label}"] = f"Section {roman(self.nsec)}-{letter}"
        return self.para(f"{letter}. {title}", align="l", italic=True, size=BODY_PT, before=3, after=2, keep_next=True)

    def run_in(self, head, text):
        return self.para(f"<bi>{head}.</bi> {text}", first=0.17)

    def bullets(self, items, size=None):
        for it in items:
            p = self.para("•\t" + it, indent=0.17, first=-0.17, after=1.5, size=size)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(0.17))
        self.doc.paragraphs[-1].paragraph_format.space_after = Pt(3)

    # ------------------------------------------------------------------ equations
    @staticmethod
    def _merge_runs(el):
        """Merge adjacent m:r runs with identical properties so that words are not letter-spaced."""
        M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
        for parent in el.iter():
            kids = list(parent)
            prev = None
            for k in kids:
                if k.tag == M + "r" and all(c.tag in (M + "rPr", M + "t") for c in k):
                    rp = k.find(M + "rPr")
                    key = etree.tostring(rp) if rp is not None else b""
                    t = k.find(M + "t")
                    if prev is not None and prev[0] == key and t is not None and t.text and t.text != " " and prev[1].text != " ":
                        prev[1].text += t.text
                        parent.remove(k)
                        continue
                    prev = (key, t) if t is not None else None
                else:
                    prev = None

    @staticmethod
    def omml(latex):
        latex = re.sub(r"_\{([A-Za-z]{2,})\}", r"_{\\mathrm{\1}}", latex)
        latex = latex.replace(",max}", ",\\mathrm{max}}")
        md = f"${latex}$\n"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "e.docx"
            subprocess.run(["pandoc", "-f", "markdown", "-t", "docx", "-o", str(out)], input=md.encode(), check=True)
            with zipfile.ZipFile(out) as z:
                xml = z.read("word/document.xml")
        root = etree.fromstring(xml)
        ns = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
        el = root.find(".//m:oMath", ns)
        if el is None:
            raise ValueError("pandoc produced no OMML for: " + latex)
        Paper._merge_runs(el)
        return el

    def eq(self, latex, label=None):
        self.neq += 1
        if label:
            self.refs[f"eq:{label}"] = f"({self.neq})"
        p = self.doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before, pf.space_after = Pt(2), Pt(3)
        pf.tab_stops.add_tab_stop(Inches(COL_W / 2), WD_TAB_ALIGNMENT.CENTER)
        pf.tab_stops.add_tab_stop(Inches(COL_W), WD_TAB_ALIGNMENT.RIGHT)
        p.add_run("\t")
        p._p.append(self.omml(latex))
        r = p.add_run(f"\t({self.neq})")
        r.font.name = FONT
        return p

    # ------------------------------------------------------------------ figures
    def figure(self, path, caption, label, wide=False, width=None):
        self.nfig += 1
        self.refs[f"fig:{label}"] = f"Fig. {self.nfig}"
        if wide:
            self.one_column()
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(1)
        p.add_run().add_picture(str(path), width=Inches(width or (FULL_W if wide else COL_W)))
        self.para(f"Fig. {self.nfig}. {caption}", align="j", size=8, after=5)
        if wide:
            self.two_columns()

    # ------------------------------------------------------------------ tables
    @staticmethod
    def _border(cell, **kw):
        tcPr = cell._tc.get_or_add_tcPr()
        b = tcPr.find(qn("w:tcBorders"))
        if b is None:
            b = OxmlElement("w:tcBorders")
            tcPr.append(b)
        for edge, (sz, color) in kw.items():
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), str(sz))
            e.set(qn("w:color"), color)
            b.append(e)

    def table(self, caption, label, header, rows, widths, size=7.5, wide=False, shade=None):
        """Table whose caption is its own first (merged, borderless) row so caption and body never separate."""
        self.ntab += 1
        self.refs[f"tab:{label}"] = f"TABLE {roman(self.ntab)}"
        if wide:
            self.one_column()
        n = len(header)
        outer = self.doc.add_table(rows=1, cols=1)
        outer.alignment = WD_TABLE_ALIGNMENT.CENTER
        outer.autofit = False
        olay = OxmlElement("w:tblLayout")
        olay.set(qn("w:type"), "fixed")
        outer._tbl.tblPr.append(olay)
        outer._tbl.tblPr.append(parse_xml('<w:tblCellMar xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                          '<w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>'
                                          '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar>'))
        outer.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        ocell = outer.cell(0, 0)
        ocell.width = Inches(FULL_W if wide else COL_W)
        outer.columns[0].width = Inches(FULL_W if wide else COL_W)
        t = ocell.add_table(rows=2, cols=n)
        for pp in ocell.paragraphs:  # mandatory empty paragraphs around the nested table: make them negligible
            pp.paragraph_format.space_after = Pt(0)
            pp.paragraph_format.space_before = Pt(0)
            pp.paragraph_format.line_spacing = Pt(1)
            for r in pp.runs:
                r.font.size = Pt(1)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        tblPr = t._tbl.tblPr
        lay = OxmlElement("w:tblLayout")
        lay.set(qn("w:type"), "fixed")
        tblPr.append(lay)
        mar = parse_xml('<w:tblCellMar xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        '<w:top w:w="15" w:type="dxa"/><w:left w:w="45" w:type="dxa"/>'
                        '<w:bottom w:w="15" w:type="dxa"/><w:right w:w="45" w:type="dxa"/></w:tblCellMar>')
        tblPr.append(mar)
        scale = (FULL_W if wide else COL_W) / sum(widths)
        widths = [w * scale for w in widths]

        def fill(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, sz=None):
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = align
            p.paragraph_format.space_after = Pt(0)
            self.runs(p, str(text), size=sz or size, bold=bold)
            return p

        cap = t.cell(0, 0).merge(t.cell(0, n - 1))
        fill(cap, f"TABLE {roman(self.ntab)}", align=WD_ALIGN_PARAGRAPH.CENTER, sz=8)
        p2 = cap.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.paragraph_format.space_after = Pt(2)
        self.runs(p2, caption.upper(), size=7.5)
        for i, h in enumerate(header):
            fill(t.rows[1].cells[i], h, bold=True)
            self._border(t.rows[1].cells[i], top=(8, "000000"), bottom=(4, "000000"))
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                fill(cells[i], v)
                if ri == len(rows) - 1:
                    self._border(cells[i], bottom=(8, "000000"))
        for i, w in enumerate(widths):
            t.columns[i].width = Inches(w)
        for ri, row in enumerate(t.rows):
            trPr = row._tr.get_or_add_trPr()
            trPr.append(OxmlElement("w:cantSplit"))
            if ri >= 1:
                for i, w in enumerate(widths):
                    row.cells[i].width = Inches(w)
        if len(rows) <= 18 and not wide:
            for row in t.rows[:-1]:
                for c in row.cells:
                    for pp in c.paragraphs:
                        pp.paragraph_format.keep_with_next = True
        else:
            for ri in (0, 1):  # long tables: repeat caption and header on continuation pages
                t.rows[ri]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
            for ri in (0, 1):
                for c in t.rows[ri].cells:
                    for pp in c.paragraphs:
                        pp.paragraph_format.keep_with_next = True
        self.para("", after=3, size=3)
        if wide:
            self.two_columns()

    # ------------------------------------------------------------------ references
    def references(self, db):
        self.para("REFERENCES", align="c", size=9, bold=True, before=7, after=3, keep_next=True)
        for n, k in enumerate(self.cite_order, 1):
            p = self.para(f"[{n}]\t{db[k]}", size=7.5, align="j", after=1.5, indent=0.28, first=-0.28)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(0.28))

    def finish(self):
        return dict(refs=self.refs, cites={k: i + 1 for i, k in enumerate(self.cite_order)})
