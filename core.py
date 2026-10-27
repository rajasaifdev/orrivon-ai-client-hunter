
"""Orrivon Client Hunter core: respectful business research, no automatic outreach.

Uses Python standard library only. Public OSM servers are for occasional, light usage;
check the applicable usage terms before growing beyond a portfolio demo.
"""
from __future__ import annotations

import csv
import html
import ipaddress
import json
import re
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.robotparser import RobotFileParser

USER_AGENT = 'OrrivonClientHunter/0.1 (local portfolio research tool)'

# Two community-operated Overpass instances.
OVERPASS_ENDPOINTS = (
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
)

OSM_COPYRIGHT = '© OpenStreetMap contributors (ODbL) https://www.openstreetmap.org/copyright'

CITY = {
    'Dubai, UAE': (25.2048, 55.2708),
    'Abu Dhabi, UAE': (24.4539, 54.3773),
    'London, UK': (51.5074, -0.1278),
    'New York, USA': (40.7580, -73.9855),
    'Islamabad, Pakistan': (33.6844, 73.0479),
}

CATEGORIES = {
    'Salons & barbers': [
        ('shop', 'hairdresser'),
        ('shop', 'beauty')
    ],
    'Restaurants': [('amenity', 'restaurant')],
    'Cleaning & laundry': [
        ('office', 'cleaning'),
        ('craft', 'cleaning'),
        ('shop', 'laundry'),
        ('shop', 'dry_cleaning')
    ],
    'Real estate agents': [('office', 'estate_agent')],
    'Gyms': [('leisure', 'fitness_centre')],
    'Dental clinics': [
        ('healthcare', 'dentist'),
        ('amenity', 'dentist')
    ],
}

STAGES = (
    'New', 'Drafted', 'Approved', 'Contacted',
    'Replied', 'Qualified', 'Not interested'
)

DB_NAME = 'client_hunter.sqlite3'

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def normalize_url(raw: str) -> str:
    raw = (raw or '').strip()

    if not raw:
        return ''

    if not re.match(r'^https?://', raw, re.I):
        raw = 'https://' + raw

    p = urllib.parse.urlsplit(raw)

    if p.scheme not in {'https', 'http'} or not p.hostname or p.username or p.password:
        return ''

    host = p.hostname.lower()

    if host in {'localhost', 'localhost.localdomain'} or host.endswith('.local'):
        return ''

    try:
        if not ipaddress.ip_address(host).is_global:
            return ''
    except ValueError:
        if not re.fullmatch(r'[a-z0-9.-]+', host) or '.' not in host:
            return ''

    if p.port not in (None, 80, 443):
        return ''

    return urllib.parse.urlunsplit(
        (p.scheme, p.netloc, p.path or '/', p.query, '')
    )

def build_overpass(city: str, category: str, radius: int = 2400) -> str:
    if city not in CITY or category not in CATEGORIES:
        raise ValueError('Select a supported city and category')

    lat, lon = CITY[city]
    radius = max(1000, min(radius, 7000))

    parts = [
        f'  nwr(around:{radius},{lat},{lon})["name"]["{key}"="{value}"];'
        for key, value in CATEGORIES[category]
    ]

    return (
        '[out:json][timeout:16];\n(\n'
        + '\n'.join(parts)
        + '\n);\nout center 70;'
    )

