"""Unit tests for tickets.py - run with:  python -m unittest -v"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta

import tickets as t


class TicketTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.db)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            t.main(["--db", self.db, *argv])
        return out.getvalue()

    def test_full_ticket_lifecycle(self):
        out = self.run_cli("new", "--title", "Printer offline", "--category", "printer",
                           "--priority", "P2", "--location", "Ship Dock")
        self.assertIn("Created ticket #1", out)
        self.assertIn("printer-offline.md", out)
        self.run_cli("assign", "1", "bdonfack")
        self.run_cli("note", "1", "Checked cable")
        out = self.run_cli("resolve", "1", "Damaged patch cable replaced, test print OK")
        self.assertIn("SLA Met", out)
        out = self.run_cli("show", "1")
        self.assertIn("Resolved", out)
        self.assertIn("Checked cable", out)
        self.assertIn("bdonfack", out)

    def test_resolution_must_be_meaningful(self):
        self.run_cli("new", "--title", "X", "--category", "Other", "--priority", "P4")
        with self.assertRaises(SystemExit):
            self.run_cli("resolve", "1", "fixed")

    def test_invalid_category_rejected(self):
        with self.assertRaises(SystemExit):
            self.run_cli("new", "--title", "X", "--category", "Coffee", "--priority", "P4")

    def test_sla_status_rules(self):
        created = datetime(2026, 1, 1, 8, 0)
        base = {"priority": "P1", "created_at": created.strftime(t.TIME_FMT)}
        open_row = dict(base, status="Open", resolved_at=None)
        self.assertEqual(t.sla_status(open_row, at=created + timedelta(hours=1)), "On track")
        self.assertEqual(t.sla_status(open_row, at=created + timedelta(hours=3, minutes=30)), "At risk")
        self.assertEqual(t.sla_status(open_row, at=created + timedelta(hours=5)), "Breached")
        met = dict(base, status="Resolved", resolved_at=(created + timedelta(hours=2)).strftime(t.TIME_FMT))
        late = dict(base, status="Resolved", resolved_at=(created + timedelta(hours=6)).strftime(t.TIME_FMT))
        self.assertEqual(t.sla_status(met), "Met")
        self.assertEqual(t.sla_status(late), "Breached")

    def test_seed_and_report_find_recurring_issue(self):
        self.run_cli("seed")
        out = self.run_cli("report")
        self.assertIn("SLA compliance", out)
        self.assertIn("Label printer offline @ Ship Dock", out)

    def test_export(self):
        self.run_cli("seed", "--count", "5")
        path = self.db + ".csv"
        self.addCleanup(os.remove, path)
        self.run_cli("export", path)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(len(fh.readlines()), 6)


if __name__ == "__main__":
    unittest.main()
