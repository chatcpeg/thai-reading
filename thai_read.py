# -*- coding: utf-8 -*-
r"""thai_read - turn Thai text into the way it is SAID, for TTS / AI voice models (style "C": syllables joined by "-").

Why: many voice models read Thai letter by letter, so silent letters (การันต์ ์), hidden linking syllables
(ราชการ = ราด-ชะ-กาน), Pali/Sanskrit loanwords, abbreviations and digits come out wrong. Feed the voice model the
reading; keep the correct spelling for subtitles. Rule of the tool: when it is not sure, it leaves the text as written,
so the output is never worse than the input.

    ตระหง่าน -> ตระ-หง่าน    อุโบสถ -> อุ-โบ-สด    ค่าธรรมเนียม -> ค่า-ทำ-เนียม    ราชการ -> ราด-ชะ-กาน
    พ.ศ. 2560 -> พอ-สอ สองพันห้าร้อยหกสิบ    08:30 น. -> แปด นาฬิกา สามสิบ นาที    35.50 บาท -> สามสิบห้า จุด ห้า ศูนย์ บาท

Usage (Python 3.8+, standard library only):
    python thai_read.py --text "พระปรางค์สูงตระหง่าน"          -> the reading (one line per input line)
    python thai_read.py --text "..." --json                     -> {"input", "reading", "changes": [...]}
    python thai_read.py file.txt [file2.srt ...] [--out DIR]    -> file_อ่าน.txt beside it, same layout, Thai changed
    python thai_read.py --stdin [--json] < in.txt               -> one reading per input line
    python thai_read.py --teach ธรรมเนียม ทำ-เนียม               -> saved in data/my_readings.txt (wins over everything)
    python thai_read.py                                          -> interactive menu
Options: --mode irregular (default: only spellings that mislead) | changed (every word whose reading differs)
         | all (every dictionary word in style C) · --pali · --no-numbers · --keys a,b (JSON keys / TSV header names)
Priority: data/my_readings.txt > data/keep_as_written.txt > data/thai_readings.txt (> Pali rules with --pali)
Exit codes: 0 ok · 1 a file / stdin / --teach failed · 2 bad arguments · 3 data files missing
Data: Wiktionary (CC BY-SA 4.0) + PyThaiNLP TNC frequencies (CC0) - see data/LICENSE. Code: MIT.
"""
import argparse, io, json, os, re, sys

__version__ = "1.2.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MY_FILE = os.environ.get("THAI_READ_MY") or os.path.join(DATA, "my_readings.txt")
PINTHU = "ฺ"
# Thai LETTERS (consonants, vowels, tone marks) - not ฯ (0E2F), ๆ (0E46), ฿ (0E3F), digits ๐-๙, ๏ ๚ ๛
LETTER = "ก-ฮะ-ฺเ-ๅ็-๎"
RUN = re.compile("([%s]+)" % LETTER)
THAI_ANY = re.compile("[฀-๿]")
CONS = "ก-ฮ"
WS = r"[^\S\r\n]"                      # space, tab, NBSP ... but never a line break
COMMON_RANK = 2500                     # data/common_words.txt holds this many (ordered by frequency)
TOP_FREQUENT = 400                     # very frequent words never take a compound (bound) form: คุณ, ราคา ...
# words that follow another word Thai-style (head first): ประเทศ+ไทย = ประ-เทด-ไท, no linking syllable
NOT_SAMAS_HEAD = {"ไทย", "จีน", "ลาว", "ญวน", "เขมร", "พม่า", "มอญ"}
# generated words are wrapped in noncharacters U+FDD0/U+FDD1 so the dictionary never respells them again
# (2019 = สองพันสิบเก้า, not สองพัน-สิบ-ก้าว); the same marks in the INPUT are removed first.
NUM_OPEN, NUM_CLOSE = "﷐", "﷑"
MARKUP = re.compile(r"(<[^<>\r\n]*>|\{\\[^{}\r\n]*\})")      # <font ...>, {\an8} in subtitles - never touched

# ------------------------------------------------------------------ comparing spelling and reading


def plain(s):
    """reading without syllable marks: ตฺระ-หฺง่าน -> ตระหง่าน"""
    return re.sub(r"[\s\-ฺ]", "", s or "")


_CLASS = str.maketrans("ขฃฅฆฉฌซศษญฎฏฐฑฒถธณผภฝฬฮใ", "คคคคชชสสสยดตทททททนพพฟลหไ")
# the sound a consonant makes at the END of a syllable
_FINAL = {}
for _g, _f in (("กขคฆ", "ก"), ("จฉชซฌฎฏฐฑฒดตถทธศษส", "ด"), ("บปพฟภ", "บ"), ("ญณนรลฬ", "น"),
               ("ม", "ม"), ("ง", "ง"), ("ย", "ย"), ("ว", "ว")):
    for _c in _g:
        _FINAL[_c] = _f


def _finals(s):
    """map consonants that close a syllable to their final sound (ราช -> ราด, อาหาร -> อาหาน, ทูป -> ทูบ)"""
    out = list(s)
    for i, ch in enumerate(s):
        if ch not in _FINAL or i == 0:
            continue
        nxt = s[i + 1] if i + 1 < len(s) else ""
        closes = (nxt == "" or re.match("[%s]" % CONS, nxt)) and re.match("[ะ-ู็่-๋]", s[i - 1])
        if closes:
            out[i] = _FINAL[ch]
    return "".join(out)


