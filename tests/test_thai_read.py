# -*- coding: utf-8 -*-
"""python -m unittest discover -s tests   (standard library only)"""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import thai_read as T  # noqa: E402

R = T.Reader(my_file=os.path.join(tempfile.mkdtemp(), "my.txt"))
NBSP = chr(0xA0)
BOM = chr(0xFEFF)
BS = chr(92)                     # backslash


def r(s, **k):
    return R.read(s, **k)[0]


def read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def write_bytes(p, data):
    with open(p, "wb") as f:
        f.write(data)
    return p


class Readme(unittest.TestCase):
    def test_readme_table(self):
        self.assertEqual(r("พระปรางค์สูงตระหง่าน"), "พระ-ปราง-สูง-ตระ-หง่าน")
        self.assertEqual(r("พระอุโบสถ"), "พระ-อุ-โบ-สด")
        self.assertEqual(r("ค่าธรรมเนียม"), "ค่า-ทำ-เนียม")
        self.assertEqual(r("พระพุทธศาสนา"), "พระ-พุด-ทะ-สาด-สะ-หนา")
        self.assertEqual(r("ทศวรรษ 1970"), "ทด-สะ-วัด หนึ่งพันเก้าร้อยเจ็ดสิบ")
        self.assertEqual(r("ราคา 35.50 บาท"), "ราคา สามสิบห้า จุด ห้า ศูนย์ บาท")
        self.assertEqual(r("เปิด 10.00-16.00 น."), "เปิด สิบ นาฬิกา ถึง สิบหก นาฬิกา")
        self.assertEqual(r("ผู้ใหญ่ ภายใน ข้าวเหนียว"), "ผู้ใหญ่ ภายใน ข้าวเหนียว")


class Words(unittest.TestCase):
    def test_irregular(self):
        for w, want in [("อุโบสถ", "อุ-โบ-สด"), ("ประดิษฐาน", "ประ-ดิด-สะ-ถาน"), ("คุณภาพ", "คุน-นะ-พาบ"),
                        ("ราชการ", "ราด-ชะ-กาน"), ("จักรยาน", "จัก-กระ-ยาน"), ("เศรษฐกิจ", "เสด-ถะ-กิด"),
                        ("กาญจนบุรี", "กาน-จะ-นะ-บุ-รี"), ("สถาปัตยกรรม", "สะ-ถา-ปัด-ตะ-ยะ-กำ")]:
            self.assertEqual(r(w), want, w)

    def test_everyday_words_stay(self):
        s = ("ผู้ ใน บาท แม่น้ำ ยิ่งใหญ่ ภายใน ผู้หญิง ข้าวเหนียว เชียงใหม่ ภูเขา ภาษา ประเทศ รถไฟ ถนน สนาม ตลาด "
             "อร่อย ศาลา ถ่ายรูป เกียรติ วิเศษ ชาติ ร้านอาหารแห่งนี้ อย่างไรก็ตาม ยุโรป โรค ตำรวจ เคารพ การศึกษา "
             "ไทยชนะ ขยะ คณะ สนับสนุน คุณสามารถเดินทาง ช่วงนี้อากาศสบาย")
        self.assertEqual(r(s), s)

    def test_keep_list_also_inside_longer_entries(self):
        self.assertNotIn("ซง", r("ทรง ทรงพระเจริญ ความทรงจำ"))

    def test_no_single_letter_or_substring_hits(self):
        self.assertNotIn("วอ", r("วัดอรุณราชวราราม"))
        self.assertEqual(r("วิเศษ", mode="changed"), "วิ-เสด")

    def test_compounds(self):
        self.assertEqual(r("พุทธบาท"), "พุด-ทะ-บาท")
        self.assertEqual(r("พระพุทธศาสนา"), "พระ-พุด-ทะ-สาด-สะ-หนา")
        self.assertIn(r("พระราชฐาน"), ("พระราชฐาน", "พระ-ราด-ชะ-ถาน"))   # never ราด without ชะ
        self.assertEqual(r("ประเทศไทย"), "ประเทศไทย")              # Thai-order phrase, no linking syllable
        self.assertNotIn("พูมพล", r("ภูมิพล"))                      # never a free form that drops a syllable
        out = r("พระบรมมหาราชวัง")
        self.assertNotIn("มะ-มะ", out)
        self.assertNotIn("มะ-มห", out)

    def test_marks_are_boundaries(self):
        self.assertTrue(r("ธรรมดาๆ").endswith("ๆ"))

    def test_no_bad_notation_in_output(self):
        out = r("ไฟส่องสว่าง กล้องถ่ายภาพ กฎแห่งกรรม อร่อย ถ้อยคำ แชมป์ เต็นท์", mode="changed")
        self.assertIsNone(re.search("็[่-๋]|[่-๋]็", out))
        self.assertIsNone(re.search(r"-(\s|$)|(^|\s)-", out))

    def test_modes(self):
        self.assertEqual(r("บาท", mode="changed"), "บาด")
        self.assertEqual(r("แม่น้ำ", mode="all"), "แม่-น้าม")


