
"""Orrivon Final MVP: lead qualification and approved Gmail drafts.

Keep app.py, core.py and orrivon_pro.py in the same folder.
No extra pip packages required. Emails are never auto-sent.
"""

from __future__ import annotations

import re
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import messagebox, simpledialog

from app import BG, MUTED, enable_windows_dpi_awareness
from core import ollama_draft, normalize_url
from orrivon_pro import ImprovedClientHunter


EMAIL_RE = re.compile(r"^[^\s@;,]+@[^\s@;,]+\.[^\s@;,]+$")

SAFE_FINDINGS = {
    "Meta description not detected":
        "a meta description wasn't detected in the fetched homepage HTML",
    "Mobile viewport tag not detected":
        "a mobile viewport tag wasn't detected in the fetched homepage HTML",
    "Homepage title not detected":
        "a page title wasn't detected in the fetched homepage HTML",
}


def email_format_ok(value: str) -> bool:
    """Check email syntax, not inbox ownership."""
    return bool(EMAIL_RE.fullmatch((value or "").strip()))


def priority_score(lead: dict) -> int:
    """Outreach readiness score, not website quality."""
    score = 20

    if lead.get("website"):
        score += 15

    if email_format_ok(lead.get("email", "")):
        score += 25

    audit = lead.get("audit") or {}

    if audit.get("checked"):
        score += 15
        score += min(
            15,
            5 * len([
                finding
                for finding in audit.get("issues", [])
                if finding in SAFE_FINDINGS
            ])
        )

    elif audit.get("summary") and lead.get("website"):
        score -= 5

    if lead.get("source_url"):
        score += 5

    return min(95, max(0, score))


def audit_observation(lead: dict) -> str:
    """Build a cautious observation from saved audit results."""
    audit = lead.get("audit") or {}

    if not audit.get("checked"):
        return ""

    match = next(
        (
            SAFE_FINDINGS[s]
            for s in audit.get("issues", [])
            if s in SAFE_FINDINGS
        ),
        ""
    )

    if not match:
        return ""

    return (
        "A basic automated check of your public homepage "
        "suggests "
        + match
        + ". This may need a manual check, especially if "
        "content loads dynamically."
    )


def personalized_email(lead: dict, ai: bool = False) -> str:
    """Create a personalized, factual business email."""
    name = str(lead.get("name") or "").strip()

    if not name:
        raise ValueError("Business name missing")

    category = str(
        lead.get("category") or "local businesses"
    ).lower()

    city = str(
        lead.get("city") or "your area"
    ).split(",")[0]

    benefits = "manage customer inquiries and bookings"

    if ai:
        choice = ollama_draft(lead)

        for phrase in (
            "organize customer bookings",
            "manage customer inquiries",
            "track customer follow-ups",
        ):
            if phrase in choice.lower():
                benefits = phrase
                break

    observed = audit_observation(lead)

    observation_paragraph = (
        observed + "\n\n"
    ) if observed else ""

    return (
        f"Subject: Quick idea for {name}\n\n"
        f"Hi {name} Team,\n\n"
        f"I came across your business while researching "
        f"{category} in {city}.\n\n"
        + observation_paragraph
        + "I'm Saif from Orrivon Digital. "
        "I build websites and simple CRM "
        + f"systems that help businesses {benefits}.\n\n"
        + "I have a working website-to-CRM demo. "
        "Would a quick 60-second walkthrough "
        "be useful?\n\n"
        + "Best regards,\n"
        "Saif\n"
        "Orrivon Digital"
    )


def split_email(draft: str) -> tuple[str, str]:
    first, sep, rest = draft.strip().partition("\n")

    if not sep or not first.lower().startswith("subject:"):
        raise ValueError(
            "Draft must start with 'Subject: ...'"
        )

    subject = first.split(":", 1)[1].strip()
    body = rest.strip()

    if not subject or not body:
        raise ValueError("Subject or body is empty")

    if any(
        bad in draft
        for bad in ("[Business Name]", "[Your Name]")
    ):
        raise ValueError(
            "Remove placeholders before approval"
        )

    return subject, body


