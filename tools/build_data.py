# -*- coding: utf-8 -*-
"""Build data/ from Wiktionary (via kaikki.org / wiktextract, CC BY-SA 4.0) + PyThaiNLP TNC frequencies (CC0).

    python tools/build_data.py            # downloads the dumps into _raw/ if missing, then builds data/
    python tools/build_data.py --offline  # use what is in _raw/

Needs (build only - thai_read.py itself is standard library): pythainlp (TNC word frequencies, CC0).

Sources:
  _raw/kaikki-Thai.jsonl     English Wiktionary, Thai entries   - sounds[] "Phonemic" (+ "bound form")
  _raw/th-extract.jsonl.gz   Thai Wiktionary, all entries       - sounds[] tag "phoneme"
  _raw/kaikki-Pali.jsonl     English Wiktionary, Pali entries   - Thai-script forms (reading = rules, thai_read.pali_reading)
  pythainlp corpus tnc_freq  Thai National Corpus word frequencies (PyThaiNLP, CC0) -> common_words.txt

Output (UTF-8, tab separated, sorted):
  data/thai_readings.txt       word<TAB>reading        free forms, style C (syllables joined by "-"), sanity-checked
  data/thai_bound_forms.txt    word<TAB>bound form     how a word is said as the first part of a compound (พุทธ -> พุด-ทะ)
  data/thai_origins.txt        word<TAB>origin         pali / sanskrit / khmer / chinese / english ... (borrowings only)
  data/thai_readings_full.tsv  word reading bound_form origin source changed
  data/suspect_readings.tsv    rows dropped by the sanity gate (not used by the reader) with the reason
  data/common_words.txt        the most frequent Thai words (TNC rank < 2500)
  data/pali_thai_script.txt    word<TAB>reading        Pali in Thai script, RULE-BASED
"""
import argparse, gzip, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "_raw")
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, ROOT)
import thai_read as T  # noqa: E402

DUMPS = {
    "kaikki-Thai.jsonl": "https://kaikki.org/dictionary/Thai/kaikki.org-dictionary-Thai.jsonl",
    "th-extract.jsonl.gz": "https://kaikki.org/dictionary/downloads/th/th-extract.jsonl.gz",
    "kaikki-Pali.jsonl": "https://kaikki.org/dictionary/Pali/kaikki.org-dictionary-Pali.jsonl",
}
HEADWORD = re.compile(r"^[ก-ฮะ-ฺเ-ๅ็-๎]+$")   # Thai letters only, no spaces/dots
LANGS = {"Pali": "pali", "Sanskrit": "sanskrit", "Old Khmer": "khmer", "Middle Khmer": "khmer", "Khmer": "khmer",
         "Middle Chinese": "chinese", "Teochew": "chinese", "Hokkien": "chinese", "Cantonese": "chinese",
         "Chinese": "chinese", "English": "english", "Malay": "malay", "Persian": "persian", "Portuguese": "portuguese",
         "French": "french", "Japanese": "japanese", "Arabic": "arabic", "Tamil": "tamil", "Mon": "mon",
         "Burmese": "burmese", "Dutch": "dutch", "Hindi": "hindi"}
COMMON_RANK = 2500


def fetch(name):
    p = os.path.join(RAW, name)
    if not os.path.isfile(p):
        os.makedirs(RAW, exist_ok=True)
        print("download", DUMPS[name])
        urllib.request.urlretrieve(DUMPS[name], p + ".part")
        os.replace(p + ".part", p)
    return p


def origin_of(ety):
    """source language only when the etymology states a borrowing/derivation at the start of a sentence
    ('Borrowed from Sanskrit ...', 'From Pali ...'); ignores Compare / Cognate / Calque / 'literally' clauses."""
    if not ety:
        return ""
    for sent in re.split(r"(?<=[.;])\s+|\n", ety):
        m = re.match(r"\s*(?:(?:Semi-|Partially )?[Ll]earned borrowing from|[Bb]orrowed from|[Ff]rom|"
                     r"[Dd]erived from|[Uu]ltimately from)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", sent)
        if not m:
            continue
        name = m.group(1)
        for k in sorted(LANGS, key=len, reverse=True):
            if re.match(r"%s\b" % re.escape(k), name):
                return LANGS[k]
        return ""
    return ""


def clean_reading(r):
    """Wiktionary phonemic notation -> style C for voice models"""
    r = r.strip().replace("ฺ", "")                     # pinthu
    r = re.sub("็(?=[่-๋])|(?<=[่-๋])็", "", r)   # ็ stacked with a tone mark
    r = re.sub("[‐-―−]", "-", r)            # en/em dash or minus used as the syllable joiner
    r = re.sub(r"\s*-\s*", "-", r)
    r = re.sub(r"\s+", "-", r)                              # "กล่าว ขวัน" -> "กล่าว-ขวัน"
    return r


