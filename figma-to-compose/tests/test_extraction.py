#!/usr/bin/env python3
"""Regression tests for the extraction half of the pipeline.

    python3 -m unittest discover -s figma-to-compose/tests -v

Fixtures are synthetic but copy the shapes real `get_design_context` responses take:
text inside a `leading-[0]` wrapper, mixed-style `<span>` runs, gradients in
`style={{ backgroundImage }}`, image-crop wrappers, helper components with variant
ternaries, and a metadata tree whose instances come back as childless stubs.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIX = HERE / "fixtures"


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, check=False)


def walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


class ContextTreeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        out = run("context_to_ir.py", "--context", str(FIX / "screen.context.json"),
                  "--tree", str(cls.tmp / "tree.json"), "--texts", str(cls.tmp / "texts.json"),
                  "--styles", str(cls.tmp / "styles.json"), "--assets", str(cls.tmp / "assets.json"))
        assert out.returncode == 0, out.stderr
        cls.tree = json.loads((cls.tmp / "tree.json").read_text())
        cls.nodes = {n["id"]: n for n in walk(cls.tree["root"])}
        cls.texts = json.loads((cls.tmp / "texts.json").read_text())
        cls.assets = json.loads((cls.tmp / "assets.json").read_text())

    def test_json_envelope_and_bare_code_agree(self):
        out = run("context_to_ir.py", "--context", str(FIX / "screen.tsx"),
                  "--tree", str(self.tmp / "tree2.json"), "--texts", str(self.tmp / "t2.json"),
                  "--styles", str(self.tmp / "s2.json"), "--assets", str(self.tmp / "a2.json"))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads((self.tmp / "tree2.json").read_text())["root"], self.tree["root"])

    def test_auto_layout_is_read_not_guessed(self):
        root = self.nodes["5:8469"]["layout"]
        self.assertEqual(root["direction"], "column")
        self.assertEqual(root["gap"], 16)
        self.assertEqual(root["padding"], {"top": 24, "end": 20, "bottom": 24, "start": 20})
        row = self.nodes["5:8470"]["layout"]
        self.assertEqual((row["direction"], row["gap"], row["align"]["cross"], row["width"]),
                         ("row", 12, "center", "fill"))
        self.assertEqual(self.nodes["5:8472"]["layout"]["weight"], 1)
        self.assertEqual(self.nodes["5:8474"]["layout"]["align"], {"main": "center", "cross": "center"})

    def test_text_in_wrapper_keeps_string_and_line_height(self):
        title = self.nodes["5:8472"]["text"]
        self.assertEqual(title["content"], "Kết nối")
        self.assertEqual(title["lineHeight"], 24)
        self.assertEqual((title["family"], title["weight"], title["size"]), ("Inter", 600, 18))
        self.assertEqual(title["letterSpacing"], {"px": -0.36, "em": -0.02})

    def test_mixed_style_runs_and_inherited_style(self):
        size = self.nodes["5:8481"]["text"]
        self.assertEqual(size["content"], "Kích thước: ~3.6 MB")
        self.assertEqual(size["family"], "Inter")                 # inherited from the wrapper div
        self.assertEqual(size["color"], {"hex": "#8E9AA8"})       # inherited
        self.assertEqual(size["lineHeight"], "auto")              # from the runs, not leading-[0]
        self.assertEqual(size["runs"][1], {"text": "~3.6 MB", "color": {"hex": "#00DC82"}})

    def test_line_breaks_entities_multiplier_and_case(self):
        lines = self.nodes["5:8482"]["text"]
        self.assertEqual(lines["content"], "Line one's\nline two")
        self.assertEqual(lines["lineHeight"], 18)                 # 1.5 × 12
        self.assertEqual(lines["textCase"], "upper")

    def test_named_colors_gradient_and_shadow(self):
        self.assertEqual(self.nodes["5:8469"]["style"]["fill"], {"hex": "#FFFFFF"})
        cta = self.nodes["5:8474"]["style"]
        self.assertEqual(cta["gradient"]["angle"], 180)
        self.assertEqual([s["hex"] for s in cta["gradient"]["stops"]], ["#FD75A7", "#FF9A8B"])
        self.assertEqual(cta["shadows"][0], {"x": 0, "y": 4, "blur": 12, "spread": 0, "hex": "#FD75A7", "alpha": 0.35})
        self.assertEqual(self.nodes["5:8475"]["text"]["color"], {"hex": "#FFFFFF"})

    def test_rgba_border_opacity_corners_inline_gradient(self):
        divider = self.nodes["5:8476"]["style"]
        self.assertEqual(divider["fill"], {"hex": "#141414", "alpha": 0.06})
        self.assertEqual(divider["border"], {"width": 1.5, "hex": "#E5E5E5"})
        self.assertEqual(divider["opacity"], 0.8)
        accent = self.nodes["5:8477"]["style"]
        self.assertEqual(accent["corners"], {"tl": 16, "tr": 0, "br": 0, "bl": 16})
        self.assertEqual(accent["gradient"]["angle"], 91.5)
        self.assertEqual(accent["gradient"]["stops"][0], {"hex": "#4ADE80", "position": 0.25})
        self.assertEqual(accent["dropShadows"][0]["alpha"], 0.35)

    def test_assets_belong_to_nearest_node(self):
        owners = {a["id"]: a["url"].rsplit("/", 1)[-1] for a in self.assets}
        self.assertEqual(owners["5:8471"], "abc123.svg")
        self.assertEqual(owners["5:8473"], "def456.svg")
        self.assertEqual(owners["5:8478"], "thumb789.png")
        self.assertEqual(self.nodes["5:8478"]["asset"]["style"]["contentScale"], "Crop")
        self.assertEqual(self.nodes["5:8478"]["layout"]["aspectRatio"], 1)

    def test_component_instances_resolve_their_own_variant(self):
        spicy, calm = self.nodes["5:8490"], self.nodes["5:8491"]
        self.assertEqual(spicy["component"], "TopicCard")
        self.assertEqual(spicy["componentId"], "5:7804")
        self.assertEqual(calm["componentId"], "5:7744")
        self.assertEqual(spicy["style"]["fill"], {"hex": "#FFE9EA"})
        self.assertEqual(calm["style"]["fill"], {"hex": "#ECFDF5"})
        self.assertEqual(spicy["children"][0]["text"]["content"], "Spicy")
        self.assertEqual(calm["children"][0]["text"]["content"], "Calm")
        self.assertEqual(spicy["props"], {"variant": "Spicy"})


class IrBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        t = cls.tmp
        out = run("context_to_ir.py", "--context", str(FIX / "screen.tsx"), "--tree", str(t / "tree.json"),
                  "--texts", str(t / "texts.json"), "--styles", str(t / "styles.json"), "--assets", str(t / "assets.json"))
        assert out.returncode == 0, out.stderr
        out = run("figma_to_ir.py", "--metadata", str(FIX / "screen.metadata.xml"), "--tree", str(t / "tree.json"),
                  "--texts", str(t / "texts.json"), "--styles", str(t / "styles.json"),
                  "--assets", str(t / "assets.json"), "--out", str(t / "ir.json"))
        assert out.returncode == 0, out.stderr
        cls.ir = json.loads((t / "ir.json").read_text())
        cls.nodes = {n["id"]: n for n in walk(cls.ir["root"])}

    def test_layout_comes_from_auto_layout(self):
        row = self.nodes["5:8470"]["layout"]
        self.assertEqual(row["layoutSource"], "auto-layout")
        self.assertEqual(row["gap"]["raw"], 12)
        self.assertEqual(row["width"], "fill")
        self.assertEqual(self.nodes["5:8472"]["layout"]["weight"], 1)
        self.assertEqual(self.ir["schema"], "ui-ir/v2")

    def test_icon_frame_collapses_to_its_exported_svg(self):
        icon = self.nodes["5:8471"]
        self.assertEqual(icon["role"], "icon")
        self.assertNotIn("children", icon)
        exports = {a["id"]: a["export"] for a in self.ir["assets"]}
        self.assertTrue(exports["5:8471"].endswith("abc123.svg"))

    def test_text_carries_full_style(self):
        text = self.nodes["5:8482"]["text"]
        self.assertEqual(text["style"]["lineHeight"], 18)
        self.assertEqual(text["lines"], 2)
        self.assertEqual(text["textCase"], "upper")
        self.assertEqual(self.nodes["5:8481"]["text"]["runs"][1]["color"]["raw"], "#00DC82")

    def test_styles_carry_effects_with_token_slots(self):
        cta = self.nodes["5:8474"]["style"]
        self.assertEqual(cta["radius"], {"raw": 999, "token": None})
        self.assertEqual(cta["shadows"][0]["color"], {"raw": "#FD75A7", "token": None, "alpha": 0.35})
        self.assertEqual(self.nodes["5:8476"]["style"]["fill"]["alpha"], 0.06)

    def test_instance_stub_is_grafted_with_instance_ids_and_no_rect(self):
        card = self.nodes["5:8490"]
        self.assertIn("rect", card)
        child = card["children"][0]
        self.assertEqual(child["id"], "I5:8490;5:7750")
        self.assertEqual(child["text"]["content"], "Spicy")
        self.assertNotIn("rect", child)
        self.assertEqual(card["mapping"]["designComponent"], "TopicCard")


class GeometryFallbackTest(unittest.TestCase):
    """No --tree: layout derived from x/y/w/h, with the three ordering/sizing bugs fixed."""

    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "empty.json").write_text("{}")
        out = run("figma_to_ir.py", "--metadata", str(FIX / "geometry.metadata.xml"),
                  "--texts", str(tmp / "empty.json"), "--styles", str(tmp / "empty.json"),
                  "--out", str(tmp / "ir.json"))
        assert out.returncode == 0, out.stderr
        cls.nodes = {n["id"]: n for n in walk(json.loads((tmp / "ir.json").read_text())["root"])}

    def test_row_keeps_left_to_right_order_when_children_are_centred(self):
        row = self.nodes["1:2"]
        self.assertEqual([c["name"] for c in row["children"]], ["icon", "title", "chevron"])
        self.assertEqual(row["layout"]["align"]["cross"], "center")

    def test_column_detected_regardless_of_layer_order(self):
        lst = self.nodes["1:6"]
        self.assertEqual(lst["layout"]["direction"], "column")
        self.assertEqual([c["name"] for c in lst["children"]], ["item-1", "item-2", "item-3"])
        self.assertEqual(lst["layout"]["gap"]["raw"], 14)

    def test_inset_child_fills_instead_of_leaking_frame_width(self):
        row = self.nodes["1:2"]["layout"]
        self.assertEqual(row["width"], "fill")
        self.assertEqual(row["margin"], {"start": 20, "end": 20})
        self.assertEqual(self.nodes["1:7"]["layout"]["width"], "fill")
        self.assertEqual(row["layoutSource"], "geometry")


if __name__ == "__main__":
    unittest.main()