class FinalClientHunter(ImprovedClientHunter):

    def _build(self):
        super()._build()

        mid = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.PanedWindow)
        )

        # LEAD MANAGEMENT BUTTONS

        row = tk.Frame(
            self.root,
            bg=BG,
            padx=25,
            pady=3
        )
        row.pack(fill="x", before=mid)

        self._button(
            row,
            "Qualify all leads",
            self._qualify_all
        ).pack(side="left", padx=(0, 7))

        self._button(
            row,
            "Top prospects",
            self._top_prospects
        ).pack(side="left", padx=(0, 7))

        self._button(
            row,
            "Evidence draft",
            self._draft_evidence
        ).pack(side="left", padx=(0, 7))

        self._button(
            row,
            "Check contact",
            self._check_contact
        ).pack(side="left", padx=(0, 7))

        self._button(
            row,
            "Edit contact",
            self._edit_contact
        ).pack(side="left", padx=(0, 7))

        # NEW: VISIBLE DRAFT CONTROLS

        draft_row = tk.Frame(
            self.root,
            bg=BG,
            padx=25,
            pady=3
        )
        draft_row.pack(fill="x", before=mid)

        self._button(
            draft_row,
            "View draft",
            self._preview_draft
        ).pack(side="left", padx=(0, 7))

        self._button(
            draft_row,
            "Copy draft",
            self._copy
        ).pack(side="left", padx=(0, 7))

        self._button(
            draft_row,
            "Approve",
            lambda: self._stage("Approved"),
            True
        ).pack(side="left", padx=(0, 7))

        self._button(
            draft_row,
            "Open Gmail draft",
            self._gmail_draft
        ).pack(side="left", padx=(0, 7))

        self._label(
            draft_row,
            "Review first - Gmail will not send automatically",
            9,
            MUTED
        ).pack(side="left", padx=5)

    # NEW: READABLE EMAIL PREVIEW

    def _preview_draft(self):
        lead = self._selected()

        if not lead:
            return

        draft = self.draft_box.get(
            "1.0", "end"
        ).strip()

        if not draft or draft.startswith("Choose Draft"):
            messagebox.showinfo(
                "No draft yet",
                "Click Evidence draft or Local AI first."
            )
            return

        preview = tk.Toplevel(self.root)

        preview.title(
            f"Outreach draft - {lead['name']}"
        )
        preview.geometry("760x560")
        preview.minsize(500, 350)
        preview.configure(bg=BG)

        self._label(
            preview,
            f"Review message for {lead['name']}",
            14,
            bold=True
        ).pack(
            anchor="w",
            padx=18,
            pady=(16, 8)
        )

        frame = tk.Frame(preview, bg=BG)
        frame.pack(
            fill="both",
            expand=True,
            padx=18
        )

        draft_text = tk.Text(
            frame,
            wrap="word",
            font=("Segoe UI", 11),
            bg="#162A3A",
            fg="#F0F6F7",
            padx=12,
            pady=12,
            relief="flat"
        )

        scrollbar = tk.Scrollbar(
            frame,
            command=draft_text.yview
        )

        draft_text.configure(
            yscrollcommand=scrollbar.set
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        draft_text.pack(
            side="left",
            fill="both",
            expand=True
        )

        draft_text.insert("1.0", draft)
        draft_text.configure(state="disabled")

        footer = tk.Frame(
            preview,
            bg=BG,
            padx=18,
            pady=12
        )
        footer.pack(fill="x")

        self._button(
            footer,
            "Copy draft",
            self._copy,
            True
        ).pack(side="left")

        self._button(
            footer,
            "Close",
            preview.destroy
        ).pack(side="right")

    def _update_priority(self, lead_id: str):
        lead = self.store.one(lead_id)

        if lead:
            self.store.update(
                lead_id,
                score=priority_score(lead)
            )

    def _qualify_all(self):
        rows = self.store.all()

        for item in rows:
            self.store.update(
                item["id"],
                score=priority_score(item)
            )

        self._refresh()

        ready = sum(
            email_format_ok(p.get("email", ""))
            for p in rows
        )

        self._msg(
            f"Qualified {len(rows)} prospects; "
            f"{ready} have a listed email format."
        )

        messagebox.showinfo(
            "Research priority recalculated",
            f"Prospects scored: {len(rows)}\n"
            f"With a listed email: {ready}\n\n"
            "Scores show outreach readiness, "
            "not website quality or a verified inbox."
        )

    def _top_prospects(self):
        candidates = sorted(
            (
                p for p in self.store.all()
                if email_format_ok(p.get("email", ""))
                and p.get("stage") not in (
                    "Contacted",
                    "Not interested"
                )
            ),
            key=priority_score,
            reverse=True
        )[:5]

        if not candidates:
            messagebox.showinfo(
                "Top prospects",
                "No public business email available. "
                "Research official contacts manually."
            )
            return

        lines = [
            f"{i}. {p['name']} - {priority_score(p)}/95"
            for i, p in enumerate(candidates, 1)
        ]

        messagebox.showinfo(
            "Top outreach-ready prospects",
            "\n".join(lines)
            + "\n\nVerify the public contact "
            "and website before outreach."
        )

        self.selected_id = candidates[0]["id"]

        self.table.selection_set(
            self.selected_id
        )
        self.table.see(self.selected_id)
        self._show(self.selected_id)

    def _draft_evidence(self):
        lead = self._selected()

        if not lead:
            return

        draft = personalized_email(
            lead, ai=False
        )

        self.store.update(
            lead["id"],
            draft=draft,
            stage="Drafted"
        )

        self._refresh()

        self._msg(
            "Evidence-based draft saved. "
            "Review before approval."
        )

    def _draft_ai(self):
        lead = self._selected()

        if not lead:
            return

        lead_id = lead["id"]

        self._run_background(
            "Local AI choosing relevant benefit...",
            lambda: personalized_email(
                lead, ai=True
            ),
            lambda draft: self._ai_done(
                lead_id, draft
            )
        )

    def _audit_done(self, item_id, audit):
        super()._audit_done(item_id, audit)

        self._update_priority(item_id)
        self._refresh()

    def _bulk_done(self, results):
        super()._bulk_done(results)

        for item_id, _audit in results:
            self._update_priority(item_id)

        self._refresh()

    def _save_draft(self):
        lead = self._selected()

        if not lead:
            return

        draft = self.draft_box.get(
            "1.0", "end"
        ).strip()

        previous = (
            lead.get("draft") or ""
        ).strip()

        if draft != previous:
            self.store.update(
                lead["id"],
                draft=draft,
                stage="Drafted"
            )

            self._refresh()

            self._msg(
                "Edited draft saved. "
                "Re-approve before outreach."
            )
        else:
            self._msg("No changes to save.")

    def _check_contact(self):
        lead = self._selected()

        if not lead:
            return

        value = (
            lead.get("email") or ""
        ).strip()

        if value and email_format_ok(value):
            note = (
                f"Listed address: {value}\n"
                "Syntax: valid\n"
                "Inbox/deliverability: NOT verified\n\n"
                "Confirm this is a public business "
                "contact before outreach."
            )
        else:
            note = (
                "No valid listed business email.\n"
                "Find an official business contact form "
                "or public contact address.\n"
                "Do not guess private email addresses."
            )

        messagebox.showinfo(
            "Contact check",
            note
        )

    def _edit_contact(self):
        lead = self._selected()

        if not lead:
            return

        messagebox.showinfo(
            "Verified public details only",
            "Edit only contact details confirmed "
            "from official public business sources."
        )

        email = simpledialog.askstring(
            "Public business email",
            "Enter verified public business email:",
            initialvalue=lead.get("email") or "",
            parent=self.root
        )

        if email is None:
            return

        email = email.strip()

        if email and not email_format_ok(email):
            messagebox.showerror(
                "Invalid email",
                "Invalid email format. Nothing saved."
            )
            return

        raw_site = simpledialog.askstring(
            "Official website",
            "Enter official website:",
            initialvalue=lead.get("website") or "",
            parent=self.root
        )

        if raw_site is None:
            return

        site = normalize_url(raw_site)

        if raw_site.strip() and not site:
            messagebox.showerror(
                "Invalid website",
                "Enter a public HTTP/HTTPS website."
            )
            return

        fields = {
            "email": email,
            "website": site
        }

        website_changed = (
            site != (lead.get("website") or "")
        )

        email_changed = (
            email != (lead.get("email") or "")
        )

        if website_changed:
            fields["audit_json"] = "{}"

        if lead.get("stage") == "Approved" and (
            email_changed or website_changed
        ):
            fields["stage"] = "Drafted"

        self.store.update(
            lead["id"],
            **fields
        )

        self._update_priority(lead["id"])
        self._refresh()

        self._msg(
            "Business details updated. "
            "Re-audit changed websites."
        )

    def _gmail_draft(self):
        lead = self._selected()

        if not lead:
            return

        if lead.get("stage") != "Approved":
            messagebox.showwarning(
                "Approve first",
                "Review and approve the final message "
                "before opening Gmail."
            )
            return

        email = (
            lead.get("email") or ""
        ).strip()

        if not email_format_ok(email):
            messagebox.showwarning(
                "No public email",
                "This business has no valid listed email. "
                "Use its official contact channel manually."
            )
            return

        text = self.draft_box.get(
            "1.0", "end"
        ).strip()

        if text != (
            lead.get("draft") or ""
        ).strip():
            messagebox.showwarning(
                "Unsaved changes",
                "Save edited draft and approve it again."
            )
            return

        try:
            subject, body = split_email(text)

        except ValueError as exc:
            messagebox.showerror(
                "Invalid draft",
                str(exc)
            )
            return

        if not messagebox.askyesno(
            "Open Gmail composition?",
            f"To: {email}\n"
            f"Subject: {subject}\n\n"
            "Open an UNSENT draft in Gmail?\n"
            "You must review it and press Send yourself.\n"
            "Respect opt-outs."
        ):
            return

        url = (
            "https://mail.google.com/mail/?"
            + urllib.parse.urlencode({
                "view": "cm",
                "fs": "1",
                "to": email,
                "su": subject,
                "body": body
            })
        )

        webbrowser.open(url)

        self._msg(
            "Gmail compose opened. NOT sent. "
            "Mark contacted only after sending."
        )


if __name__ == "__main__":
    enable_windows_dpi_awareness()

    root = tk.Tk()

    FinalClientHunter(root)

    root.mainloop()
