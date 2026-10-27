
"""Orrivon Pro — Duplicate Review + Bulk Website Audit."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import json
import re
import sqlite3
import time
import tkinter as tk
from tkinter import messagebox

from core import inspect_website
from app import (
    ClientHunter,
    BG,
    MUTED,
    enable_windows_dpi_awareness,
)


def word_key(text):
    return ' '.join(
        re.findall(r'[\w]+', (text or '').casefold())
    )


def url_key(raw):
    if not raw:
        return ''

    try:
        p = urlsplit(raw)
        host = (p.hostname or '').lower().removeprefix('www.')

        if not host:
            return ''

        path = (p.path or '/').rstrip('/') or '/'
        return host + path
    except ValueError:
        return ''


def duplicate_report(rows):
    strong = defaultdict(list)
    possible = defaultdict(list)

    for row in rows:
        name, city, category = (
            word_key(row.get(k))
            for k in ('name', 'city', 'category')
        )

        if not all((name, city, category)):
            continue

        site = url_key(row.get('website'))

        if site:
            strong[
                (name, city, category, site)
            ].append(row)
        else:
            possible[
                (name, city, category)
            ].append(row)

    strong_groups = [
        v for v in strong.values() if len(v) >= 2
    ]

    possible_groups = [
        v for v in possible.values() if len(v) >= 2
    ]

    return strong_groups, possible_groups


def safe_removal_ids(groups):
    deletes = []

    for group in groups:
        ranked = sorted(
            group,
            key=lambda r: (
                bool(
                    r.get('stage')
                    and r.get('stage') != 'New'
                ),
                bool((r.get('draft') or '').strip()),
                bool((r.get('audit') or {}).get('summary')),
                bool(r.get('email')),
                bool(r.get('source_url')),
            ),
            reverse=True,
        )

        keeper = ranked[0]

        for item in ranked[1:]:
            if item.get('stage') != 'New':
                continue

            if (item.get('draft') or '').strip():
                continue

            if (item.get('audit') or {}).get('summary'):
                continue

            if item.get('email'):
                if (
                    item['email'].strip().casefold()
                    != (keeper.get('email') or '').strip().casefold()
                ):
                    continue

            if item.get('source_url'):
                if (
                    item['source_url']
                    != (keeper.get('source_url') or '')
                ):
                    continue

            deletes.append(item['id'])

    return deletes


def backup_and_remove(store, ids):
    if not ids:
        return 0, None

    backup_dir = store.path.parent / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime(
        '%Y%m%d-%H%M%S-%f'
    )

    destination = backup_dir / (
        f'client_hunter_before_dedupe_{stamp}.sqlite3'
    )

    with store.lock:
        with sqlite3.connect(str(destination)) as target:
            store.conn.backup(target)

        try:
            store.conn.executemany(
                'DELETE FROM prospects WHERE id=?',
                [(i,) for i in ids],
            )
            store.conn.commit()
        except Exception:
            store.conn.rollback()
            raise

    return len(ids), destination


def audit_candidates(rows, limit=5):
    return [
        r for r in rows
        if r.get('website')
        and not (r.get('audit') or {}).get('summary')
    ][:limit]


def audit_batch(rows):
    results = []

    for i, row in enumerate(rows[:5], 1):
        try:
            audit = inspect_website(row['website'])
        except Exception as exc:
            audit = {
                'checked': False,
                'issues': [],
                'score': 35,
                'summary': (
                    f'Audit failed: {type(exc).__name__}'
                ),
            }

        results.append((row['id'], audit))

        if i < min(5, len(rows)):
            time.sleep(1.5)

    return results


class ImprovedClientHunter(ClientHunter):

    def _build(self):
        super()._build()

        mid = next(
            w for w in self.root.winfo_children()
            if isinstance(w, tk.PanedWindow)
        )

        tools = tk.Frame(
            self.root, bg=BG, padx=25, pady=3
        )
        tools.pack(fill='x', before=mid)

        self._button(
            tools,
            'Review duplicates',
            self._review_duplicates,
        ).pack(side='left', padx=(0, 8))

        self._button(
            tools,
            'Bulk audit (5)',
            self._bulk_audit,
        ).pack(side='left', padx=(0, 8))

        self._label(
            tools,
            'Safe review, no auto-send',
            9, MUTED,
        ).pack(side='left', padx=8)

    def _review_duplicates(self):
        if self.busy:
            messagebox.showinfo(
                'Busy', 'Finish current task first.'
            )
            return

        strong, possible = duplicate_report(
            self.store.all()
        )

        delete_ids = safe_removal_ids(strong)

        names = ', '.join(
            group[0]['name'] for group in strong[:4]
        ) or 'None'

        note = (
            f'Exact duplicate groups: {len(strong)}\n'
            f'Safe copies to remove: {len(delete_ids)}\n'
            f'Possible duplicates for manual review: '
            f'{len(possible)} groups\n'
            f'Examples: {names}\n\n'
            'Drafted, contacted, audited and different-source '
            'records will be preserved.\n'
            'Possible separate branches are not removed.'
        )

        if not delete_ids:
            messagebox.showinfo(
                'Duplicate review',
                note + '\n\nNo safely removable records found.',
            )
            self._msg(
                'Duplicate review finished; nothing removed.'
            )
            return

        approved = messagebox.askyesno(
            'Backup + remove duplicate copies?',
            note + '\n\nBackup and delete these safe New copies?',
        )

        if not approved:
            return

        try:
            count, backup = backup_and_remove(
                self.store, delete_ids
            )

            self.selected_id = None
            self._refresh()

            self._msg(
                f'Removed {count} duplicate copies; backup saved.'
            )

            messagebox.showinfo(
                'Cleanup complete',
                f'Deleted: {count}\nBackup: {backup}',
            )

        except Exception as exc:
            messagebox.showerror(
                'Cleanup error', str(exc)[:300]
            )

    def _bulk_audit(self):
        if self.busy:
            messagebox.showinfo(
                'Busy', 'Finish current task first.'
            )
            return

        eligible = audit_candidates(
            self.store.all(), limit=5
        )

        if not eligible:
            messagebox.showinfo(
                'Bulk audit',
                'No unaudited leads with websites left.\n'
                'Missing websites and previously checked '
                'leads are skipped.',
            )
            return

        approved = messagebox.askyesno(
            'Bulk website audit',
            f'Audit {len(eligible)} public homepages?\n'
            'They will be checked sequentially.\n'
            'HTTPS and robots.txt checks remain enabled.\n'
            'No emails will be sent.',
        )

        if not approved:
            return

        self._run_background(
            f'Auditing {len(eligible)} websites...',
            lambda: audit_batch(eligible),
            self._bulk_done,
        )

    def _bulk_done(self, results):
        for lead_id, audit in results:
            self.store.update(
                lead_id,
                audit_json=json.dumps(audit),
                score=audit.get('score', 35),
            )

        self._refresh()

        passed = sum(
            bool(a.get('checked'))
            for _, a in results
        )

        self._msg(
            f'Bulk audit completed: '
            f'{len(results)} attempted, {passed} checked.'
        )

        messagebox.showinfo(
            'Bulk audit finished',
            f'Attempted: {len(results)}\n'
            f'Checked: {passed}\n'
            f'Blocked/unreachable: {len(results)-passed}\n\n'
            'Review audit evidence before making client claims.',
        )


if __name__ == '__main__':
    enable_windows_dpi_awareness()
    root = tk.Tk()
    ImprovedClientHunter(root)
    root.mainloop()