class Numbers(unittest.TestCase):
    def test_num_th(self):
        self.assertEqual(T.num_th(2560), "สองพันห้าร้อยหกสิบ")
        self.assertEqual(T.num_th(21), "ยี่สิบเอ็ด")
        self.assertEqual(T.num_th(101), "หนึ่งร้อยเอ็ด")
        self.assertEqual(T.num_th(1000000), "หนึ่งล้าน")

    def test_decimals_are_not_times(self):
        self.assertEqual(r("1.85 เมตร"), "หนึ่ง จุด แปด ห้า เมตร")
        self.assertNotIn("นาฬิกา", r("ใช้เวลา 1.30 ชั่วโมง เกรด 3.75 ค่า 99.99"))
        self.assertIn("ยี่สิบห้า", r("25:99"))                       # not a time (minute > 59)

    def test_times_dates_ranges(self):
        self.assertIn("แปด นาฬิกา สามสิบ นาที", r("08:30 น."))
        self.assertIn("สิบแปด นาฬิกา สามสิบ นาที", r("18.30 น."))
        self.assertEqual(r("ปี 2556-2560"), "ปี สองพันห้าร้อยห้าสิบหก ถึง สองพันห้าร้อยหกสิบ")
        self.assertEqual(r("1,500-2,000 บาท"), "หนึ่งพันห้าร้อย ถึง สองพัน บาท")
        self.assertEqual(r("12.10.2560"), "สิบสอง ตุลาคม สองพันห้าร้อยหกสิบ")
        self.assertIn("พอ-สอ สองพันห้าร้อยหกสิบ", r("พ.ศ. 2560"))

    def test_commas_percent_negative_phone(self):
        self.assertEqual(r("ปี 2019,2020"), "ปี สองพันสิบเก้า,สองพันยี่สิบ")
        self.assertEqual(r("1,200 บาท"), "หนึ่งพันสองร้อย บาท")
        self.assertIn("ห้าสิบ", r("ลด 50%"))
        self.assertIn("ลบ ห้า", r("-5 องศา"))
        self.assertIn("ศูนย์ สอง, หนึ่ง สอง สาม, สี่ ห้า หก เจ็ด", r("โทร 02-123-4567"))
        self.assertIn("หนึ่ง หก เจ็ด สอง", r("สายด่วน 1672"))

    def test_number_words_never_respelled(self):
        self.assertNotIn("ก้าว", r("2019 9 90"))

    def test_abbreviations(self):
        self.assertEqual(r("5 กม."), "ห้า กิโลเมตร")
        self.assertIn("จังหวัด", r("จ.เชียงใหม่"))
        self.assertIn("กรุงเทพ", r("กรุงเทพฯ"))
        self.assertNotIn("ม.ค.", r("15 ม.ค. 2567"))

    def test_no_numbers(self):
        self.assertEqual(r("ราคา 100", numbers=False), "ราคา 100")