SINGLE_CONS = re.compile(r"(?:^|-)[ก-ฮ](?:-|$)")


def sanity(word, reading):
    """'' if the reading looks plausible for the word, else the reason it is dropped"""
    if not reading:
        return "empty"
    if "์" in reading:
        return "reading keeps a silent-letter mark"
    if SINGLE_CONS.search(reading):
        return "bare single-consonant syllable"
    if not re.fullmatch(r"[ก-๎-]+", reading):
        return "non-Thai characters"
    for pre, rp in (("การ", "กา"), ("ความ", "ความ")):          # การเสียดาย = "ความ-เสีย-ดาย" is wrong;
        if word.startswith(pre) and len(word) > len(pre) + 1 and not plain_r(reading).startswith(rp):   # การบูร fine
            return "reading drops the %s prefix" % pre
    fa, fb = onsets(word), onsets(reading)
    if fa and fb and not (fa & fb) and not any(p in SAME_ONSET for p in ((x, y) for x in fa for y in fb)) \
            and not ("ทร" in word and "ส" in fb):
        return "first consonant differs (%s / %s)" % ("".join(sorted(fa)), "".join(sorted(fb)))
    spoken = re.sub("(?:[ก-ฮ]ร|[ก-ฮ])[ิุ]?์", "", word).replace("รร", "ร")
    a, b = T.norm(spoken), T.norm(reading)
    if len(b) < 0.6 * len(a):
        return "reading much shorter than the word"
    ca = set(re.findall("[ก-ฬ]", a.translate(LOOSE)))       # consonants only (อ = vowel carrier)
    cb = set(re.findall("[ก-ฬ]", b.translate(LOOSE)))
    if len(cb) >= 4 and len(cb & ca) / len(cb) < 0.55:
        return "reading shares too few consonants with the word"
    if abs(len(a) - len(b)) > max(3, len(a) // 2):
        return "length very different from the word"
    return ""


def plain_r(r):
    return T.plain(r)


SAME_ONSET = {("ฤ", "ร"), ("ฦ", "ล"), ("ท", "ด"), ("ฤ", "ล"), ("อ", "ห")}  # ฤดู = รึ-ดู, บัณฑิต, อย่า = หย่า
LOOSE = str.maketrans("ตทสชปพฟคฤฦรลญอ", "ดดดดบบบกรลนนนอ")      # finals ร/ล/ญ read น; อ kept (filtered)


def onsets(s):
    """possible first consonant sounds: as written, and with a leading ห/อ read as ห นำ / อ นำ
    (หน้า = น่า, อย่า = หย่า - but อนุ = อะ-นุ, หนุมาน = หะ-นุ-มาน keep theirs); sound classes merged"""
    s = T.plain(s)
    out = {first_consonant(s.translate(T._CLASS))}
    out.add(first_consonant(re.sub("^([เ-ไ]?)[หอ](?=[งญนมยรลว])", r"\1", s).translate(T._CLASS)))
    return {x for x in out if x}


def first_consonant(s):
    m = re.search("[ก-ฮ]", s)
    return m.group(0) if m else ""


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    paths = {n: (os.path.join(RAW, n) if a.offline else fetch(n)) for n in DUMPS}
    table, pos = {}, {}

    def add(word, reading, bound, origin, source):
        if not HEADWORD.match(word or ""):
            return
        e = table.setdefault(word, {"reading": "", "bound": "", "origin": "", "source": [], "alt": []})
        if reading:
            if not e["reading"]:
                e["reading"] = reading                     # English Wiktionary first (read first), then Thai Wiktionary
            elif reading != e["reading"]:
                e["alt"].append(reading)
        if bound and not e["bound"]:
            e["bound"] = bound
        if origin and not e["origin"]:
            e["origin"] = origin
        if source not in e["source"]:
            e["source"].append(source)

    n = 0
    for line in open(paths["kaikki-Thai.jsonl"], encoding="utf-8"):
        d = json.loads(line)
        n += 1
        reading = bound = ""
        for s in d.get("sounds") or []:
            tags = " ".join((s.get("raw_tags") or []) + (s.get("tags") or []))
            if "Phonemic" in tags and s.get("other"):
                if "bound form" in tags:
                    bound = bound or clean_reading(s["other"])
                else:
                    reading = reading or clean_reading(s["other"])
        add(d.get("word", ""), reading, bound, origin_of(d.get("etymology_text")), "enwikt")
        if HEADWORD.match(d.get("word") or "") and d.get("pos"):
            pos.setdefault(d["word"], [])
            if d["pos"] not in pos[d["word"]]:
                pos[d["word"]].append(d["pos"])
    print("enwiktionary Thai entries", n)
    n = 0
    for line in gzip.open(paths["th-extract.jsonl.gz"], "rt", encoding="utf-8"):
        d = json.loads(line)
        if d.get("lang_code") != "th":
            continue
        n += 1
        reading = ""
        for s in d.get("sounds") or []:
            if "phoneme" in (s.get("tags") or []) and s.get("other"):
                reading = reading or clean_reading(s["other"])
        add(d.get("word", ""), reading, "", "", "thwikt")
    print("thwiktionary Thai entries", n)

    free, bound, origin, suspects = {}, {}, {}, []
    for w, e in sorted(table.items()):
        r = e["reading"]
        if r.endswith("-") or r.startswith("-"):           # bound-only stem (ทัศน -> ทัด-สะ-นะ-)
            if r.endswith("-") and not r.startswith("-") and not e["bound"]:
                e["bound"] = r
            r = ""
        why = sanity(w, r) if r else ""
        if why and e["alt"]:                               # the other Wiktionary edition may have it right
            for alt in e["alt"]:
                if not alt.strip("-") == alt or sanity(w, alt):
                    continue
                r, why = alt, ""
                break
        if why:
            suspects.append((w, r, why, ",".join(e["source"])))
        elif r:
            free[w] = r
        b = e["bound"].strip("-")
        if b and not sanity(w, b) and b != free.get(w):
            bound[w] = b
        if e["origin"]:
            origin[w] = e["origin"]
    os.makedirs(DATA, exist_ok=True)

    def write(name, header, rows):
        with open(os.path.join(DATA, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(header)
            for row in rows:
                f.write("\t".join(row) + "\n")

    lic = "Wiktionary (CC BY-SA 4.0) via kaikki.org - see data/LICENSE"
    write("thai_readings.txt", "# word<TAB>reading (style C: syllables joined by -) - %s\n" % lic, sorted(free.items()))
    write("thai_bound_forms.txt", "# word<TAB>bound form (first part of a compound) - %s\n" % lic, sorted(bound.items()))
    write("thai_origins.txt", "# word<TAB>origin language of a borrowing - %s\n" % lic, sorted(origin.items()))
    # parts of speech of Pali/Sanskrit words: a compound (สมาส) form is used only before a NOUN
    # (พุทธ+ศาสนา), never before an adjective/verb written after a noun Thai-style (อากาศ+สบาย)
    write("thai_pos.txt", "# word<TAB>parts of speech (Pali/Sanskrit-origin words) - %s\n" % lic,
          sorted((w, ",".join(p)) for w, p in pos.items() if origin.get(w) in ("pali", "sanskrit")))
    write("suspect_readings.tsv", "word\treading\twhy_dropped\tsource\n", suspects)
    changed = 0
    with open(os.path.join(DATA, "thai_readings_full.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("word\treading\tbound_form\torigin\tsource\tchanged\n")
        for w in sorted(set(free) | set(bound)):
            ch = int(T.needs_respell(w, free.get(w, "")))
            changed += ch
            f.write("\t".join([w, free.get(w, ""), bound.get(w, ""), origin.get(w, ""),
                               ",".join(table[w]["source"]), str(ch)]) + "\n")
    print("readings %d · bound forms %d · origins %d · suspects dropped %d · read differently %d"
          % (len(free), len(bound), len(origin), len(suspects), changed))
    # common words (PyThaiNLP TNC frequencies, CC0)
    from pythainlp.corpus import tnc
    ranked = [w for w, c in sorted(tnc.word_freqs(), key=lambda x: -x[1]) if HEADWORD.match(w)]
    write("common_words.txt", "# most frequent Thai words (Thai National Corpus frequencies via PyThaiNLP, CC0)\n"
          "# words listed here are treated as everyday words: read as written unless clearly irregular\n",
          [(w,) for w in ranked[:COMMON_RANK]])
    print("common words", min(COMMON_RANK, len(ranked)))
    # Pali in Thai script (rule-based)
    pali = {}
    for line in open(paths["kaikki-Pali.jsonl"], encoding="utf-8"):
        d = json.loads(line)
        for w in [d.get("word", "")] + [x.get("form", "") for x in d.get("forms") or []]:
            w = (w or "").strip()
            if HEADWORD.match(w) and w not in pali:
                r = T.pali_reading(w)
                if r:
                    pali[w] = r
    write("pali_thai_script.txt", "# Pali written in Thai script (Wiktionary Pali entries + inflected forms) -> reading.\n"
          "# RULE-BASED (thai_read.pali_reading), not from a dictionary - check before trusting. %s\n" % lic,
          sorted(pali.items()))
    print("pali thai-script forms", len(pali))


if __name__ == "__main__":
    main()
