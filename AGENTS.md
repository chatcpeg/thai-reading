# For AI agents: how to call thai-reading

Purpose: before sending Thai narration to a voice model, convert it to the spoken reading (style C, syllables
joined by "-"). Never put the converted text in subtitles - subtitles keep the original spelling.

**Call Python directly** (`python thai_read.py ...`, or `py -3 thai_read.py ...` on Windows). Do not pass text
through `ThaiReading.bat`: cmd.exe cannot safely pass arbitrary text that contains `"` together with `& | < > ^`.
The .bat is for people (menu, drag and drop).

## Commands (non-interactive when given arguments)

| Need | Command | Output |
|---|---|---|
| one text | `python thai_read.py --text "<thai>"` | the reading on stdout, one line per input line |
| one text + what changed | `python thai_read.py --text "<thai>" --json` | one object `{"input", "reading", "changes": [{"word", "reading", "source", "why"}]}`; a list of such objects if the text has several lines |
| many lines | `python thai_read.py --stdin [--json] < in.txt` | one reading per input line; with `--json` **always a list** (one object per line). Only `\n` / `\r\n` split lines. A UTF-8 BOM is ignored; non-UTF-8 input is an error |
| files | `python thai_read.py a.txt b.srt c.json d.jsonl e.tsv f.ass [--out DIR] [--keys th,voice]` | writes `a_อ่าน.txt` ... beside each file (or in DIR, created if missing; same names get `(2)`); stdout `[ok] src -> dst (N lines changed)` (no count for .json); a bad file prints `[error] src: reason` on stderr and the others still run |
| teach a fix | `python thai_read.py --teach <word> <read-ing>` | appends to `data/my_readings.txt` (or `$THAI_READ_MY`); wins over every other source, also inside longer dictionary words. The word must be Thai letters only |
| menu (people) | `python thai_read.py --menu` | interactive; with no arguments it opens only when stdin is a terminal, otherwise exit 2 |

Exit codes: 0 ok · 1 a file / stdin / --teach failed · 2 bad arguments or no input · 3 data files missing (broken checkout).
Only one of `--text`, `--stdin`, `--teach`, `--menu`, files per call; `--json` only with `--text`/`--stdin`;
`--keys` only with files (JSON keys / TSV header names or column numbers; ignored with a warning for other types).
`source` is one of `my`, `wiktionary`, `wiktionary-bound` (compound form), `pali-rule`.

**Windows encoding:** set `PYTHONUTF8=1` (or `PYTHONIOENCODING=utf-8`) when capturing stdout. In Windows
PowerShell 5.1 a pipe into Python is ASCII by default (Thai turns into `?`): prefer file arguments or `--text`, or
first run `[Console]::OutputEncoding = $OutputEncoding = [Text.UTF8Encoding]::new()`. PowerShell has no `<`; use
`Get-Content -Encoding UTF8 in.txt | python thai_read.py --stdin` after setting the encoding, or `cmd /c "... < in.txt"`.

Options: `--mode irregular|changed|all` (default `irregular` = only misleading spellings), `--pali`
(rule-based readings of Pali written in Thai script, e.g. ธมฺม), `--no-numbers` (leave digits and abbreviations).

## What the tool already does
- digits -> Thai words (2560 -> สองพันห้าร้อยหกสิบ; 1,200 -> หนึ่งพันสองร้อย; 35.50 -> สามสิบห้า จุด ห้า ศูนย์)
- times: `08:30` and `18.30 น.` (a dot counts as a time only with น.) -> แปด นาฬิกา สามสิบ นาที; ranges `a-b` -> a ถึง b;
  durations: `2:15:30`, `1:30 ชม.`, `ใช้เวลา 1:30` -> ชั่วโมง/นาที; `3:45 นาที`, `ยาว 3:45` -> นาที/วินาที
- dates `12.10.2560`, `12/10/2560`, `12-10-2567`, `2024-10-02` -> day month-name year; `50%` -> ห้าสิบ เปอ-เซ็น;
  `-5` -> ลบ ห้า; `10-20%`, `99/1` (ทับ), `บาท/คน`, `กม./ชม.` (ต่อ - only between a unit and a per-unit word;
  ชาย/หญิง, ไป/กลับ, และ/หรือ stay), `1:50,000` (ต่อ), `฿1,200`, `350.-`, scores after ชนะ/แพ้ (ต่อ)
- phone numbers (02-123-4567, 053-248604, 08-1234-5678, 0 2250 5500, (02) 123-4567, +66 ...), hotlines and numbers
  with a leading 0 are read digit by digit; 5-digit postcodes after ไปรษณีย์ or ending an address too
- era abbreviations are read as the full name: พ.ศ. -> พุด-ทะ-สัก-กะ-หราด, ค.ศ. -> คริด-สัก-กะ-หราด,
  จ.ศ. -> จุน-ละ-สัก-กะ-หราด, ร.ศ. -> รัด-ตะ-นะ-โก-สิน-สก; plus `data/abbreviations.txt` (months, units, จ. ต. ถ. ซ., กทม., titles รศ. ผศ. ดร. นพ. ม.ร.ว., ฯลฯ, กรุงเทพฯ ...);
  1-2 letter abbreviations only when they do not touch a Thai letter (ชีวิต. / เข้าชม. stay)
- words are found by dictionary maximal matching (not substring search); a known word glued to unknown letters
  (part of an unknown compound) and short rare pieces of a long run are left as written; generated number words
  are never respelled again
- subtitle markup (`<font ...>`, `{\an8}`) is copied untouched; NBSP, tabs, indentation, BOM and CRLF are kept;
  `.ass`/`.ssa`: only the Text field of Dialogue lines; `.tsv`: the header row is never changed
- when unsure the tool leaves the text as written: everyday words and phrases made of everyday words are never
  respelled (ผู้, ร้านอาหาร, อย่างไรก็ตาม); compound (linking-syllable) forms only after พุทธ ราช บรม ธรรม before a
  Pali/Sanskrit noun (พุทธ+ศาสนา); a word that might start a compound but is not one of those stays as written

## When a word still sounds wrong
1. Find the right reading (a dictionary, or ask the user).
2. `python thai_read.py --teach <word> <syl-la-bles>` (no spaces in the word).
3. If the respelling sounds worse than the spelling, add the word to `data/keep_as_written.txt`.

## Library use
```python
import thai_read
R = thai_read.Reader()                            # Reader(use_pali=True) to add Pali rules
reading, changes = R.read("ค่าธรรมเนียม 200 บาท")  # -> ("ค่า-ทำ-เนียม สองร้อย บาท", [...])
dst, n = R.convert_file("script.txt")              # -> ("script_อ่าน.txt", lines changed)
```