def norm(s):
    """what a reader would say from the letters, as comparable text: ห/อ นำ dropped, tone marks dropped, sound-alike
    letters merged, ำ = าม, ะ dropped, syllable finals mapped (ผู้ = พู่, ใหญ่ = ไหย่, สนาม = สะ-หนาม, น้ำ = น้าม)."""
    s = plain(s)
    s = re.sub("ห(?=[งญนมยรลว])", "", s)
    s = re.sub("อ(?=ย)", "", s)
    s = re.sub("[็-๋]", "", s)
    s = s.replace("ำ", "าม").translate(_CLASS)
    return _finals(s).replace("ะ", "")


def needs_respell(word, reading):
    """reading differs from the spelling at all (or splits a leading-ห cluster: ตระ-หง่าน)"""
    if not reading:
        return False
    return plain(reading) != plain(word) or bool(re.search(r"-[เแโใไ]?ห[งญนมยรลว]", reading))


def linking_syllable(reading):
    """a ะ-syllable whose onset repeats the previous syllable's final sound (ราด-ชะ, ผน-ละ, จัก-กระ, ทด-สะ):
    a syllable that is said but not written. Not: สะ-หนาม, ชะ-นะ (the ะ only opens the word)."""
    syl = reading.split("-")
    for i in range(1, len(syl)):
        s, prev = syl[i], syl[i - 1]
        if not s.endswith("ะ") or not prev:
            continue
        onset = re.match("[เแโใไ]?([%s])" % CONS, s)
        coda = prev[-1]
        if onset and coda in "กดบนมงยว" and _FINAL.get(onset.group(1)) == coda and not re.search("[ะาีืูอ]$|[่-๋]$", prev):
            return True
    return False


def irregular_reason(word, reading, is_common=lambda w: False):
    """Why the SPELLING misleads a reader (mode "irregular"), or "" if a voice model can read it as written.
    Everyday words and phrases that only differ in phonemic notation (ผู้ -> พู่, ร้านอาหาร, อย่างไรก็ตาม) stay."""
    if not needs_respell(word, reading):
        return ""
    if "์" in word:
        return "silent letter (์)"
    if linking_syllable(reading):
        return "hidden linking syllable"
    if re.search("ะห[งญนมยรลว]", word):
        return "leading ห after ะ"
    if not is_common(word) and norm(word) != norm(reading):
        return "rare word, read differently"
    return ""


def is_irregular(word, reading, common=()):
    return bool(irregular_reason(word, reading, lambda w: w in common))


# ------------------------------------------------------------------ data files


def _read_pairs(path, keep_spaces=False):
    """'word<TAB>value' or 'word = value  # note' lines -> {word: value}; '#' lines are comments"""
    out = {}
    if not os.path.isfile(path):
        return out
    with io.open(path, encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    for ln in lines:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        ln = re.sub(r"\s+#.*$", "", ln)
        if "\t" in ln:
            k, _, v = ln.partition("\t")
            v = v.split("\t")[0]
        elif "=" in ln:
            k, _, v = ln.partition("=")
        else:
            k, v = ln, ""
        k, v = k.strip(), v.strip()
        if k:
            out[k] = v if keep_spaces else re.sub(r"\s+", "-", v)
    return out


def _read_list(path):
    out = []
    if os.path.isfile(path):
        with io.open(path, encoding="utf-8-sig") as fh:
            for ln in fh.read().splitlines():
                ln = re.sub(r"\s+#.*$", "", ln).strip()
                if ln and not ln.startswith("#"):
                    out.append(ln)
    return out


# ------------------------------------------------------------------ numbers, dates, abbreviations

_DIG = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_POS = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]
_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน",
           "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def num_th(n):
    """2560 -> สองพันห้าร้อยหกสิบ · 21 -> ยี่สิบเอ็ด · 101 -> หนึ่งร้อยเอ็ด · 1000000 -> หนึ่งล้าน"""
    n = int(n)
    if n == 0:
        return _DIG[0]
    if n >= 1000000:
        hi, lo = divmod(n, 1000000)
        return num_th(hi) + "ล้าน" + (num_th(lo) if lo else "")
    s, digits = "", str(n)
    for i, ch in enumerate(digits):
        d, pos = int(ch), len(digits) - i - 1
        if d == 0:
            continue
        if pos == 1:
            s += ("" if d == 1 else "ยี่" if d == 2 else _DIG[d]) + "สิบ"
        elif pos == 0:
            s += "เอ็ด" if d == 1 and n > 10 else _DIG[d]
        else:
            s += _DIG[d] + _POS[pos]
    return s


def number_words(tok):
    """'1,234.50' -> หนึ่งพันสองร้อยสามสิบสี่ จุด ห้า ศูนย์"""
    whole, _, frac = tok.replace(",", "").partition(".")
    out = num_th(whole)
    if frac:
        out += " จุด " + " ".join(_DIG[int(d)] for d in frac)
    return out


def digits_words(tok):
    """phone / id numbers digit by digit: 02-123-4567 -> ศูนย์ สอง, หนึ่ง สอง สาม, ..."""
    tok = tok.replace("+66", "0")
    groups = [g for g in re.split(r"[-\s]+", tok) if g]
    return ", ".join(" ".join(_DIG[int(d)] for d in g if d.isdigit()) for g in groups)


