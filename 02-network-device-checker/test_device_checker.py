"""Unit tests for device_checker.py - run with:  python -m unittest -v"""

import csv
import os
import socket
import tempfile
import threading
import unittest
from unittest import mock

import device_checker as dc


class ClassifyTests(unittest.TestCase):
    def make(self, **kw):
        r = dc.Result(device=dc.Device(name="P1", host="10.0.0.5", device_type=kw.pop("dtype", "printer")))
        for k, v in kw.items():
            setattr(r, k, v)
        dc.classify(r)
        return r

    def test_up_when_ping_and_all_ports_open(self):
        r = self.make(ip="10.0.0.5", ping_ok=True, open_ports=[9100, 80])
        self.assertEqual(r.status, "UP")
        self.assertEqual(r.hint, "")

    def test_degraded_when_port_closed(self):
        r = self.make(ip="10.0.0.5", ping_ok=True, open_ports=[80], closed_ports=[9100])
        self.assertEqual(r.status, "DEGRADED")
        self.assertIn("Print Spooler", r.hint)

    def test_degraded_icmp_blocked(self):
        r = self.make(ip="10.0.0.5", ping_ok=False, open_ports=[443], dtype="web")
        self.assertEqual(r.status, "DEGRADED")
        self.assertIn("ICMP", r.hint)

    def test_down_when_nothing_answers(self):
        r = self.make(ip="10.0.0.5", ping_ok=False, closed_ports=[9100, 80])
        self.assertEqual(r.status, "DOWN")
        self.assertIn("config page", r.hint)

    def test_dns_fail(self):
        r = self.make(ip=None, dtype="server")
        self.assertEqual(r.status, "DNS FAIL")
        self.assertIn("flushdns", r.hint)


class ResolveTests(unittest.TestCase):
    def test_ip_passthrough(self):
        self.assertEqual(dc.resolve("192.168.1.10"), "192.168.1.10")

    def test_bad_name_returns_none(self):
        self.assertIsNone(dc.resolve("does-not-exist.invalid"))


class PortTests(unittest.TestCase):
    def test_open_and_closed_port(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        t = threading.Thread(target=lambda: server.accept(), daemon=True)
        t.start()
        try:
            self.assertTrue(dc.port_open("127.0.0.1", port))
        finally:
            server.close()
        self.assertFalse(dc.port_open("127.0.0.1", port, timeout_s=0.5))


class CsvTests(unittest.TestCase):
    def write_csv(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_load_devices_with_ports_and_defaults(self):
        path = self.write_csv("name,host,type,location,ports\nP1,10.0.0.1,Printer,Dock,9100;80\nPC,pc01,,Office,\n")
        devices = dc.load_devices(path)
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].device_type, "printer")
        self.assertEqual(devices[0].ports, [9100, 80])
        self.assertEqual(devices[1].device_type, "workstation")
        self.assertEqual(devices[1].ports, [])

    def test_missing_columns_raises(self):
        path = self.write_csv("device,address\nP1,10.0.0.1\n")
        with self.assertRaises(ValueError):
            dc.load_devices(path)

    def test_rows_without_host_are_skipped(self):
        path = self.write_csv("name,host\nP1,\nP2,10.0.0.2\n")
        self.assertEqual([d.name for d in dc.load_devices(path)], ["P2"])


class EndToEndTests(unittest.TestCase):
    @mock.patch.object(dc, "ping", return_value=3.2)
    @mock.patch.object(dc, "port_open", side_effect=lambda ip, port, t=1.5: port == 80)
    def test_check_device_uses_default_ports(self, _port, _ping):
        r = dc.check_device(dc.Device(name="P1", host="10.0.0.9", device_type="printer"))
        self.assertEqual(r.open_ports, [80])
        self.assertEqual(r.closed_ports, [9100])
        self.assertEqual(r.status, "DEGRADED")

    @mock.patch.object(dc, "ping", return_value=None)
    @mock.patch.object(dc, "port_open", return_value=False)
    def test_reports_are_written(self, _port, _ping):
        results = [dc.check_device(dc.Device(name="P<1>", host="10.0.0.9", device_type="printer"))]
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "r.html")
            csv_path = os.path.join(tmp, "r.csv")
            dc.write_html(results, html_path)
            dc.write_csv(results, csv_path)
            with open(html_path, encoding="utf-8") as fh:
                page = fh.read()
            self.assertIn("P&lt;1&gt;", page)  # names are HTML-escaped
            with open(csv_path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["status"], "DOWN")


if __name__ == "__main__":
    unittest.main()
