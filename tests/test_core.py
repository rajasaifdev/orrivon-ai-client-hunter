
import tempfile
import unittest
from pathlib import Path

from core import (
    CITY,
    CATEGORIES,
    Store,
    build_overpass,
    csv_safe,
    inspect_website,
    normalize_url,
    outreach_draft,
    PageAnalyzer
)


class Tests(unittest.TestCase):

    def test_cities_and_categories(self):
        q = build_overpass('Dubai, UAE', 'Salons & barbers')
        self.assertIn('nwr(around:', q)
        self.assertIn('out center 70;', q)
        self.assertIn('hairdresser', q)

    def test_reject_private_websites(self):
        for url in (
            'http://localhost:1000',
            'http://127.0.0.1',
            'file:///etc/passwd',
            'http://192.168.0.1',
            'http://admin:pw@example.com'
        ):
            self.assertEqual(normalize_url(url), '')

        self.assertEqual(
            normalize_url('example.com'),
            'https://example.com/'
        )

    def test_html_analysis(self):
        p = PageAnalyzer()

        p.feed(
            '<html><head><title>Test</title>'
            '<meta name="viewport" content="width=device-width">'
            '</head><body>'
            '<a href="/contact">Contact</a>'
            '</body></html>'
        )

        self.assertEqual(p.title, 'Test')
        self.assertTrue(p.viewport)
        self.assertTrue(p.has_contact_link)
        self.assertFalse(p.meta_description)

    def test_missing_website(self):
        d = inspect_website('')

        self.assertFalse(d['checked'])
        self.assertIn(
            'No valid website listed',
            d['issues']
        )

    def test_db_save_update_export(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Store(Path(folder) / 'test.sqlite3')

            try:
                sample = {
                    'id': 'manual:1',
                    'name': 'Fictional Co',
                    'city': 'Dubai, UAE',
                    'category': 'Salons & barbers',
                    'website': '',
                    'email': '',
                    'source': 'Demo',
                    'source_url': ''
                }

                self.assertEqual(db.upsert([sample]), 1)
                self.assertEqual(db.upsert([sample]), 0)

                db.update(
                    sample['id'],
                    stage='Approved',
                    draft='Draft text'
                )

                self.assertEqual(
                    db.one(sample['id'])['stage'],
                    'Approved'
                )

                fp = Path(folder) / 'out.csv'

                self.assertEqual(db.export(fp), 1)

                self.assertIn(
                    'Fictional Co',
                    fp.read_text(encoding='utf-8-sig')
                )

            finally:
                # FIX: Close database before Windows
                # deletes the temporary test folder.
                db.conn.close()

    def test_factual_draft(self):
        draft = outreach_draft({
            'name': 'Fictional Co',
            'website': 'https://example.com/',
            'audit': {
                'checked': False,
                'issues': [
                    'Mobile viewport tag not detected'
                ]
            }
        })

        self.assertIn('Fictional Co', draft)

        self.assertNotIn(
            'mobile viewport',
            draft.lower()
        )

    def test_csv_injection(self):
        self.assertEqual(
            csv_safe('=HYPERLINK("bad")')[0],
            "'"
        )


if __name__ == '__main__':
    unittest.main()
