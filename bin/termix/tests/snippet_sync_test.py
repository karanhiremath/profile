#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from snippet_sync import (
    CTRL_A,
    CTRL_G,
    ESC,
    desired_snippets,
    parse_snippet_list,
    plan,
    snippet_content,
)


class SnippetSyncTest(unittest.TestCase):
    def test_content_is_the_zsh_command(self):
        self.assertEqual(snippet_content("cos"), "cos")
        self.assertEqual(snippet_content("mac"), "mac")
        self.assertEqual(snippet_content("status"), "status")

    def test_desired_includes_keys_then_sessions(self):
        rows = desired_snippets(["ao0", "cos", "mac", "phone-s", "cos"])
        names = [row["name"] for row in rows]
        self.assertEqual(names[:4], ["ctrl-g", "panes", "zoom", "esc"])
        self.assertIn("cos", names)
        self.assertIn("phone-s", names)
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["cos"]["folder"], "")
        self.assertEqual(by_name["cos"]["content"], "cos")
        self.assertEqual(by_name["ctrl-g"]["content"], CTRL_G)
        self.assertEqual(by_name["panes"]["content"], CTRL_A + "q")
        self.assertEqual(by_name["zoom"]["content"], CTRL_A + "z")
        self.assertEqual(by_name["wq"]["content"], ESC + ":wq")
        self.assertEqual(by_name["palette"]["content"], ESC + ":Telescope commands")
        self.assertTrue(by_name["ctrl-g"]["description"].startswith("hostctl:keys "))
        self.assertTrue(by_name["cos"]["description"].startswith("hostctl:attach mac "))

    def test_plan_recreates_foldered_snippets_and_deletes_gone(self):
        existing = [
            {
                "id": 1,
                "name": "cos",
                "folder": "tmux",
                "content": "old",
                "description": "hostctl:attach mac cos",
                "order": 7,
            },
            {
                "id": 2,
                "name": "gone",
                "folder": "tmux",
                "content": "termix gone",
                "description": "hostctl:attach mac gone",
                "order": 8,
            },
            {
                "id": 3,
                "name": "keep-me",
                "folder": "personal",
                "content": "echo hi",
                "description": "mine",
            },
        ]
        planned = plan(["cos", "mac"], existing)
        created = {row["name"] for row in planned["create"]}
        self.assertIn("cos", created)
        self.assertIn("mac", created)
        self.assertIn("ctrl-g", created)
        self.assertIn("palette", created)
        self.assertEqual(planned["update"], [])
        self.assertEqual({row["name"] for row in planned["delete"]}, {"cos", "gone"})

    def test_plan_updates_unfiled_content_in_place(self):
        existing = [
            {
                "id": 4,
                "name": "cos",
                "folder": "",
                "content": "old",
                "description": "hostctl:attach mac cos",
                "order": next(
                    row["order"]
                    for row in desired_snippets(["cos"])
                    if row["name"] == "cos"
                ),
            }
        ]
        planned = plan(["cos"], existing)
        self.assertEqual([row["name"] for row in planned["update"]], ["cos"])
        self.assertEqual(planned["update"][0]["id"], 4)
        self.assertNotIn("cos", {row["name"] for row in planned["create"]})

    def test_parse_snippet_list_shapes(self):
        self.assertEqual(len(parse_snippet_list({"snippets": [{"name": "cos"}]})), 1)
        self.assertEqual(len(parse_snippet_list([{"name": "cos"}])), 1)
        self.assertEqual(parse_snippet_list({}), [])


if __name__ == "__main__":
    unittest.main()