def _pad(text, start, end, words):
    """spaces around inserted words only where they touch letters or digits (the rest of the layout is kept)"""
    left = " " if start > 0 and re.match(r"[฀-๿\w%s]" % NUM_CLOSE, text[start - 1]) else ""
    right = " " if end < len(text) and re.match(r"[฀-๿\w%s]" % NUM_OPEN, text[end]) else ""
    return left + words + right


def _sub(pattern, fn, text, flags=0):
    out, last = [], 0
    for m in re.finditer(pattern, text, flags):
        rep = fn(m)
        if rep is None:
            continue
        out.append(text[last:m.start()])
        out.append(_pad(text, m.start(), m.end(), rep))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def _time(h, m, s=None):
    h, m = int(h), int(m)
    if h > 24 or m > 59 or (s is not None and int(s) > 59):
        return None
    out = "%s นาฬิกา%s" % (num_th(h), (" " + num_th(m) + " นาที") if m else "")
    if s is not None and int(s):
        out += " %s วินาที" % num_th(s)
    return out


def _date(d, m, y):
    d, m = int(d), int(m)
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return None
    return (num_th(d), _MONTHS[m - 1], num_th(y))


def numbers_to_words(text, abbrev=None, mark=False):
    """digits, times, dates, ranges, %, phone numbers and abbreviations -> spoken Thai. Spaces are added only where a
    spoken word touches Thai text; tabs, line breaks, indentation and NBSP are kept. mark=True wraps the generated
    words in NUM_OPEN/NUM_CLOSE so Reader.read() leaves them alone (month names and เปอร์เซ็นต์ are left open so they
    get the same reading as everywhere else)."""
    def M(x):
        return (NUM_OPEN + x + NUM_CLOSE) if mark and x else x

    def MT(*a):
        r = _time(*a)
        return M(r) if r else None

    def MD(d, m, y):
        r = _date(d, m, y)
        return ("%s %s %s" % (M(r[0]), r[1], M(r[2]))) if r else None

    W, N = WS, NUM
    t = text.translate(_THAI_DIGITS).replace(NUM_OPEN, "").replace(NUM_CLOSE, "")
    for k, v in (abbrev or {}).items():                       # longest first (dict built sorted)
        # 1-2 letter keys (จ. ต. กม. ชม. ม.ค.) must not touch a Thai letter before them (ชีวิต. / เข้าชม. stay);
        # longer ones (กทม. กรุงเทพฯ ฯลฯ) may follow a word directly (จากกทม. ในกรุงเทพฯ)
        short = len(re.sub("[.ฯ]", "", k)) <= 2
        before = r"(?<![฀-๿.])" if short else r"(?<![.])"
        t = _sub(before + re.escape(k) + r"(?![%s]\.)(?!\.)" % CONS, lambda m, v=v: v, t)
    t = _sub(r"พ\s*\.\s*ศ\s*\.", lambda m: M("พอ-สอ"), t)
    t = _sub(r"ค\s*\.\s*ศ\s*\.", lambda m: M("คอ-สอ"), t)
    t = re.sub(r"(?<=[ก-๎])(?=\d)", " ", t)          # "ปี2560" -> separate the digits
    # money: ฿1,200 -> 1,200 บาท · 350.- -> 350
    t = re.sub(r"฿%s*(%s)" % (W, N), r"\1 บาท", t)
    t = re.sub(r"(\d)\.-(?=\s|$|[฀-๿])", r"\1", t)
    # dates: yyyy-mm-dd, d/m/yyyy, d.m.yyyy (a sentence-final "." is allowed), d/m/yy
    t = _sub(r"(?<![\d./-])(\d{4})-(\d{2})-(\d{2})(?![\d-])", lambda m: MD(m.group(3), m.group(2), m.group(1)), t)
    t = _sub(r"(?<![\d.:/])(\d{1,2})([./])(\d{1,2})\2(\d{4}|\d{2})(?![\d/]|\.\d)",
             lambda m: MD(m.group(1), m.group(3), m.group(4)), t)
    # ratios / scale: 1:50,000 · อัตราส่วน 1:10 -> ต่อ
    t = re.sub(r"(อัตราส่วน|มาตราส่วน|สัดส่วน)(%s*)(%s):(%s)" % (W, N, N), lambda m: m.group(1) + (m.group(2) or " ") + M(
        "%s ต่อ %s" % (number_words(m.group(3)), number_words(m.group(4)))), t)
    t = _sub(r"(?<![\d.:])(\d{1,3}):(\d{1,3}(?:,\d{3})+)", lambda m: M("%s ต่อ %s" % (
        number_words(m.group(1)), number_words(m.group(2)))), t)
    # durations h:mm:ss
    t = _sub(r"(?<![\d.:])(\d{1,2}):(\d{2}):(\d{2})(?![\d:])", lambda m: MT(m.group(1), m.group(2), m.group(3)), t)
    # time ranges 09.00 น. - 12.00 น. / 10:00-16:00
    TT = r"(\d{1,2})([:.])(\d{2})(%s*น\.)?" % W
    t = _sub(r"(?<![\d.:])%s%s*[-–]%s*(\d{1,2})([:.])(\d{2})(?![\d.:])(%s*น\.)?" % (TT, W, W, W), lambda m: (
        "%s %s %s" % (MT(m.group(1), m.group(3)), M("ถึง"), MT(m.group(5), m.group(7)))
        if ((m.group(2) == ":" and m.group(6) == ":") or m.group(4) or m.group(8))
        and _time(m.group(1), m.group(3)) and _time(m.group(5), m.group(7)) else None), t)
    # times: "08:30" (":" always) or "18.30 น." ("." only with น.)
    t = _sub(r"(?<![\d.:])(\d{1,2}):(\d{2})(?![\d:,])(%s*น\.)?" % W, lambda m: MT(m.group(1), m.group(2)), t)
    t = _sub(r"(?<![\d.:])(\d{1,2})\.(\d{2})%s*น\." % W, lambda m: MT(m.group(1), m.group(2)), t)
    # phone numbers: 0x-xxx-xxxx, 0xx-xxxxxx, 0x-xxxx-xxxx, +66 ..., after โทร/สายด่วน (even with an agency acronym)
    t = _sub(r"(?<![\d,.])(?:\+66[ -]?|0)\d{1,2}(?:[ -]?\d){6,8}(?![\d.,])", lambda m: M(digits_words(m.group(0))), t)
    t = _sub(r"((?:โทร(?:ศัพท์)?|สายด่วน|หมายเลข)\.?%s*(?:[%s]{2,6}\.?%s*)?)(\d[\d-]*\d|\d)" % (W, CONS, W),
             lambda m: m.group(1) + M(digits_words(m.group(2))), t)
    t = _sub(r"(?<![\d,.])0\d+(?![\d.,])", lambda m: M(digits_words(m.group(0))), t)
    # scores after ชนะ/แพ้/เสมอ: 3-1 -> สาม ต่อ หนึ่ง
    t = re.sub(r"(ชนะ|แพ้|เสมอ|สกอร์)(%s*)(\d{1,3})%s*[-–]%s*(\d{1,3})(?!\d)" % (W, W, W),
               lambda m: m.group(1) + (m.group(2) or " ") + M("%s ต่อ %s" % (num_th(m.group(3)), num_th(m.group(4)))), t)
    # 99/1, ฉบับที่ 3/2567 -> ทับ · บาท/คน, กม./ชม. -> ต่อ
    t = _sub(r"(?<![\d/])(%s)/(%s)(?![\d/])" % (N, N), lambda m: M("%s ทับ %s" % (
        number_words(m.group(1)), number_words(m.group(2)))), t)
    t = re.sub(r"(?<=[ก-๎.])/(?=[ก-ฮ])", " ต่อ ", t)
    # ranges and percentages: 10-20% · -1.25% · 1,500-2,000 · -5
    t = _sub(r"(?<![\d.,])(%s)%s*%%?%s*[-–]%s*(%s)%s*%%" % (N, W, W, W, N, W), lambda m: "%s %s %s เปอร์เซ็นต์" % (
        M(number_words(m.group(1))), M("ถึง"), M(number_words(m.group(2)))), t)
    t = _sub(r"(?:(?<=^)|(?<=[\s(]))[-−](%s)%s*%%" % (N, W), lambda m: M("ลบ " + number_words(m.group(1))) + " เปอร์เซ็นต์", t)
    t = _sub(r"(%s)%s*%%" % (N, W), lambda m: M(number_words(m.group(1))) + " เปอร์เซ็นต์", t)
    t = _sub(r"(?<![\d.,])(%s)%s*[-–]%s*(%s)(?![\d])" % (N, W, W, N), lambda m: "%s %s %s" % (
        M(number_words(m.group(1))), M("ถึง"), M(number_words(m.group(2)))), t)
    t = _sub(r"(?:(?<=^)|(?<=[\s(]))[-−](%s)" % N, lambda m: M("ลบ " + number_words(m.group(1))), t)
    t = _sub(N, lambda m: M(number_words(m.group(0))), t)
    # Thai ranges written with a dash between day / month names: วันจันทร์-ศุกร์ -> วันจันทร์ ถึง ศุกร์
    names = "|".join(sorted(_DAYS + _MONTHS, key=len, reverse=True))
    t = re.sub(r"(%s)%s*[-–]%s*(?=(?:วัน)?(?:%s))" % (names, W, W, names), r"\1 ถึง ", t)
    return t


