import unittest

from catalog.parse import parse_heading, parse_course_list, parse_course_page
from catalog.scrape import merge_courses
from catalog.sources import SOURCE_BY_SLUG

HTML = '''
<main><div class="view-content">
<div class="views-row">
<h3><a href="/course/csc207h1">CSC207H1 - Software Design</a></h3>
<p>Build software with good architecture.</p>
<p>Prerequisite: CSC148H1</p>
<p>Exclusion: CSC270H1</p>
</div>
<div class="views-row">
<h3>MAT237Y1 - Multivariable Calculus</h3>
<p>Derivatives and integrals in several variables.</p>
</div>
</div></main>'''


class TestCatalogParsing(unittest.TestCase):
    def test_heading_formats(self):
        self.assertEqual(parse_heading("CSC207H1 - Software Design"), ("CSC207H1", "Software Design"))
        self.assertEqual(parse_heading("Anesthesia [ANS310Y]"), ("ANS310Y", "Anesthesia"))
        self.assertIsNone(parse_heading("Courses"))

    def test_html_course_extraction(self):
        courses = parse_course_list(HTML, SOURCE_BY_SLUG["artsci"])
        self.assertEqual(len(courses), 2)
        c = next(x for x in courses if x["code"] == "CSC207H1")
        self.assertEqual(c["title"], "Software Design")
        self.assertEqual(c["description"], "Build software with good architecture.")
        self.assertEqual(c["prerequisites"], "CSC148H1")
        self.assertEqual(c["exclusions"], "CSC270H1")
        self.assertEqual(c["source_url"], "https://artsci.calendar.utoronto.ca/course/csc207h1")
        self.assertIsNone(c["credits"])

    def test_md_course_format(self):
        html = '<main><div class="view-content"><div class="views-row"><h3>Anesthesia [ANS310Y]</h3><p>Clinical rotation.</p></div></div></main>'
        course, = parse_course_list(html, SOURCE_BY_SLUG["medicine"])
        self.assertEqual((course["code"], course["title"]), ("ANS310Y", "Anesthesia"))

    def test_flat_printer_friendly_html(self):
        html = ('<main><div class="view-content"><h3>MAT244H1 - Differential Equations</h3>'
                '<p>Ordinary differential equations.</p><p>Prerequisite: MAT237Y1</p>'
                '<h3>CSC207H1 - Software Design</h3><p>Clean architecture.</p></div></main>')
        courses = parse_course_list(html, SOURCE_BY_SLUG["artsci"])
        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]["description"], "Ordinary differential equations.")
        self.assertEqual(courses[0]["prerequisites"], "MAT237Y1")
        self.assertEqual(courses[1]["description"], "Clean architecture.")

    def test_credit_override(self):
        html = '<main><div class="view-content"><div class="views-row"><h3>EMU254H1 - Instrumental Class</h3><p>Fixed Credit: 0.17</p><p>Study.</p></div></div></main>'
        course, = parse_course_list(html, SOURCE_BY_SLUG["music"])
        self.assertEqual(course["credits"], 0.17)

    def test_nested_drupal_fields_and_link_boundaries(self):
        html = '''
        <div class="view-content"><div class="views-row"><h3>ABC200H1 - Field Study</h3>
        <div class="views-row">
          <span class="views-field views-field-field-hours">
            <strong class="views-label">Hours: </strong><span class="field-content">24L</span></span>
          <div class="views-field views-field-body"><p>Read <a>original studies</a>.</p>
            <p>Discuss results.</p></div>
          <span class="views-field views-field-field-prerequisite"><span class="field-content">
            <strong>Prerequisite:</strong> 65% in <a>ABC100H1</a> or instructor permission.</span></span>
          <span class="views-field views-field-field-exclusion"><strong>Exclusion:</strong>
            <a>ABC201H1</a>, <a>ABC202H1</a></span>
          <div class="views-field views-field-field-credit"><strong>Credit Value:</strong> 0.50</div>
          <span class="views-field views-field-field-program-tags"><strong>Program Tags:</strong>
            <ul><li>Year 1</li><li>Year 2</li></ul></span>
        </div></div></div><a rel="next" href="?page=3">Next</a>'''
        url = SOURCE_BY_SLUG["engineering"].url + "?page=2"
        courses, has_next = parse_course_page(html, SOURCE_BY_SLUG["engineering"], url)
        course, = courses
        self.assertTrue(has_next)
        self.assertEqual(course["description"], "Read original studies.\nDiscuss results.")
        self.assertEqual(course["prerequisites"], "65% in ABC100H1 or instructor permission.")
        self.assertEqual(course["exclusions"], "ABC201H1, ABC202H1")
        self.assertEqual(course["credits"], 0.5)
        self.assertEqual(course["source_url"], url)
        self.assertEqual(course["source_fields"]["program_tags"], "Year 1 Year 2")

    def test_mixed_layout_and_variable_credits(self):
        html = '''<div class="views-row"><h3>ABC300H1 - Practicum</h3>
            <p>Individual study.</p>
            <div class="views-field views-field-field-variable-credit">
            <strong>Variable Credit:</strong> 0.5 to 1</div></div>'''
        course, = parse_course_list(html, SOURCE_BY_SLUG["music"])
        self.assertEqual(course["description"], "Individual study.")
        self.assertEqual(course["source_fields"]["variable_credit"], "0.5 to 1")
        self.assertIsNone(course["credits"])

    def test_deduplicate_multiple_faculties(self):
        original = parse_course_list(HTML, SOURCE_BY_SLUG["artsci"])[0]
        incoming = dict(original, faculties=["engineering"], source_url="https://engineering.calendar.utoronto.ca/search-courses")
        combined = merge_courses(original, incoming)
        self.assertEqual(combined["faculties"], ["artsci", "engineering"])
        self.assertEqual(len(combined["source_urls"]), 2)


if __name__ == "__main__":
    unittest.main()