def discover(city: str, category: str) -> list[dict]:
    """Search public map listings with one fallback."""

    query = build_overpass(city, category)
    request_body = urllib.parse.urlencode(
        {'data': query}
    ).encode('utf-8')

    payload = None
    errors = []

    for n, endpoint in enumerate(OVERPASS_ENDPOINTS):
        if n:
            time.sleep(2)

        req = urllib.request.Request(
            endpoint,
            data=request_body,
            headers={
                'User-Agent': USER_AGENT,
                'Accept': 'application/json'
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=19) as response:
                body = response.read(2_000_001)

            if len(body) > 2_000_000:
                raise ValueError('Unexpectedly large response')

            result = json.loads(body)

            if not isinstance(result, dict) or not isinstance(result.get('elements'), list):
                raise ValueError('Unexpected map server response')

            payload = result
            break

        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            errors.append(type(exc).__name__)

    if payload is None:
        raise RuntimeError(
            'Public map search servers did not respond ('
            + ', '.join(errors) + '). '
            'Your app and saved leads are safe. '
            'Use Add manually with verified business listings, '
            'or try again later. Do not spam public APIs.'
        )

    found = []

    for obj in payload.get('elements', []):
        tags = obj.get('tags') or {}

        name = (
            tags.get('name:en')
            or tags.get('name')
            or ''
        ).strip()

        if not name:
            continue

        website = normalize_url(
            tags.get('website')
            or tags.get('contact:website')
            or tags.get('url')
            or ''
        )

        mail = (
            tags.get('contact:email')
            or tags.get('email')
            or ''
        ).strip()

        if not re.fullmatch(
            r'[^\s@;,]+@[^\s@;,]+\.[^\s@;,]+',
            mail
        ):
            mail = ''

        kind = obj.get('type', 'node')
        oid = obj.get('id')

        if not oid:
            continue

        found.append({
            'id': f'osm:{kind}:{oid}',
            'name': name[:160],
            'city': city,
            'category': category,
            'website': website[:400],
            'email': mail[:160],
            'source': 'OpenStreetMap',
            'source_url': f'https://www.openstreetmap.org/{kind}/{oid}',
        })

    return found

class PageAnalyzer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)

        self.title = ''
        self.meta_description = ''
        self.viewport = False
        self.has_contact_link = False
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)

        if tag.lower() == 'title':
            self._in_title = True

        if tag.lower() == 'meta':
            if d.get('name', '').lower() == 'description':
                self.meta_description = (
                    d.get('content') or ''
                ).strip()[:250]

            if d.get('name', '').lower() == 'viewport':
                self.viewport = True

        if tag.lower() == 'a':
            href = (d.get('href') or '').strip().lower()
            if any(term in href for term in (
                'contact', 'appointment', 'booking', 'book-now',
                'mailto:', 'wa.me/', 'api.whatsapp.com',
                'whatsapp.com/send', 'web.whatsapp.com/send'
            )):
                self.has_contact_link = True

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data

def _safe_host(url: str) -> bool:
    """Reject local and private website addresses."""

    p = urllib.parse.urlsplit(url)

    if not normalize_url(url):
        return False

    try:
        ips = socket.getaddrinfo(
            p.hostname,
            p.port or (443 if p.scheme == 'https' else 80),
            type=socket.SOCK_STREAM
        )
    except OSError:
        return False

    return bool(ips) and all(
        ipaddress.ip_address(info[4][0]).is_global
        for info in ips
    )

class ValidatingRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_host(newurl):
            raise ValueError('Redirect blocked to an unsafe address')

        return super().redirect_request(
            req, fp, code, msg, headers, newurl
        )

