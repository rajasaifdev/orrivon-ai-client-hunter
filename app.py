
"""Orrivon AI Client Hunter — Desktop Application."""
from __future__ import annotations

import csv
import os
import ctypes
import sys
import hashlib
import json
import re
import urllib.parse
import queue
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import (
    CATEGORIES, CITY, OSM_COPYRIGHT, STAGES, Store,
    inspect_website, normalize_url, ollama_draft, outreach_draft,
)

BG = '#0D1925'
PANEL = '#162A3A'
CARD = '#244054'
TEXT = '#F0F6F7'
MUTED = '#D8E5EC'
ACCENT = '#24C2A7'
OUTLINE = '#476071'

# Free API setup. Never put an API key directly into source code.
KEY_FILE = Path.home() / '.orrivon' / 'geoapify_key.txt'
GEOAPIFY_URL = 'https://api.geoapify.com/v2/places'

GEOAPIFY_CATEGORIES = {
    'Salons & barbers': 'service.beauty.hairdresser,service.beauty.spa',
    'Restaurants': 'catering.restaurant',
    'Cleaning & laundry': 'service.cleaning',
    'Real estate agents': 'service.estate_agent',
    'Gyms': 'sport.fitness.fitness_centre,sport.fitness.gym',
    'Dental clinics': 'healthcare.dentist',
}


def geoapify_discover(city: str, category: str, api_key: str) -> list[dict]:
    """Discover up to 20 real mapped business places."""
    if city not in CITY or category not in GEOAPIFY_CATEGORIES:
        raise ValueError('Unsupported city or industry')

    if not api_key or len(api_key) < 10:
        raise ValueError('A Geoapify API key is required')

    lat, lon = CITY[city]

    payload = {
        'categories': GEOAPIFY_CATEGORIES[category].split(','),
        'filter': {
            'type': 'circle',
            'lon': lon,
            'lat': lat,
            'radius': 3500,
        },
        'bias': {
            'type': 'proximity',
            'lon': lon,
            'lat': lat
        },
        'limit': 20,
    }

    request = urllib.request.Request(
        GEOAPIFY_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-api-key': api_key,
            'User-Agent': 'OrrivonClientHunter/0.2'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw_response = response.read(2_000_001)

    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            raise RuntimeError(
                'Geoapify API key rejected. Check the key.'
            ) from None

        if err.code == 429:
            raise RuntimeError(
                'Geoapify free quota or rate limit reached.'
            ) from None

        raise RuntimeError(
            f'Places API returned HTTP {err.code}.'
        ) from None

    except (urllib.error.URLError, OSError, TimeoutError):
        raise RuntimeError(
            'Geoapify network request failed. '
            'Check internet and retry later.'
        ) from None

    if len(raw_response) > 2_000_000:
        raise RuntimeError('Places API result was too large')

    try:
        data = json.loads(raw_response)
    except ValueError:
        raise RuntimeError(
            'Places API returned invalid JSON'
        ) from None

    if not isinstance(data, dict) or not isinstance(
        data.get('features'), list
    ):
        raise RuntimeError(
            'Unexpected Places API response format'
        )

    results = []

    for item in data['features'][:20]:
        if not isinstance(item, dict):
            continue

        props = item.get('properties') or {}
        raw = (props.get('datasource') or {}).get('raw') or {}

        if not isinstance(raw, dict):
            raw = {}

        name = str(
            props.get('name') or raw.get('name') or ''
        ).strip()

        if not name:
            continue

        website = normalize_url(
            str(
                props.get('website')
                or raw.get('website')
                or raw.get('contact:website')
                or ''
            )
        )

        email = str(
            props.get('email')
            or raw.get('contact:email')
            or raw.get('email')
            or ''
        ).strip()

        if not re.fullmatch(
            r'[^\s@;,]+@[^\s@;,]+\.[^\s@;,]+', email
        ):
            email = ''

        place_id = str(
            props.get('place_id') or ''
        ).strip()

        if not place_id:
            coords = (
                (item.get('geometry') or {}).get('coordinates') or []
            )
            place_id = hashlib.sha256(
                f'{name}|{city}|{coords}'.encode('utf-8')
            ).hexdigest()[:24]

        osm_type = str(raw.get('osm_type') or '').lower()
        osm_id = str(raw.get('osm_id') or '')

        if osm_type in ('n', 'node'):
            osm_type = 'node'
        elif osm_type in ('w', 'way'):
            osm_type = 'way'
        elif osm_type in ('r', 'relation'):
            osm_type = 'relation'

        source_url = (
            f'https://www.openstreetmap.org/{osm_type}/{osm_id}'
            if osm_type in ('node', 'way', 'relation')
            and osm_id.isdecimal()
            else ''
        )

        results.append({
            'id': 'geoapify:' + place_id[:120],
            'name': name[:160],
            'city': city,
            'category': category,
            'website': website[:400],
            'email': email[:160],
            'source': 'Geoapify / OpenStreetMap',
            'source_url': source_url,
        })

    return results


def enable_windows_dpi_awareness():
    """Improve Tkinter sharpness on Windows."""
    if sys.platform != 'win32':
        return

    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)
        ):
            return
    except (AttributeError, OSError, ValueError):
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError, ValueError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError, ValueError):
            pass