class Round2(unittest.TestCase):
    """second review: abbreviations, numbers, markup"""
    def test_one_letter_abbrev_never_inside_words(self):
        for s_ in ("สู้ชีวิต...", "ปัญหาเศรษฐกิจ.", "เรื่องในอดีต.", "เปิดให้เข้าชม."):
            out = r(s_)
            for bad in ("ตำบล", "จังหวัด", "ชั่วโมง"):
                self.assertNotIn(bad, out, s_)
        self.assertIn("ส.ค.ส.", r("ส.ค.ส. พระราชทาน"))
        self.assertIn("จ.ส.ต.", r("จ.ส.ต. สมชาย"))
        self.assertIn("กรุงเทพ ", r("ในกรุงเทพฯ มีวัด"))
        self.assertIn("กรุงเทพมหานคร", r("จากกทม. ใช้เวลา"))
        self.assertIn("และอื่น ๆ", r("ฯลฯ"))

    def test_more_numbers(self):
        self.assertIn("ศูนย์ ห้า สาม, สอง สี่ แปด หก ศูนย์ สี่", r("ติดต่อ 053-248604"))
        self.assertIn("ศูนย์ แปด, หนึ่ง สอง สาม สี่, ห้า หก เจ็ด แปด", r("08-1234-5678"))
        self.assertIn("หนึ่ง หก เจ็ด สอง", r("สายด่วน ททท. 1672"))
        self.assertIn("สิบ ถึง ยี่สิบ เปอ", r("ลดราคา 10-20%"))
        self.assertIn("ลบ หนึ่ง จุด สอง ห้า", r("-1.25%"))
        self.assertIn("สิบสอง ตุลาคม", r("เมื่อ 12/10/2567."))
        self.assertIn("สอง ตุลาคม สองพันยี่สิบสี่", r("2024-10-02"))
        self.assertIn("สามร้อยห้าสิบ บาท", r("350.- บาท"))
        self.assertIn("หนึ่งพันสองร้อย บาท", r("฿1,200"))
        self.assertIn("เก้าสิบเก้า ทับ หนึ่ง", r("บ้านเลขที่ 99/1"))
        self.assertIn("บาท ต่อ คน", r("50 บาท/คน"))
        self.assertIn("หนึ่ง ต่อ ห้าหมื่น", r("มาตราส่วน 1:50,000"))
        self.assertEqual(r("ไทยชนะ 3-1"), "ไทยชนะ สาม ต่อ หนึ่ง")
        self.assertIn("เก้า นาฬิกา ถึง สิบสอง นาฬิกา", r("เวลา 09.00 น. - 12.00 น."))
        self.assertIn("จัน ถึง สุก", r("เปิดวันจันทร์-ศุกร์"))
        self.assertEqual(r("เปิด" + NBSP + "18.30" + NBSP + "น."), "เปิด" + NBSP + "สิบแปด นาฬิกา สามสิบ นาที")

    def test_markup_and_private_marks(self):
        self.assertEqual(r('<font color="#ffff00">พระอุโบสถ</font>'), '<font color="#ffff00">พระ-อุ-โบ-สด</font>')
        tag = "{" + BS + "an8}"
        self.assertTrue(r(tag + "อุโบสถ 2 หลัง").startswith(tag))
        out = r(chr(0xFDD0) + "ราคา 100 บาท " + chr(0xE000) + "อุโบสถ")
        self.assertNotIn(chr(0xFDD0), out)
        self.assertIn("หนึ่งร้อย", out)


class Teach(unittest.TestCase):
    def test_teach_wins_even_inside_longer_words(self):
        rr = T.Reader(my_file=os.path.join(tempfile.mkdtemp(), "my.txt"))
        rr.teach("ธรรมเนียม", "ทัม-มะ-เนียม")
        self.assertIn("ทัม-มะ-เนียม", rr.read("ค่าธรรมเนียม")[0])

    def test_teach_without_trailing_newline(self):
        p = write_bytes(os.path.join(tempfile.mkdtemp(), "my.txt"), "ประธาน = ประ-ทาน".encode("utf-8"))
        rr = T.Reader(my_file=p)
        rr.teach("ธรรมเนียม", "ทำ-เนียม")
        self.assertEqual(rr.read("ประธาน")[0], "ประ-ทาน")
        self.assertIn("ทำ-เนียม", rr.read("ธรรมเนียม")[0])

    def test_teach_strips_spaces_and_rejects_unmatchable(self):
        rr = T.Reader(my_file=os.path.join(tempfile.mkdtemp(), "my.txt"))
        self.assertEqual(rr.teach("วัด อรุณ", "วัด อะ รุน")[0], "วัดอรุณ")
        for bad in ("ต่างๆ", "COVID-19", "ร.9"):
            with self.assertRaises(ValueError):
                rr.teach(bad, "x")