def inspect_website(website: str) -> dict:
    url = normalize_url(website)

    if not url:
        return {
            'checked': False,
            'issues': ['No valid website listed'],
            'summary': 'No website listed in source',
            'score': 65
        }

    if not _safe_host(url):
        return {
            'checked': False,
            'issues': [],
            'summary': 'Website URL blocked or cannot resolve',
            'score': 35
        }

    opener = urllib.request.build_opener(ValidatingRedirect())

    parts = urllib.parse.urlsplit(url)
    robot_url = f'{parts.scheme}://{parts.netloc}/robots.txt'

    try:
        with opener.open(
            urllib.request.Request(
                robot_url,
                headers={'User-Agent': USER_AGENT}
            ),
            timeout=7
        ) as r:
            content = r.read(150_000).decode('utf-8', 'replace')

            parser = RobotFileParser()
            parser.parse(content.splitlines())

            if not parser.can_fetch(USER_AGENT, url):
                return {
                    'checked': False,
                    'issues': [],
                    'summary': 'Website audit blocked by robots.txt',
                    'score': 35
                }

    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {
                'checked': False,
                'issues': [],
                'summary': f'robots.txt denied access ({exc.code})',
                'score': 35
            }

        if exc.code != 404:
            return {
                'checked': False,
                'issues': [],
                'summary': f'robots.txt unavailable ({exc.code})',
                'score': 35
            }

    except Exception as exc:
        return {
            'checked': False,
            'issues': [],
            'summary': f'robots.txt check failed: {type(exc).__name__}',
            'score': 35
        }

    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': USER_AGENT,
                'Accept': 'text/html'
            }
        )

        with opener.open(req, timeout=12) as response:
            final = response.geturl()

            if not _safe_host(final):
                raise ValueError('Website redirected to unsafe address')

            content_type = response.headers.get('Content-Type', '')

            if 'text/html' not in content_type.lower():
                return {
                    'checked': False,
                    'issues': [],
                    'summary': 'Website did not return HTML',
                    'score': 35
                }

            text = response.read(400_000).decode(
                'utf-8', 'replace'
            )

        parser = PageAnalyzer()
        parser.feed(text)

        issues = []

        if not parser.title.strip():
            issues.append('Homepage title not detected')

        if not parser.meta_description:
            issues.append('Meta description not detected')

        if not parser.viewport:
            issues.append('Mobile viewport tag not detected')

        if final.startswith('http://'):
            issues.append('Homepage did not use HTTPS')

        if not parser.has_contact_link:
            issues.append('Contact/booking link not detected in HTML')

        score = min(95, 35 + 12 * len(issues))

        return {
            'checked': True,
            'issues': issues,
            'summary': 'Basic homepage check complete; manual review required',
            'score': score,
            'title': parser.title.strip()[:160],
        }

    except Exception as exc:
        return {
            'checked': False,
            'issues': [],
            'summary': (
                'Website could not be inspected: '
                f'{type(exc).__name__}'
            ),
            'score': 35
        }

def outreach_draft(p: dict) -> str:
    name = p['name']
    website = p.get('website') or ''
    audit = p.get('audit') or {}
    issues = audit.get('issues') or []

    proof = ''

    if audit.get('checked') and issues:
        candidates = [
            s for s in issues
            if s in {
                'Meta description not detected',
                'Mobile viewport tag not detected',
                'Contact/booking link not detected in HTML'
            }
        ]

        if candidates:
            proof = (
                'I noticed a possible website improvement area '
                'during a quick public-page review: '
                f'{candidates[0].lower()}. '
                'This would need a closer check. '
            )

    elif not website:
        proof = (
            "I couldn't find a website link in the public "
            "business listing I reviewed. "
        )

    else:
        proof = (
            'I came across your business while researching '
            'local service providers. '
        )

    return (
        f'Subject: Quick website idea for {name}\n\n'
        f'Hi {name} team,\n\n'
        f'{proof}'
        'I build simple websites and lead-management tools that '
        'help local businesses turn enquiries into bookings. '
        "If it's relevant, I can share a short, no-obligation "
        'example tailored to your business.\n\n'
        'Would it be useful if I sent over a quick demo?\n\n'
        'Thanks,\nSaif | Orrivon Digital\n'
    )

# ========================================
# UPDATED AI OUTREACH GENERATOR
# ========================================