def short_website_display(raw):
    if not raw:
        return 'Not listed'

    try:
        parsed = urllib.parse.urlsplit(raw)
        hostname = (
            parsed.hostname or ''
        ).removeprefix('www.')
        return hostname or raw[:65]
    except ValueError:
        return raw[:65]


class ClientHunter:
    def __init__(self, root):
        self.root = root

        root.title(
            'Orrivon • AI Client Hunter | Portfolio MVP'
        )
        root.geometry(
            f'{min(1450, root.winfo_screenwidth()-40)}x'
            f'{min(850, root.winfo_screenheight()-80)}'
        )
        root.minsize(1000, 650)
        root.configure(bg=BG)

        self.store = Store(
            Path(__file__).parent
            / 'data'
            / 'client_hunter.sqlite3'
        )

        self.queue = queue.Queue()
        self.selected_id = None
        self.busy = False
        self.last_search_at = 0.0
        self.last_searches = set()

        self._build()
        self._refresh()
        self.root.after(125, self._poll)

    def _get_api_key(self):
        key = os.environ.get(
            'GEOAPIFY_API_KEY', ''
        ).strip()

        if not key and KEY_FILE.exists():
            try:
                key = KEY_FILE.read_text(
                    encoding='utf-8'
                ).strip()
            except OSError:
                pass

        if key:
            return key

        messagebox.showinfo(
            'Free Geoapify API key',
            'Automatic search needs a Geoapify API key.\n'
            'Free registration, no credit card required.\n'
            'Visit myprojects.geoapify.com and copy your key.\n'
            'The key will be saved outside your GitHub project.'
        )

        key = simpledialog.askstring(
            'Geoapify API key',
            'Paste your API key (do not send it in chat):',
            show='*',
            parent=self.root
        )

        if not key or len(key.strip()) < 10:
            return ''

        key = key.strip()

        KEY_FILE.parent.mkdir(
            parents=True, exist_ok=True
        )

        KEY_FILE.write_text(
            key, encoding='utf-8'
        )

        return key

    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use('clam')

        s.configure(
            'Treeview',
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            bordercolor=OUTLINE,
            rowheight=40,
            font=('Segoe UI', 11)
        )

        s.map(
            'Treeview',
            background=[('selected', '#1C736E')],
            foreground=[('selected', 'white')]
        )

        s.configure(
            'Treeview.Heading',
            background=CARD,
            foreground=TEXT,
            relief='flat',
            font=('Segoe UI', 11, 'bold')
        )

        s.map(
            'Treeview.Heading',
            background=[('active', '#26475B')]
        )

        s.configure(
            'TCombobox',
            padding=6,
            font=('Segoe UI', 11)
        )

    def _button(
        self, parent, text, command,
        primary=False, width=None
    ):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=('Segoe UI', 11, 'bold'),
            bg=ACCENT if primary else CARD,
            fg=BG if primary else TEXT,
            activebackground='#18a58f',
            activeforeground=BG if primary else TEXT,
            relief='flat',
            bd=0,
            padx=12,
            pady=9,
            cursor='hand2',
            width=width
        )

    def _label(
        self, parent, text, size=10,
        color=TEXT, bold=False, **kw
    ):
        font_size = (
            11 if size == 10
            else 10 if size == 9
            else size
        )

        return tk.Label(
            parent,
            text=text,
            font=(
                'Segoe UI',
                font_size,
                'bold' if bold else 'normal'
            ),
            bg=parent['bg'],
            fg=color,
            **kw
        )

    def _build(self):
        self._style()

        hero = tk.Frame(
            self.root, bg=BG,
            padx=25, pady=15
        )
        hero.pack(fill='x')

        self._label(
            hero,
            'ORRIVON   /   AI CLIENT HUNTER',
            19, TEXT, True
        ).pack(side='left')

        self._label(
            hero,
            'LOCAL MVP  •  NO AUTO-SEND',
            9, ACCENT, True
        ).pack(side='right')

        sub = tk.Frame(
            self.root, bg=BG, padx=25
        )
        sub.pack(fill='x')

        self._label(
            sub,
            'Find businesses → inspect public homepage → '
            'prepare tailored outreach → approve manually',
            10, MUTED
        ).pack(anchor='w')

        toolbar = tk.Frame(
            self.root,
            bg=PANEL,
            padx=15,
            pady=12
        )
        toolbar.pack(
            fill='x',
            padx=25,
            pady=(17, 10)
        )

        self._label(
            toolbar, 'City', 10, MUTED
        ).pack(side='left', padx=(0, 5))

        self.city = tk.StringVar(
            value='Dubai, UAE'
        )

        ttk.Combobox(
            toolbar,
            textvariable=self.city,
            state='readonly',
            values=list(CITY),
            width=19
        ).pack(side='left', padx=(0, 14))

        self._label(
            toolbar, 'Industry', 10, MUTED
        ).pack(side='left', padx=(0, 5))

        self.category = tk.StringVar(
            value='Salons & barbers'
        )

        ttk.Combobox(
            toolbar,
            textvariable=self.category,
            state='readonly',
            values=list(CATEGORIES),
            width=19
        ).pack(side='left', padx=(0, 14))

        self._button(
            toolbar,
            'Find businesses',
            self._search,
            True
        ).pack(side='left', padx=(0, 8))

        self._button(
            toolbar,
            'Research web',
            self._research_web
        ).pack(side='left', padx=(0, 8))

        self._button(
            toolbar,
            'Import CSV',
            self._import_csv
        ).pack(side='left', padx=(0, 8))

        self._button(
            toolbar,
            'Add manually',
            self._add_manual
        ).pack(side='left', padx=(0, 8))

        self._button(
            toolbar,
            'Export CSV',
            self._export
        ).pack(side='right')

        stats = tk.Frame(
            self.root,
            bg=BG,
            padx=25,
            pady=2
        )
        stats.pack(fill='x')

        self.stats = self._label(
            stats, '', 10, ACCENT, True
        )
        self.stats.pack(side='left')

        self.status = self._label(
            stats,
            'Ready. Search one city/category at a time.',
            9, MUTED
        )
        self.status.pack(side='right')

        mid = tk.PanedWindow(
            self.root,
            orient='horizontal',
            sashwidth=7,
            bg=BG,
            bd=0,
            relief='flat'
        )
        mid.pack(
            fill='both',
            expand=True,
            padx=25,
            pady=(10, 8)
        )

        left = tk.Frame(
            mid, bg=PANEL, padx=12, pady=11
        )
        right = tk.Frame(
            mid, bg=PANEL, padx=14, pady=10
        )

        mid.add(
            left,
            minsize=510,
            stretch='always'
        )
        mid.add(
            right,
            minsize=375,
            stretch='always'
        )

        heading = tk.Frame(
            left, bg=PANEL
        )
        heading.pack(
            fill='x',
            pady=(0, 10)
        )

        self._label(
            heading,
            'Prospect Pipeline',
            14, TEXT, True
        ).pack(side='left')

        self._button(
            heading,
            'Refresh',
            self._refresh
        ).pack(side='right')

        cols = (
            'name', 'city',
            'website', 'score', 'stage'
        )

        self.table = ttk.Treeview(
            left,
            columns=cols,
            show='headings',
            selectmode='browse'
        )

        for key, label, width in (
            ('name', 'Business', 180),
            ('city', 'Market', 120),
            ('website', 'Website?', 75),
            ('score', 'Score', 55),
            ('stage', 'Stage', 90)
        ):
            self.table.heading(key, text=label)
            self.table.column(
                key,
                width=width,
                minwidth=50,
                stretch=(key == 'name')
            )

        scroll = ttk.Scrollbar(
            left,
            orient='vertical',
            command=self.table.yview
        )
        self.table.configure(
            yscrollcommand=scroll.set
        )
        scroll.pack(
            side='right',
            fill='y'
        )
        self.table.pack(
            fill='both',
            expand=True
        )

        self.table.tag_configure(
            'odd',
            background='#203749',
            foreground=TEXT
        )
        self.table.tag_configure(
            'even',
            background=PANEL,
            foreground=TEXT
        )

        self.table.bind(
            '<<TreeviewSelect>>',
            self._choose
        )

        self._label(
            left,
            'Scores are rough research priorities, '
            'not proof of business problems.',
            9, MUTED
        ).pack(anchor='w', pady=(10, 0))

        self._label(
            right,
            'Lead Detail & Outreach',
            14, TEXT, True
        ).pack(anchor='w', pady=(1, 10))

        self.lead_label = self._label(
            right,
            'Choose a business from the list',
            12,
            ACCENT,
            True,
            wraplength=460,
            justify='left'
        )
        self.lead_label.pack(
            anchor='w',
            pady=4
        )

        self.details = self._label(
            right,
            '',
            10,
            MUTED,
            wraplength=440,
            justify='left'
        )
        self.details.pack(
            anchor='w',
            pady=(0, 8)
        )

        actions = tk.Frame(
            right, bg=PANEL
        )
        actions.pack(
            fill='x',
            pady=4
        )

        self._button(
            actions,
            'Open website',
            self._open_website
        ).pack(side='left', padx=(0, 5))

        self._button(
            actions,
            'Audit site',
            self._audit,
            True
        ).pack(side='left', padx=(0, 5))

        self._button(
            actions,
            'Source',
            self._open_source
        ).pack(side='left')

        self._label(
            right,
            'AUDIT EVIDENCE',
            9, ACCENT, True
        ).pack(anchor='w', pady=(12, 5))

        self.audit_text = tk.Text(
            right,
            height=5,
            bg=BG,
            fg=TEXT,
            font=('Segoe UI', 11),
            relief='flat',
            wrap='word',
            padx=9,
            pady=6
        )
        self.audit_text.pack(fill='x')
        self.audit_text.configure(
            state='disabled'
        )

        drafts = tk.Frame(
            right, bg=PANEL
        )
        drafts.pack(
            fill='x',
            pady=(12, 7)
        )

        self._button(
            drafts,
            'Draft template',
            self._draft_template,
            True
        ).pack(side='left', padx=(0, 7))

        self._button(
            drafts,
            'Local AI (optional)',
            self._draft_ai
        ).pack(side='left', padx=(0, 7))

        self._button(
            drafts,
            'Copy',
            self._copy
        ).pack(side='right')

        self.draft_box = tk.Text(
            right,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            font=('Segoe UI', 11),
            relief='flat',
            padx=12,
            pady=10,
            height=10,
            wrap='word'
        )
        self.draft_box.pack(
            fill='both',
            expand=True
        )

        bottom = tk.Frame(
            right, bg=PANEL
        )
        bottom.pack(
            fill='x',
            pady=10
        )

        self._button(
            bottom,
            'Save edited draft',
            self._save_draft
        ).pack(side='left', padx=(0, 7))

        self._button(
            bottom,
            'Approve',
            lambda: self._stage('Approved'),
            True
        ).pack(side='left', padx=(0, 7))

        self._button(
            bottom,
            'Mark contacted',
            lambda: self._stage('Contacted')
        ).pack(side='left')

        bottom2 = tk.Frame(
            right, bg=PANEL
        )
        bottom2.pack(fill='x')

        self._label(
            bottom2,
            'Stage:',
            10, MUTED
        ).pack(side='left', padx=(0, 7))

        self.stage = tk.StringVar(
            value='New'
        )

        ttk.Combobox(
            bottom2,
            textvariable=self.stage,
            values=STAGES,
            width=16,
            state='readonly'
        ).pack(side='left')

        self._button(
            bottom2,
            'Update stage',
            lambda: self._stage(
                self.stage.get()
            )
        ).pack(side='left', padx=7)

        self._label(
            bottom2,
            'Manual outreach only',
            9, MUTED
        ).pack(side='right')

        foot = tk.Frame(
            self.root,
            bg=BG,
            padx=25,
            pady=12
        )
        foot.pack(fill='x')

        self._label(
            foot,
            '© OpenStreetMap contributors · ODbL',
            9, MUTED
        ).pack(side='left')

        self._label(
            foot,
            'SQLite locally • No auto emails',
            9, MUTED
        ).pack(side='right')

    def _msg(self, text):
        self.status.config(
            text=text[:110]
        )

    def _run_background(
        self, description, action, callback
    ):
        if self.busy:
            messagebox.showinfo(
                'Please finish first',
                'Another task is running.'
            )
            return

        self.busy = True
        self._msg(description)

        def job():
            try:
                result = action()
                self.queue.put(
                    ('success', callback, result)
                )
            except Exception as exc:
                self.queue.put(
                    ('error', None, str(exc))
                )

        threading.Thread(
            target=job,
            daemon=True
        ).start()

    def _poll(self):
        try:
            while True:
                kind, callback, value = (
                    self.queue.get_nowait()
                )
                self.busy = False

                if kind == 'error':
                    self._msg(
                        'Task failed. See explanation.'
                    )
                    messagebox.showerror(
                        'Could not complete',
                        value[:350]
                        + '\n\nUse Research web / Import CSV '
                        'if API is unavailable.'
                    )
                else:
                    callback(value)

        except queue.Empty:
            pass

        self.root.after(
            125, self._poll
        )

    def _refresh(self):
        previous = self.selected_id

        self.table.delete(
            *self.table.get_children()
        )

        rows = self.store.all()

        for idx, p in enumerate(rows):
            self.table.insert(
                '',
                'end',
                iid=p['id'],
                tags=(
                    'odd' if idx % 2
                    else 'even',
                ),
                values=(
                    p['name'][:32],
                    p['city'].split(',')[0],
                    'Yes' if p['website'] else 'No',
                    p['score'],
                    p['stage']
                )
            )

        approved = sum(
            p['stage'] in (
                'Approved',
                'Contacted',
                'Replied',
                'Qualified'
            )
            for p in rows
        )

        self.stats.config(
            text=(
                f'{len(rows)} saved prospects   •   '
                f'{approved} approved/contacted'
            )
        )

        if previous and self.table.exists(previous):
            self.table.selection_set(previous)
            self.table.see(previous)
            self._show(previous)

    def _selected(self):
        if not self.selected_id:
            messagebox.showinfo(
                'Select business',
                'Choose a business from the list.'
            )
            return None

        return self.store.one(
            self.selected_id
        )

    def _choose(self, _event=None):
        selection = self.table.selection()

        if selection:
            self.selected_id = selection[0]
            self._show(self.selected_id)

    def _set_readonly_text(
        self, widget, value
    ):
        widget.config(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', value)
        widget.config(state='disabled')

    def _show(self, item_id):
        p = self.store.one(item_id)

        if not p:
            return

        self.lead_label.config(
            text=p['name']
        )

        self.details.config(
            text=(
                f"{p['category']} · {p['city']}\n"
                f"Website: {short_website_display(p['website'])}\n"
                f"Public business email: {p['email'] or 'Not listed'}\n"
                f"Research priority score: {p['score']}/95"
            )
        )

        audit = p['audit']
        info = audit.get(
            'summary', 'Not audited yet'
        )

        if audit.get('checked'):
            if audit.get('issues'):
                info += (
                    '\n• '
                    + '\n• '.join(
                        audit['issues']
                    )
                )
            else:
                info += (
                    '\nNo issues detected '
                    'by these limited checks.'
                )

        self._set_readonly_text(
            self.audit_text, info
        )

        self.draft_box.delete(
            '1.0', 'end'
        )

        self.draft_box.insert(
            '1.0',
            p['draft'] or (
                'Choose Draft template or Local AI '
                'to prepare a message.'
            )
        )

        self.stage.set(p['stage'])

    def _search(self):
        if self.busy:
            messagebox.showinfo(
                'Search in progress',
                'Please finish the current task.'
            )
            return

        elapsed = (
            time.monotonic()
            - self.last_search_at
        )

        if self.last_search_at and elapsed < 12:
            messagebox.showinfo(
                'Search cooldown',
                f'Try again in {int(12-elapsed)+1}s.'
            )
            return

        city = self.city.get()
        category = self.category.get()
        key = (city, category)

        if key in self.last_searches:
            messagebox.showinfo(
                'Already searched',
                'This market was searched in this session. '
                'Switch city/industry or restart to refresh.'
            )
            return

        api_key = self._get_api_key()

        if not api_key:
            self._msg(
                'Geoapify key required.'
            )
            return

        self.last_search_at = time.monotonic()

        self._run_background(
            'Finding businesses via Geoapify...',
            lambda: geoapify_discover(
                city, category, api_key
            ),
            lambda rows: self._handle_results(
                rows, key
            )
        )

    def _handle_results(
        self, rows, key
    ):
        self.last_searches.add(key)

        added = self.store.upsert(rows)
        self._refresh()

        self._msg(
            f'{len(rows)} places found, '
            f'{added} new saved. Verify details.'
        )

        if not rows:
            messagebox.showinfo(
                'No places found',
                'No listings in this 3.5 km circle. '
                'Try another city/category or CSV import.'
            )

    def _research_web(self):
        city = self.city.get()
        category = self.category.get()

        industry_terms = {
            'Salons & barbers': 'hair salons barbers',
            'Restaurants': 'restaurants',
            'Cleaning & laundry': 'cleaning companies laundry services',
            'Real estate agents': 'real estate agencies',
            'Gyms': 'gyms fitness centres',
            'Dental clinics': 'dental clinics',
        }

        query = (
            f'{industry_terms.get(category, category)} '
            f'{city} official business websites'
        )

        url = (
            'https://www.google.com/search?'
            + urllib.parse.urlencode({
                'q': query
            })
        )

        webbrowser.open(url)

        self._msg(
            'Browser opened. Verify business details '
            'then import or add manually.'
        )

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title='Import prospect CSV',
            filetypes=[('CSV files', '*.csv')]
        )

        if not path:
            return

        file_path = Path(path)

        if file_path.stat().st_size > 2_000_000:
            messagebox.showerror(
                'CSV too large',
                'Use a small CSV under 2 MB.'
            )
            return

        try:
            with file_path.open(
                'r', newline='',
                encoding='utf-8-sig'
            ) as fh:
                reader = csv.DictReader(fh)

                if not reader.fieldnames:
                    raise ValueError(
                        'CSV needs header row: '
                        'name,website,email,city,category,source_url'
                    )

                rows = []
                rejected = 0

                for i, row in enumerate(reader):
                    if i >= 250:
                        rejected += 1
                        break

                    if None in row:
                        rejected += 1
                        continue

                    clean = {
                        (k or '').strip().lower():
                        (v or '').strip()
                        for k, v in row.items()
                    }

                    name = (
                        clean.get('name')
                        or clean.get('business')
                        or clean.get('company')
                        or ''
                    )[:160]

                    if not name:
                        rejected += 1
                        continue

                    raw_url = (
                        clean.get('website')
                        or clean.get('url')
                        or ''
                    )

                    url = normalize_url(raw_url)

                    if raw_url and not url:
                        rejected += 1
                        continue

                    email = (
                        clean.get('email') or ''
                    )[:160]

                    if email and not re.fullmatch(
                        r'[^\s@;,]+@[^\s@;,]+\.[^\s@;,]+',
                        email
                    ):
                        rejected += 1
                        continue

                    city = (
                        clean.get('city')
                        or self.city.get()
                    )[:100]

                    category = (
                        clean.get('category')
                        or clean.get('industry')
                        or self.category.get()
                    )[:100]

                    source_url = normalize_url(
                        clean.get('source_url') or ''
                    )

                    identity = (
                        f'{city.lower()}|'
                        f'{category.lower()}|'
                        f'{(url or name).lower()}'
                    )

                    uid = hashlib.sha256(
                        identity.encode('utf-8')
                    ).hexdigest()[:24]

                    rows.append({
                        'id': 'csv:' + uid,
                        'name': name,
                        'city': city,
                        'category': category,
                        'website': url,
                        'email': email,
                        'source': 'CSV import',
                        'source_url': source_url
                    })

            if not rows:
                messagebox.showwarning(
                    'No leads imported',
                    f'No usable rows. Skipped: {rejected}.'
                )
                return

            count = self.store.upsert(rows)
            self._refresh()

            self._msg(
                f'Imported {count} new prospects.'
            )

            messagebox.showinfo(
                'CSV import complete',
                f'New prospects: {count}\n'
                f'Already saved: {len(rows)-count}\n'
                f'Invalid rows: {rejected}'
            )

        except (
            OSError, UnicodeDecodeError,
            ValueError, csv.Error
        ) as exc:
            messagebox.showerror(
                'CSV import failed',
                str(exc)[:300]
            )

    def _add_manual(self):
        name = simpledialog.askstring(
            'Manual prospect',
            'Public business name:'
        )

        if not name or not name.strip():
            return

        website = simpledialog.askstring(
            'Manual prospect',
            'Business website (optional):'
        ) or ''

        if website and not normalize_url(website):
            messagebox.showerror(
                'Invalid URL',
                'Enter a normal public website.'
            )
            return

        email = simpledialog.askstring(
            'Manual prospect',
            'Public business email (optional):'
        ) or ''

        if email and (
            '@' not in email or ' ' in email
        ):
            messagebox.showerror(
                'Invalid email',
                'Enter a valid business email.'
            )
            return

        from uuid import uuid4
        key = 'manual:' + uuid4().hex

        self.store.upsert([{
            'id': key,
            'name': name.strip(),
            'city': self.city.get(),
            'category': self.category.get(),
            'website': normalize_url(website),
            'email': email.strip(),
            'source': 'Manually entered',
            'source_url': ''
        }])

        self._refresh()
        self.table.selection_set(key)
        self.table.see(key)
        self.selected_id = key
        self._show(key)

        self._msg(
            'Prospect added. Verify details before outreach.'
        )

    def _open_website(self):
        p = self._selected()

        if p and p['website']:
            webbrowser.open(p['website'])

    def _open_source(self):
        p = self._selected()

        if p and p['source_url']:
            webbrowser.open(p['source_url'])

    def _audit(self):
        p = self._selected()

        if not p:
            return

        item_id = p['id']

        self._run_background(
            'Checking public homepage...',
            lambda: inspect_website(p['website']),
            lambda audit: self._audit_done(
                item_id, audit
            )
        )

    def _audit_done(
        self, item_id, audit
    ):
        self.store.update(
            item_id,
            audit_json=json.dumps(audit),
            score=audit['score']
        )

        self._refresh()
        self._msg(
            'Basic website audit completed.'
        )

    def _draft_template(self):
        p = self._selected()

        if not p:
            return

        draft = outreach_draft(p)

        self.store.update(
            p['id'],
            draft=draft,
            stage='Drafted'
        )

        self._refresh()
        self._msg(
            'Template draft saved.'
        )

    def _draft_ai(self):
        p = self._selected()

        if not p:
            return

        item_id = p['id']

        self._run_background(
            'Generating local AI draft...',
            lambda: ollama_draft(p),
            lambda draft: self._ai_done(
                item_id, draft
            )
        )

    def _ai_done(self, item_id, draft):
        self.store.update(
            item_id,
            draft=draft,
            stage='Drafted'
        )

        self._refresh()
        self._msg(
            'AI draft generated. Check facts and tone.'
        )

    def _save_draft(self):
        p = self._selected()

        if not p:
            return

        draft = self.draft_box.get(
            '1.0', 'end'
        ).strip()

        self.store.update(
            p['id'],
            draft=draft
        )

        self._msg(
            'Draft saved locally.'
        )

    def _copy(self):
        draft = self.draft_box.get(
            '1.0', 'end'
        ).strip()

        if draft:
            self.root.clipboard_clear()
            self.root.clipboard_append(draft)

            self._msg(
                'Draft copied. Manual outreach only.'
            )

    def _stage(self, status):
        p = self._selected()

        if not p:
            return

        if status == 'Contacted':
            if not messagebox.askyesno(
                'Confirm manual contact',
                'Have you already contacted this business?'
            ):
                return

        if status == 'Approved':
            draft = self.draft_box.get(
                '1.0', 'end'
            ).strip()

            if not draft or draft.startswith(
                'Choose Draft'
            ):
                messagebox.showinfo(
                    'Draft first',
                    'Write a draft before approving.'
                )
                return

            self.store.update(
                p['id'],
                draft=draft
            )

        self.store.update(
            p['id'],
            stage=status
        )

        self._refresh()
        self._msg(
            f'Lead marked {status}. No email sent.'
        )

    def _export(self):
        path = filedialog.asksaveasfilename(
            title='Save prospect CSV',
            defaultextension='.csv',
            initialfile='orrivon-prospects.csv',
            filetypes=[('CSV files', '*.csv')]
        )

        if not path:
            return

        n = self.store.export(Path(path))

        self._msg(
            f'Exported {n} prospects.'
        )

        messagebox.showinfo(
            'CSV export complete',
            f'Saved {n} prospects to:\n{path}\n\n'
            'Respect source attribution and data terms.'
        )


if __name__ == '__main__':
    enable_windows_dpi_awareness()

    root = tk.Tk()
    ClientHunter(root)
    root.mainloop()