class Pali(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(T.pali_reading("ธมฺม"), "ธัม-มะ")
        self.assertEqual(T.pali_reading("เมตฺตา"), "เม็ต-ตา")
        self.assertEqual(T.pali_reading("รูปํ"), "รู-ปัง")
        self.assertEqual(T.pali_reading("กเรยฺย"), "กะ-เรย-ยะ")
        for bad in ("กะปิง", "hello", "พฺรหฺม", "ชหวฺเห", "กฺ"):
            self.assertIsNone(T.pali_reading(bad), bad)

    def test_unlisted_pali_with_flag(self):
        rp = T.Reader(use_pali=True, my_file=os.path.join(tempfile.mkdtemp(), "m.txt"))
        self.assertEqual(rp.read("เมตฺตา")[0], "เม็ต-ตา")


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_srt_layout_kept(self):
        p = write_bytes(os.path.join(self.d, "a.srt"),
                        "1\r\n00:00:01,000 --> 00:00:03,000\r\nพระอุโบสถ\r\n\r\n".encode("utf-8"))
        dst, n = R.convert_file(p)
        self.assertEqual(read_bytes(dst).decode("utf-8"), "1\r\n00:00:01,000 --> 00:00:03,000\r\nพระ-อุ-โบ-สด\r\n\r\n")
        self.assertEqual(n, 1)

    def test_tsv_columns_indent_bom_kept(self):
        self.assertEqual(R.convert_line("L01\tอุโบสถ\t5\n"), "L01\tอุ-โบ-สด\t5\n")
        self.assertEqual(R.convert_line("1\t2\tพระอุโบสถ\n"), "1\t2\tพระ-อุ-โบ-สด\n")
        self.assertEqual(R.convert_line("    พระอุโบสถ  สวยงาม\n"), "    พระ-อุ-โบ-สด  สวยงาม\n")
        p = write_bytes(os.path.join(self.d, "b.txt"), (BOM + "อุโบสถ\n").encode("utf-8"))
        dst, _ = R.convert_file(p)
        self.assertTrue(read_bytes(dst).startswith(b"\xef\xbb\xbf"))

    def test_json_keys_paths_indent(self):
        src = json.dumps({"img": "ภาพ/วัด01.jpg", "vo": "อุโบสถ", "n": 3}, ensure_ascii=False, indent=2) + "\n"
        p = write_bytes(os.path.join(self.d, "x.json"), src.encode("utf-8"))
        dst, _ = R.convert_file(p)
        txt = read_bytes(dst).decode("utf-8")
        self.assertEqual(json.loads(txt), {"img": "ภาพ/วัด01.jpg", "vo": "อุ-โบ-สด", "n": 3})
        self.assertTrue(txt.endswith("\n") and '\n  "vo"' in txt)
        dst, _ = R.convert_file(p, keys={"img"})
        self.assertEqual(json.loads(read_bytes(dst).decode("utf-8"))["vo"], "อุโบสถ")

    def test_json_values_with_slash_or_dot_are_text(self):
        src = json.dumps({"price": "ราคา 35.50", "date": "วันที่ 12/10/2560", "img": "ภาพ/วัด01.jpg"}, ensure_ascii=False)
        p = write_bytes(os.path.join(self.d, "j.json"), src.encode("utf-8"))
        d = json.loads(read_bytes(R.convert_file(p)[0]).decode("utf-8"))
        self.assertIn("จุด", d["price"])
        self.assertIn("ตุลาคม", d["date"])
        self.assertEqual(d["img"], "ภาพ/วัด01.jpg")

    def test_jsonl_tsv_keys_json_crlf(self):
        p = write_bytes(os.path.join(self.d, "d.jsonl"), '{"id": 5, "th": "ราคา 35 บาท", "dur": 2.5}\n'.encode("utf-8"))
        d = json.loads(read_bytes(R.convert_file(p)[0]).decode("utf-8"))
        self.assertEqual((d["id"], d["dur"], d["th"]), (5, 2.5, "ราคา สามสิบห้า บาท"))
        p = write_bytes(os.path.join(self.d, "m.tsv"),
                        "shot\tsub\tvoice\timage\n1\tอุโบสถ 2 หลัง\tอุโบสถ 2 หลัง\tภาพ/อุโบสถ_01.png\n".encode("utf-8"))
        dst, _ = R.convert_file(p, keys={"voice"})
        row = read_bytes(dst).decode("utf-8").splitlines()[1].split("\t")
        self.assertEqual(row, ["1", "อุโบสถ 2 หลัง", "อุ-โบ-สด สอง หลัง", "ภาพ/อุโบสถ_01.png"])
        p = write_bytes(os.path.join(self.d, "c.json"), (BOM + '{\r\n    "th": "ราชการ"\r\n}\r\n').encode("utf-8"))
        dst, _ = R.convert_file(p)
        self.assertEqual(read_bytes(dst).decode("utf-8"), BOM + '{\r\n    "th": "ราด-ชะ-กาน"\r\n}\r\n')

    def test_no_numbers_in_files(self):
        p = write_bytes(os.path.join(self.d, "n.txt"), "ราคา 100 บาท อุโบสถ\n".encode("utf-8"))
        dst, _ = R.convert_file(p, numbers=False)
        self.assertEqual(read_bytes(dst).decode("utf-8"), "ราคา 100 บาท อุ-โบ-สด\n")

    def test_bad_file_does_not_stop_others(self):
        bad = write_bytes(os.path.join(self.d, "bad.txt"), "อุโบสถ".encode("cp874"))
        ok = write_bytes(os.path.join(self.d, "ok.txt"), "อุโบสถ\n".encode("utf-8"))
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = T.main([bad, ok, "--out", os.path.join(self.d, "new", "dir")])
        self.assertEqual(rc, 1)
        self.assertIn("not UTF-8", err.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.d, "new", "dir", "ok_อ่าน.txt")))

    def test_out_collision_gets_unique_name(self):
        os.makedirs(os.path.join(self.d, "a"))
        os.makedirs(os.path.join(self.d, "b"))
        p1 = write_bytes(os.path.join(self.d, "a", "x.txt"), "ราชการ\n".encode("utf-8"))
        p2 = write_bytes(os.path.join(self.d, "b", "x.txt"), "อุโบสถ\n".encode("utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            T.main([p1, p2, "--out", os.path.join(self.d, "o")])
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, "o"))), ["x_อ่าน(2).txt", "x_อ่าน.txt"])