def ollama_draft(p: dict, model='qwen2.5:0.5b') -> str:
    """Generate factual outreach using local AI to choose a service benefit."""

    name = str(p.get('name') or '').strip()
    city = str(p.get('city') or '').split(',')[0].strip()
    category = str(p.get('category') or 'local businesses').strip()

    if not name:
        raise ValueError('Business name is required')

    # Small AI model chooses one relevant benefit.
    prompt = (
        'Select exactly ONE of these words for the most relevant '
        'service to offer this business: bookings, inquiries, followups. '
        'Do not write an email or explanation. '
        f'Business category: {category}. Answer with one word only.'
    )

    req = urllib.request.Request(
        'http://127.0.0.1:11434/api/generate',
        data=json.dumps({
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': 0.0,
                'num_predict': 12
            }
        }).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    with urllib.request.urlopen(req, timeout=90) as response:
        result = json.load(response)

    answer = str(result.get('response') or '').strip().lower()
    words = re.findall(r'[a-z]+', answer)

    selected = next(
        (
            w for w in words
            if w in ('bookings', 'inquiries', 'followups')
        ),
        ''
    )

    if not selected:
        selected = (
            'bookings'
            if category == 'Salons & barbers'
            else 'inquiries'
        )

    benefits = {
        'bookings': 'organize customer bookings',
        'inquiries': 'manage customer inquiries',
        'followups': 'track customer follow-ups'
    }

    benefit = benefits[selected]

    # Final email is assembled from verified business details.
    # AI cannot invent names, CEO titles or fake achievements.
    return (
        f'Subject: Quick idea for {name}\n\n'
        f'Hi {name} Team,\n\n'
        f'I came across your business while researching '
        f'{category.lower()} in {city}.\n\n'
        f"I'm Saif from Orrivon Digital. I build websites "
        f'and simple CRM systems that help businesses {benefit}.\n\n'
        'I recently built a website-to-CRM demo and would '
        'be happy to show how a similar setup could work '
        'for your business.\n\n'
        'Would a quick 60-second demo be useful?\n\n'
        'Best regards,\n'
        'Saif\n'
        'Orrivon Digital'
    )

def csv_safe(value) -> str:
    s = str(value or '')

    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s

    return s

class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False
        )

        self.lock = threading.Lock()

        self.conn.execute(
            '''CREATE TABLE IF NOT EXISTS prospects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT,
                category TEXT,
                website TEXT,
                email TEXT,
                source TEXT,
                source_url TEXT,
                audit_json TEXT DEFAULT '{}',
                score INTEGER DEFAULT 35,
                stage TEXT DEFAULT 'New',
                draft TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )'''
        )

        self.conn.commit()

    def upsert(self, rows: list[dict]) -> int:
        count = 0

        with self.lock:
            for p in rows:
                old = self.conn.execute(
                    'SELECT id FROM prospects WHERE id=?',
                    (p['id'],)
                ).fetchone()

                if old:
                    continue

                self.conn.execute(
                    '''INSERT INTO prospects
                    (id,name,city,category,website,email,
                     source,source_url,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (
                        p['id'],
                        p['name'],
                        p['city'],
                        p['category'],
                        p.get('website', ''),
                        p.get('email', ''),
                        p.get('source', ''),
                        p.get('source_url', ''),
                        utc_now(),
                        utc_now()
                    )
                )

                count += 1

            self.conn.commit()

        return count

    def all(self, city=None, category=None) -> list[dict]:
        with self.lock:
            self.conn.row_factory = sqlite3.Row

            rows = self.conn.execute(
                '''SELECT * FROM prospects
                ORDER BY score DESC, created_at DESC'''
            ).fetchall()

        out = []

        for r in rows:
            d = dict(r)
            d['audit'] = json.loads(d.pop('audit_json') or '{}')

            if city and d['city'] != city:
                continue

            if category and d['category'] != category:
                continue

            out.append(d)

        return out

    def one(self, item_id):
        return next(
            (r for r in self.all() if r['id'] == item_id),
            None
        )

    def update(self, item_id, **values):
        allowed = {
            'audit_json', 'score', 'stage',
            'draft', 'email', 'website'
        }

        data = {
            k: v for k, v in values.items()
            if k in allowed
        }

        if not data:
            return

        if 'stage' in data and data['stage'] not in STAGES:
            raise ValueError('Invalid outreach stage')

        data['updated_at'] = utc_now()

        sql = ', '.join(
            f'{name}=?' for name in data
        )

        with self.lock:
            self.conn.execute(
                f'UPDATE prospects SET {sql} WHERE id=?',
                (*data.values(), item_id)
            )

            self.conn.commit()

    def export(self, path: Path):
        rows = self.all()

        columns = (
            'name', 'city', 'category', 'website',
            'email', 'score', 'stage',
            'source', 'source_url', 'draft'
        )

        with Path(path).open(
            'w',
            encoding='utf-8-sig',
            newline=''
        ) as fp:
            writer = csv.writer(fp)
            writer.writerow(columns)

            for p in rows:
                writer.writerow([
                    csv_safe(p.get(col))
                    for col in columns
                ])

        return len(rows)