# ------------------------------------------------------------------ Pali (Thai script) - rule-based

_PALI_CONS = set("กขคฆงจฉชฌญฏฐฑฒณตถทธนปผพภมยรลวสหฬอ")


def pali_reading(word):
    """Thai reading of Pali written in Thai script (pinthu ฺ = no vowel, ํ = ṃ). ธมฺม -> ธัม-มะ, เมตฺตา -> เม็ต-ตา,
    รูปํ -> รู-ปัง, กเรยฺย -> กะ-เรย-ยะ. Returns None for spellings the rules do not cover (Thai-phonetic spellings
    with ะ/ั, a ห/ว/ร closing a syllable, pinthu with no following consonant)."""
    w = word.strip()
    if not w or not all(c in _PALI_CONS or c in "าิีุูเโํฺ" for c in w) or w.endswith(PINTHU):
        return None
    units, i = [], 0                          # (pre, cons, vowel, pinthu, nikkhahit)
    while i < len(w):
        pre = ""
        if w[i] in "เโ":
            pre, i = w[i], i + 1
        if i >= len(w) or w[i] not in _PALI_CONS:
            return None
        c, i = w[i], i + 1
        vow, pin, nik = "", False, False
        if i < len(w) and w[i] == PINTHU:
            pin, i = True, i + 1
        elif i < len(w) and w[i] in "าิีุู":
            vow, i = w[i], i + 1
        if i < len(w) and w[i] == "ํ":
            nik, i = True, i + 1
        if pin and pre:
            return None
        units.append((pre, c, vow, pin, nik))
    syl = []                                   # [pre, onset, vowel, final]
    for pre, c, vow, pin, nik in units:
        if pin:
            if syl and not syl[-1][3] and syl[-1][2] is not None:
                if c in "หวร":
                    return None                # ห/ว/ร cannot close a Thai syllable (พฺรหฺม, ชิวฺหา, ปิตรฺ)
                syl[-1][3] = c
            elif not syl:
                syl.append(["", c, None, ""])  # word-initial cluster
            else:
                return None
            continue
        if syl and syl[-1][2] is None:
            syl[-1][1] += c
            syl[-1][0], syl[-1][2] = pre, vow
        else:
            syl.append([pre, c, vow, ""])
        if nik:
            syl[-1][3] = "ง"
    out = []
    for pre, c, vow, fin in syl:
        vow = vow or ""
        if not fin:
            out.append(pre + c + (vow if (vow or pre) else "ะ"))
        elif pre == "เ":
            out.append("เ" + c + ("" if fin == "ย" else "็") + fin)
        elif pre == "โ":
            out.append("โ" + c + fin)
        elif vow:
            out.append(c + vow + fin)
        else:
            out.append(c + "ั" + fin)
    return "-".join(out)


