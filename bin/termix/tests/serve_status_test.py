#!/usr/bin/env python3
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import serve_status  # noqa: E402


DESIRED = "http://127.0.0.1:8080"


class ServeStatusTests(unittest.TestCase):
    def test_empty_status(self):
        doc = serve_status.load("{}")
        summary = serve_status.summarize(doc, DESIRED)
        self.assertTrue(summary["empty"])
        self.assertFalse(summary["matches"])
        self.assertEqual(summary["funnel"], [])

    def test_plain_text_empty(self):
        doc = serve_status.load("No serve config")
        self.assertTrue(serve_status.is_empty(doc))

    def test_matching_root_proxy(self):
        doc = {
            "TCP": {"443": {"HTTPS": True}},
            "Web": {
                "karans-mac-mini.tail1e8436.ts.net:443": {
                    "/": {"Proxy": "http://127.0.0.1:8080"}
                }
            },
            "AllowFunnel": {
                "karans-mac-mini.tail1e8436.ts.net:443": {"/": False}
            },
        }
        self.assertTrue(serve_status.matches_desired(doc, DESIRED))
        self.assertEqual(serve_status.funnel_paths(doc), [])

    def test_conflicting_proxy(self):
        doc = {
            "Web": {
                "karans-mac-mini.tail1e8436.ts.net:443": {
                    "/": {"Proxy": "http://127.0.0.1:9119"}
                }
            }
        }
        self.assertFalse(serve_status.matches_desired(doc, DESIRED))
        self.assertFalse(serve_status.is_empty(doc))

    def test_funnel_enabled(self):
        doc = {
            "Web": {
                "karans-mac-mini.tail1e8436.ts.net:443": {
                    "/": {"Proxy": "http://127.0.0.1:8080"}
                }
            },
            "AllowFunnel": {
                "karans-mac-mini.tail1e8436.ts.net:443": {"/": True}
            },
        }
        self.assertEqual(
            serve_status.funnel_paths(doc),
            ["karans-mac-mini.tail1e8436.ts.net:443/"],
        )

    def test_cli_json(self):
        raw = json.dumps(
            {
                "Web": {
                    "host:443": {"/": {"Proxy": "http://127.0.0.1:8080/"}}
                }
            }
        )
        summary = serve_status.summarize(serve_status.load(raw), DESIRED)
        self.assertTrue(summary["matches"])

    def test_handlers_nested_status(self):
        doc = {
            "TCP": {"443": {"HTTPS": True}},
            "Web": {
                "karans-mac-mini.tail1e8436.ts.net:443": {
                    "Handlers": {
                        "/": {"Proxy": "http://127.0.0.1:8080"}
                    }
                }
            },
        }
        summary = serve_status.summarize(doc, DESIRED)
        self.assertFalse(summary["empty"])
        self.assertTrue(summary["matches"])
        self.assertEqual(summary["funnel"], [])
        self.assertEqual(
            summary["proxies"],
            [
                {
                    "host": "karans-mac-mini.tail1e8436.ts.net:443",
                    "proxy": DESIRED,
                }
            ],
        )

    def test_https_port_mismatch_is_not_a_match(self):
        doc = {
            "TCP": {"443": {"HTTPS": True}},
            "Web": {
                "karans-mac-mini.tail1e8436.ts.net:443": {
                    "Handlers": {"/": {"Proxy": DESIRED}}
                }
            },
        }
        self.assertTrue(serve_status.proxy_matches(doc, DESIRED))
        self.assertFalse(serve_status.matches_desired(doc, DESIRED, "8443"))
        summary = serve_status.summarize(doc, DESIRED, "8443")
        self.assertFalse(summary["matches"])
        self.assertTrue(summary["proxy_matches"])
        self.assertEqual(summary["https_ports"], ["443"])

    def test_https_port_8443_matches(self):
        doc = {
            "TCP": {"8443": {"HTTPS": True}},
            "Web": {
                "karans-mac-mini.tail1e8436.ts.net:8443": {
                    "Handlers": {"/": {"Proxy": DESIRED}}
                }
            },
        }
        self.assertTrue(serve_status.matches_desired(doc, DESIRED, "8443"))


if __name__ == "__main__":
    unittest.main()