class Cli(unittest.TestCase):
    def run_cli(self, args, stdin=None):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "thai_read.py")] + args, input=stdin,
                           capture_output=True, env=dict(os.environ, PYTHONUTF8="1"))
        return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")

    def test_json_output(self):
        rc, out, _ = self.run_cli(["--text", "อุโบสถ", "--json"])
        d = json.loads(out)
        self.assertEqual((rc, d["reading"], d["changes"][0]["word"]), (0, "อุ-โบ-สด", "อุโบสถ"))

    def test_stdin_bom(self):
        rc, out, _ = self.run_cli(["--stdin"], stdin=(BOM + "อุโบสถ\n").encode("utf-8"))
        self.assertEqual(out.strip(), "อุ-โบ-สด")

    def test_bad_inputs(self):
        self.assertEqual(self.run_cli(["--stdin"], stdin="อุโบสถ".encode("cp874"))[0], 1)
        self.assertEqual(self.run_cli(["--text", "x", "a.txt"])[0], 2)
        self.assertEqual(self.run_cli(["--teach", "ต่างๆ", "ต่าง-ต่าง"])[0], 1)
        self.assertEqual(self.run_cli([], stdin=b"")[0], 0)            # menu on EOF exits cleanly

    def test_missing_data_fails_loudly(self):
        with self.assertRaises(FileNotFoundError):
            T.Reader(data_dir=tempfile.mkdtemp())


class DataLint(unittest.TestCase):
    def test_readings_are_style_c(self):
        bad = []
        with open(os.path.join(ROOT, "data", "thai_readings.txt"), encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("#"):
                    continue
                w, rd = ln.rstrip("\n").split("\t")
                if (not re.fullmatch("[ก-๎]+(-[ก-๎]+)*", rd) or "์" in rd
                        or re.search("็[่-๋]|[่-๋]็", rd)):
                    bad.append((w, rd))
        self.assertEqual(bad[:10], [])


if __name__ == "__main__":
    unittest.main()