# ------------------------------------------------------------------ the reader


class Reader:
    def __init__(self, data_dir=DATA, use_pali=False, my_file=None):
        self.dict = _read_pairs(os.path.join(data_dir, "thai_readings.txt"))
        if not self.dict:
            raise FileNotFoundError("thai_readings.txt missing or empty in %s - reinstall or run tools/build_data.py"
                                    % data_dir)
        self.bound = _read_pairs(os.path.join(data_dir, "thai_bound_forms.txt"))
        self.origin = _read_pairs(os.path.join(data_dir, "thai_origins.txt"))
        self.pos = {k: set(v.split(",")) for k, v in _read_pairs(os.path.join(data_dir, "thai_pos.txt")).items()}
        ranked = _read_list(os.path.join(data_dir, "common_words.txt"))
        self.rank = {w: i for i, w in enumerate(ranked)}
        self.common = set(ranked)
        self.keep = set(_read_list(os.path.join(data_dir, "keep_as_written.txt")))
        ab = _read_pairs(os.path.join(data_dir, "abbreviations.txt"), keep_spaces=True)
        self.abbrev = dict(sorted(ab.items(), key=lambda kv: -len(kv[0])))
        self.use_pali = use_pali
        self.pali = _read_pairs(os.path.join(data_dir, "pali_thai_script.txt")) if use_pali else {}
        self.my_file = my_file or MY_FILE
        self._common_cache = {}
        self.reload_my()

    def reload_my(self):
        self.my = {k.replace(" ", ""): v for k, v in _read_pairs(self.my_file).items()}
        # single letters (ก = กอ, ว = วอ) would split real words (ราชวราราม -> ราช+ว(วอ)+...)
        self.words = {w for w in set(self.dict) | set(self.pali) | self.keep
                      if len(w) > 1 and RUN.fullmatch(w)} | {w for w in self.my if RUN.fullmatch(w)}
        self.maxlen = max(len(w) for w in self.words)

    # ---- word classes
    def is_common(self, w):
        """an everyday word, or a phrase made only of everyday words (ร้านอาหาร, อย่างไรก็ตาม, น้ำตก)"""
        if w in self.common:
            return True
        if w in self._common_cache:
            return self._common_cache[w]
        n = len(w)
        ok = [True] + [False] * n
        for i in range(n):
            if ok[i]:
                for j in range(i + 2, min(n, i + 12) + 1):
                    if w[i:j] in self.common:
                        ok[j] = True
        self._common_cache[w] = ok[n]
        return ok[n]

    def samas_origin(self, w):
        return self.origin.get(w) in ("pali", "sanskrit")

    # ---- segmentation
    def segment(self, run):
        """maximal matching: fewest unknown letters, then most letters covered by YOUR readings, then fewest tokens,
        ties broken toward the longest first word (ราชการ+มี, not ราช+การมี). Returns [(token, known)]."""
        n = len(run)
        INF = (10 ** 9, 0, 10 ** 9)
        best = [INF] * n + [(0, 0, 0)]
        nxt = [None] * n
        for i in range(n - 1, -1, -1):
            for j in range(min(n, i + self.maxlen), i, -1):          # longest first: ties keep the longest
                w = run[i:j]
                if w in self.words:
                    u, my, t = best[j]
                    cand = (u, my - (len(w) if w in self.my else 0), t + 1)
                    if cand < best[i]:
                        best[i], nxt[i] = cand, (j, True)
            u, my, t = best[i + 1]
            cand = (u + 1, my, t + 1)
            if cand < best[i]:
                best[i], nxt[i] = cand, (i + 1, False)
        toks, i = [], 0
        while i < n:
            j, known = nxt[i]
            toks.append((run[i:j], known))
            i = j
        merged = []
        for tok, known in toks:
            if merged and not known and not merged[-1][1]:
                merged[-1] = (merged[-1][0] + tok, False)
            else:
                merged.append((tok, known))
        return merged

    # ---- readings
    def _restore_keep(self, tok, reading):
        """keep-list words inside a longer entry stay as written too (ทรงพระเจริญ: ซง -> ทรง)"""
        for k in self.keep:
            rk = self.dict.get(k)
            if k != tok and k in tok and rk and rk in reading:
                reading = reading.replace(rk, k)
        return reading

    def word_reading(self, w, mode="irregular"):
        """-> (reading or None, source, reason)"""
        if w in self.my:
            return self.my[w], "my", "your reading"
        if w in self.keep:
            return None, "keep", ""
        r = self.dict.get(w)
        if r:
            if mode == "all":
                why = "all"
            elif mode == "changed":
                why = "changed" if needs_respell(w, r) else ""
            else:
                why = irregular_reason(w, r, self.is_common)
            return (self._restore_keep(w, r), "wiktionary", why) if why else (None, "", "")
        if w in self.pali:
            return self.pali[w], "pali-rule", "pali"
        return None, "", ""

    def bound_form(self, tok, nxt):
        """compound (สมาส) form of tok before nxt, or None. Only for a real Pali/Sanskrit compound: tok and nxt both
        Pali/Sanskrit, tok not one of the most frequent words (คุณ, ราคา), nxt not a Thai-order head (ไทย).
        พระ + X uses X's bound form (พระพุทธ + ศาสนา = พระ-พุด-ทะ-สาด-สะ-หนา)."""
        if tok in self.keep or tok in self.my or nxt in NOT_SAMAS_HEAD or not self.samas_origin(nxt):
            return None
        if not (self.pos.get(nxt, set()) & {"noun", "name"}):     # อากาศ+สบาย (adv), คุณ+สามารถ (verb): Thai order
            return None
        head, core = "", tok
        if tok not in self.bound and tok.startswith("พระ") and tok[3:] in self.bound:
            head, core = "พระ-", tok[3:]
        if core not in self.bound or not self.samas_origin(core) or self.rank.get(core, 10 ** 9) < TOP_FREQUENT:
            return None
        b = self._restore_keep(core, self.bound[core])
        if plain(b) == plain(self.dict.get(core, core)):
            return None
        return head + b

    def read(self, text, mode="irregular", numbers=True):
        """-> (reading, changes [{word, reading, source, why}])"""
        out, changes = [], []
        for part in MARKUP.split(text):                         # subtitle markup is copied as is
            if MARKUP.fullmatch(part or "x"):
                out.append(part)
                continue
            r, ch = self._read_plain(part, mode, numbers)
            out.append(r)
            changes += ch
        return "".join(out), changes

    def _read_plain(self, text, mode, numbers):
        text = text.replace(NUM_OPEN, "").replace(NUM_CLOSE, "")
        if numbers:
            text = numbers_to_words(text, self.abbrev, mark=True)
        out, changes = [], []
        pieces = []                                            # (text, protected)
        for seg in re.split("(%s[^%s]*%s)" % (NUM_OPEN, NUM_CLOSE, NUM_CLOSE), text):
            if seg.startswith(NUM_OPEN) and seg.endswith(NUM_CLOSE):
                pieces.append((seg[1:-1], True))
            else:
                pieces.extend((x, False) for x in RUN.split(seg))
        for chunk, protected in pieces:
            if protected or not chunk or not RUN.fullmatch(chunk):
                out.append(chunk)
                continue
            if self.use_pali and re.search("[ฺํ]", chunk) and chunk not in self.words:
                pr = self.pali.get(chunk) or pali_reading(chunk)     # whole Pali word, before it is split up
                if pr:
                    out.append(pr)
                    changes.append({"word": chunk, "reading": pr, "source": "pali-rule", "why": "pali"})
                    continue
            toks = self.segment(chunk)
            parts = []                                          # (text, converted?)
            for k, (tok, known) in enumerate(toks):
                nxt = toks[k + 1] if k + 1 < len(toks) else None
                glued = (k > 0 and not toks[k - 1][1]) or (nxt is not None and not nxt[1])
                r, src, why = (None, "", "")
                if known and (not glued or tok in self.my):
                    r, src, why = self.word_reading(tok, mode)
                if known and not glued and nxt is not None and nxt[1] and src not in ("my", "keep"):
                    b = self.bound_form(tok, nxt[0])
                    if b:
                        # the linking syllable may already be the next word's first syllable:
                        # บรม (บอ-รม-มะ) + มหาราช (มะ-หา-ราด) -> บอ-รม + มหาราช, said บอ-รม-มะ-หา-ราด
                        rn = (self.dict.get(nxt[0]) or "").split("-")[0]
                        if rn and b.split("-")[-1] == rn and rn.endswith("ะ") and "-" in b:
                            b = b.rsplit("-", 1)[0]
                        r, src, why = b, "wiktionary-bound", "compound"
                    elif r and self.samas_origin(nxt[0]) and nxt[0] not in NOT_SAMAS_HEAD and \
                            len(plain(r)) < len(tok) and self.samas_origin(tok):
                        r = None          # a free form that drops letters before a compound part (ภูมิ+พล) -> as written
                if r:
                    parts.append((r, True))
                    changes.append({"word": tok, "reading": r, "source": src, "why": why})
                else:
                    parts.append((tok, False))
            for k, (p, conv) in enumerate(parts):              # style C: "-" between a respelled word and its
                if k and (conv or parts[k - 1][1]):            # Thai neighbours in the same run (พระ-อุ-โบ-สด)
                    prev = out[-1] if out else ""
                    a, b = prev.split("-")[-1], p.split("-")[0]
                    if conv and parts[k - 1][1] and a == b and a.endswith("ะ"):
                        p = p[len(b) + 1:] if "-" in p else ""  # บอ-รม-มะ + มะ-หา -> one มะ
                        if not p:
                            continue
                    out.append("-")
                out.append(p)
        return "".join(out), changes

    # ---- files: same layout, Thai text only
    def convert_line(self, line, mode="irregular", numbers=True, cols=None):
        body = line.rstrip("\r\n")
        end = line[len(body):]
        if not THAI_ANY.search(body) or body.lstrip().startswith("#"):
            return line
        fields = body.split("\t")
        out = []
        for i, f in enumerate(fields):
            wanted = (i in cols) if cols is not None else not looks_like_path(f)
            out.append(self.read(f, mode, numbers)[0] if wanted and THAI_ANY.search(f) else f)
        return "\t".join(out) + end

    def convert_json(self, x, mode="irregular", numbers=True, keys=None, _key=None):
        if isinstance(x, str):
            wanted = (_key in keys) if keys else not looks_like_path(x)
            return self.read(x, mode, numbers)[0] if wanted and THAI_ANY.search(x) else x
        if isinstance(x, list):
            return [self.convert_json(v, mode, numbers, keys, _key) for v in x]
        if isinstance(x, dict):
            return {k: self.convert_json(v, mode, numbers, keys, k) for k, v in x.items()}
        return x

    def _json_text(self, raw, mode, numbers, keys):
        data = json.loads(raw)
        m = re.search(r"\n([ \t]+)\S", raw)
        if m:
            ind = m.group(1)
            text = json.dumps(self.convert_json(data, mode, numbers, keys), ensure_ascii=False,
                              indent=(len(ind) if ind.strip(" ") == "" else ind))
        elif "\n" not in raw.strip() and re.search(r'":\S', raw):
            text = json.dumps(self.convert_json(data, mode, numbers, keys), ensure_ascii=False, separators=(",", ":"))
        else:
            text = json.dumps(self.convert_json(data, mode, numbers, keys), ensure_ascii=False)
        return text

    def convert_file(self, path, out_dir=None, mode="irregular", numbers=True, keys=None, dst=None):
        with io.open(path, "rb") as fh:
            data = fh.read()
        bom = data.startswith(b"\xef\xbb\xbf")
        raw = data.decode("utf-8-sig")                          # UnicodeDecodeError -> caller reports it
        nl = "\r\n" if "\r\n" in raw else "\n"
        stem, ext = os.path.splitext(os.path.basename(path))
        ext_l = ext.lower()
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        dst = dst or os.path.join(out_dir or os.path.dirname(os.path.abspath(path)), "%s_อ่าน%s" % (stem, ext))
        changed = None
        if ext_l == ".json":
            text = self._json_text(raw.replace("\r\n", "\n"), mode, numbers, keys).replace("\n", nl)
            if raw.endswith("\n"):
                text += nl
        elif ext_l == ".jsonl":
            lines = raw.splitlines(True)
            new = []
            for l in lines:
                body = l.rstrip("\r\n")
                new.append((self._json_text(body, mode, numbers, keys) if body.strip() else body) + l[len(body):])
            text = "".join(new)
            changed = sum(1 for a, b in zip(lines, new) if a != b)
        else:
            lines = raw.splitlines(True)
            cols = None
            if keys and ext_l == ".tsv" and lines:
                header = lines[0].rstrip("\r\n").split("\t")
                cols = {i for i, h in enumerate(header) if h in keys or str(i) in keys}
                new = [lines[0]] + [self.convert_line(l, mode, numbers, cols) for l in lines[1:]]
            else:
                new = [self.convert_line(l, mode, numbers) for l in lines]
            text = "".join(new)
            changed = sum(1 for a, b in zip(lines, new) if a != b)
        with io.open(dst, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            f.write(text)
        return dst, changed

    def teach(self, word, reading):
        word = re.sub(r"\s+", "", word)                         # Thai runs have no spaces - a spaced key never matches
        reading = re.sub(r"\s+", "-", reading.strip())
        if not word or not reading:
            raise ValueError("word and reading are both required")
        if not RUN.fullmatch(word):
            raise ValueError("'%s' cannot be matched: only Thai letters (no digits, Latin, ๆ or ฯ - use "
                             "data/abbreviations.txt for those)" % word)
        exists = os.path.isfile(self.my_file)
        need_nl = False
        if exists and os.path.getsize(self.my_file):
            with io.open(self.my_file, "rb") as fh:
                need_nl = not fh.read().endswith(b"\n")
        with io.open(self.my_file, "a", encoding="utf-8", newline="\n") as f:
            if not exists:
                f.write("# my readings - win over every other source.  word = read-ing (syllables joined by -)\n")
            if need_nl:
                f.write("\n")
            f.write("%s = %s\n" % (word, reading))
        self.reload_my()
        return word, reading


def looks_like_path(s):
    """a file path / URL / file name with no spaces (ภาพ/วัด01.jpg, https://...) - never converted"""
    s = s.strip()
    if not s or re.search(r"\s", s):
        return False
    return bool(re.match(r"^(?:https?://|[A-Za-z]:[\\/]|[\\/])", s) or re.search(r"[\\/]", s)
                or re.search(r"\.[A-Za-z0-9]{2,4}$", s))


# ------------------------------------------------------------------ CLI


def _menu(R, mode, numbers):
    try:
        while True:
            print("\n==== thai_read %s - Thai text -> reading (style C) ====" % __version__)
            print("  [1] word / sentence -> reading")
            print("  [2] file -> <name>_อ่าน<ext> (.txt .srt .tsv .json .jsonl)")
            print("  [3] teach a reading (saved in data/my_readings.txt)")
            print("  [Q] quit")
            c = input("> ").strip().lower()
            if c == "1":
                while True:
                    t = input("\ntext (empty = back): ").strip()
                    if not t:
                        break
                    r, ch = R.read(t, mode, numbers)
                    print("  reading: %s" % r)
                    for x in ch:
                        print("     %-18s -> %-22s (%s: %s)" % (x["word"], x["reading"], x["source"], x["why"]))
            elif c == "2":
                p = input("file path (drag & drop): ").strip()
                p = p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p.replace("\\ ", " ")
                try:
                    dst, n = R.convert_file(p, mode=mode, numbers=numbers)
                    print("  [ok] -> %s%s" % (dst, "" if n is None else " (%d lines changed)" % n))
                except UnicodeDecodeError:
                    print("  [error] not UTF-8 - save the file as UTF-8 first")
                except (OSError, ValueError) as e:
                    print("  [error] %s" % e)
            elif c == "3":
                w = input("  word: ").strip()
                r = input("  reading (e.g. ทำ-เนียม): ").strip()
                if w and r:
                    try:
                        print("  [ok] %s = %s" % R.teach(w, r))
                    except (OSError, ValueError) as e:
                        print("  [error] %s" % e)
            elif c in ("q", "quit", "exit"):
                return 0
    except (EOFError, KeyboardInterrupt):
        print()
        return 0


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure") and not s.isatty():
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--text")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--json", action="store_true", help="with --text / --stdin: JSON output")
    ap.add_argument("--out", help="output folder for converted files (created if missing)")
    ap.add_argument("--mode", choices=("irregular", "changed", "all"), default="irregular",
                    help="irregular (default): only misleading spellings · changed: every word whose reading differs "
                         "from the spelling · all: every dictionary word in style C")
    ap.add_argument("--pali", action="store_true", help="also read Pali written in Thai script (rule-based)")
    ap.add_argument("--no-numbers", action="store_true", help="leave digits, times and abbreviations alone")
    ap.add_argument("--keys", help="JSON keys or TSV header names (or column numbers) to convert, comma separated")
    ap.add_argument("--teach", nargs=2, metavar=("WORD", "READING"))
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)
    modes = sum(1 for x in (a.text is not None, a.stdin, bool(a.teach), bool(a.files)) if x)
    if modes > 1:
        ap.error("use only one of: --text, --stdin, --teach, files")
    if a.json and (a.files or a.teach):
        ap.error("--json works with --text or --stdin")
    if a.keys and not a.files:
        ap.error("--keys works with .json / .jsonl / .tsv files")
    try:
        R = Reader(use_pali=a.pali)
    except FileNotFoundError as e:
        print("error: %s" % e, file=sys.stderr)
        return 3
    numbers = not a.no_numbers
    if a.teach:
        try:
            print("%s = %s" % R.teach(*a.teach))
            return 0
        except (OSError, ValueError) as e:
            print("error: %s" % e, file=sys.stderr)
            return 1
    if a.text is not None or a.stdin:
        if a.text is not None:
            text = a.text
        else:
            try:
                text = sys.stdin.buffer.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                print("error: stdin is not UTF-8", file=sys.stderr)
                return 1
        text = text.lstrip("﻿")
        outs = []
        for line in text.splitlines() or [""]:
            r, ch = R.read(line, a.mode, numbers=numbers)
            outs.append({"input": line, "reading": r, "changes": ch})
        if a.json:
            print(json.dumps(outs[0] if len(outs) == 1 else outs, ensure_ascii=False))
        else:
            print("\n".join(o["reading"] for o in outs))
        return 0
    if a.files:
        rc, used = 0, set()
        keys = set(k.strip() for k in a.keys.split(",")) if a.keys else None
        for p in a.files:
            p = p.strip().strip('"')
            ext = os.path.splitext(p)[1].lower()
            if keys and ext not in (".json", ".jsonl", ".tsv"):
                print("[warn] %s: --keys only applies to .json / .jsonl / .tsv - converting every Thai text" % p,
                      file=sys.stderr)
            if ext not in (".txt", ".srt", ".tsv", ".json", ".jsonl", ".md", ".vtt", ".ass", ""):
                print("[warn] %s: unknown type - every Thai text in it is converted as plain text" % p, file=sys.stderr)
            stem, e2 = os.path.splitext(os.path.basename(p))
            folder = a.out or os.path.dirname(os.path.abspath(p))
            dst, k = os.path.join(folder, "%s_อ่าน%s" % (stem, e2)), 2
            while os.path.normcase(os.path.abspath(dst)) in used:              # two inputs with the same name
                dst, k = os.path.join(folder, "%s_อ่าน(%d)%s" % (stem, k, e2)), k + 1
            try:
                dst, n = R.convert_file(p, a.out, a.mode, numbers, keys, dst=dst)
                used.add(os.path.normcase(os.path.abspath(dst)))
                print("[ok] %s -> %s%s" % (p, dst, "" if n is None else " (%d lines changed)" % n))
            except UnicodeDecodeError:
                print("[error] %s: not UTF-8 (save it as UTF-8 first)" % p, file=sys.stderr)
                rc = 1
            except (OSError, ValueError) as e:
                print("[error] %s: %s" % (p, e), file=sys.stderr)
                rc = 1
        return rc
    return _menu(R, a.mode, numbers)


if __name__ == "__main__":
    sys.exit(main())
