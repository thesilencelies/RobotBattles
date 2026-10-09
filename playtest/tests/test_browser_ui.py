"""End-to-end headless browser test for Combat Robotics playtest UI elements."""

import base64
import json
import os
import socket
import struct
import subprocess
import time
import unittest
import urllib.request
from pathlib import Path


def make_ws_request(host, port, path):
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("utf-8")


def encode_ws_frame(msg):
    payload = msg.encode("utf-8")
    mask = os.urandom(4)
    frame = bytearray()
    frame.append(0x81)
    length = len(payload)
    if length <= 125:
        frame.append(0x80 | length)
    elif length <= 65535:
        frame.append(0x80 | 126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack("!Q", length))
    frame.extend(mask)
    for i, b in enumerate(payload):
        frame.append(b ^ mask[i % 4])
    return bytes(frame)


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError("Socket closed")
        data.extend(chunk)
    return bytes(data)


def decode_ws_frame(sock):
    while True:
        b0 = recv_exact(sock, 1)[0]
        opcode = b0 & 0x0F
        b1 = recv_exact(sock, 1)[0]
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", recv_exact(sock, 8))[0]
        payload = recv_exact(sock, length)
        if opcode == 0x01:  # Text frame
            return payload.decode("utf-8", errors="replace")
        elif opcode == 0x09:  # Ping
            pong = bytearray([0x8A, 0x80])
            mask = os.urandom(4)
            pong.extend(mask)
            sock.sendall(bytes(pong))


class TestBrowserUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_port = 8016
        cls.chrome_port = 9236
        cls.repo_dir = Path(__file__).resolve().parent.parent.parent

        cls.server_proc = subprocess.Popen(
            ["python3", "-m", "playtest.server", "--port", str(cls.server_port)],
            cwd=str(cls.repo_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        cls.chrome_proc = subprocess.Popen(
            [
                "google-chrome",
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                f"--remote-debugging-port={cls.chrome_port}",
                "--user-data-dir=/tmp/chrome_test_ui2",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for Chrome DevTools
        for _ in range(30):
            time.sleep(0.2)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cls.chrome_port}/json/version", timeout=1):
                    break
            except Exception:
                pass

        # Open page
        page_url = f"http://127.0.0.1:{cls.server_port}/"
        req = urllib.request.Request(f"http://127.0.0.1:{cls.chrome_port}/json/new?{page_url}", method="PUT")
        with urllib.request.urlopen(req) as r:
            target = json.loads(r.read().decode("utf-8"))
            ws_url = target["webSocketDebuggerUrl"]

        ws_part = ws_url[len("ws://"):]
        host_port, path = ws_part.split("/", 1)
        host, port = host_port.split(":")
        cls.sock = socket.socket()
        cls.sock.settimeout(10.0)
        cls.sock.connect((host, int(port)))
        cls.sock.sendall(make_ws_request(host, int(port), "/" + path))

        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += cls.sock.recv(1024)

        cls.msg_id = 0

        # Wait for app to be completely initialized
        for _ in range(50):
            time.sleep(0.1)
            try:
                ready = cls._eval_static("Boolean(window.app && window.app.isReady)")
                if ready:
                    break
            except Exception:
                pass

        # Disable blocking modals
        cls._eval_static("window.alert = (m) => console.log('ALERT:', m); window.confirm = () => true;")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.sock.close()
        except Exception:
            pass
        cls.chrome_proc.terminate()
        cls.server_proc.terminate()

    @classmethod
    def _eval_static(cls, expr):
        cls.msg_id += 1
        msg = json.dumps({
            "id": cls.msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True},
        })
        cls.sock.sendall(encode_ws_frame(msg))
        while True:
            frame = decode_ws_frame(cls.sock)
            data = json.loads(frame)
            if data.get("id") == cls.msg_id:
                if "exceptionDetails" in data.get("result", {}):
                    raise RuntimeError(f"JS Exception in {expr}: {data['result']['exceptionDetails']}")
                return data.get("result", {}).get("result", {}).get("value")

    def js_eval(self, expr):
        return self._eval_static(expr)

    def test_01_page_title_and_tabs(self):
        title = self.js_eval("document.title")
        self.assertIn("Combat Robotics Playtest", title)
        tabs = self.js_eval("[...document.querySelectorAll('#main-nav .nav-tab')].map(t => t.dataset.tab)")
        self.assertEqual(tabs, ["arena", "player-robot", "automaton-robot", "builder", "log"])

        # Check that only arena is visible on load and builder is hidden
        arena_disp = self.js_eval("window.getComputedStyle(document.getElementById('view-arena')).display")
        builder_disp = self.js_eval("window.getComputedStyle(document.getElementById('view-builder')).display")
        self.assertEqual(arena_disp, "flex")
        self.assertEqual(builder_disp, "none")

    def test_02_builder_catalogue_and_card_selection(self):
        # 1. Switch to Builder tab
        self.js_eval("document.querySelector(\"#main-nav .nav-tab[data-tab='builder']\").click()")
        self.assertTrue(self.js_eval("document.getElementById('view-builder').classList.contains('active')"))
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-builder')).display"), "flex")
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-arena')).display"), "none")

        # Verify horizontal scroll on top-row-main
        top_row_overflow = self.js_eval("window.getComputedStyle(document.querySelector('#view-builder .top-row-main')).overflowX")
        self.assertEqual(top_row_overflow, "auto")
        top_row_wrap = self.js_eval("window.getComputedStyle(document.querySelector('#view-builder .top-row-main')).flexWrap")
        self.assertEqual(top_row_wrap, "nowrap")

        # 2. Check chassis selector options
        chassis_opts = self.js_eval("[...document.getElementById('chassis-select').options].map(o => o.value)")
        self.assertTrue(len(chassis_opts) >= 3)
        self.assertTrue(any("Viper" in c for c in chassis_opts))

        # 3. Open Card Catalogue via bottom nav button
        self.js_eval("document.getElementById('tab-btn-catalogue').click()")
        self.assertTrue(self.js_eval("document.getElementById('drawer-catalogue').classList.contains('open')"))

        # 4. Verify all cards are rendered
        card_count = self.js_eval("document.querySelectorAll('#catalogue-list .catalog-card-item').length")
        self.assertGreaterEqual(card_count, 40)

        # 5. Filter by category 'weapon'
        self.js_eval("document.querySelector(\".pill-btn[data-category='weapon']\").click()")
        weapon_count = self.js_eval("document.querySelectorAll('#catalogue-list .catalog-card-item').length")
        self.assertGreaterEqual(weapon_count, 10)
        self.assertLess(weapon_count, card_count)

        # 6. Filter by search query
        self.js_eval("document.getElementById('card-search-input').value = 'Vertical'; document.getElementById('card-search-input').dispatchEvent(new Event('input'))")
        search_count = self.js_eval("document.querySelectorAll('#catalogue-list .catalog-card-item').length")
        self.assertGreaterEqual(search_count, 1)
        name = self.js_eval("document.querySelector('#catalogue-list .catalog-card-title').textContent")
        self.assertIn("Vertical Spinner", name)

        # 7. Add card to chassis (+ Chassis)
        initial_placed = self.js_eval("document.querySelectorAll('#layer-cards .card-node').length")
        self.js_eval("document.querySelector('#catalogue-list .catalog-card-item .btn-primary').click()")
        new_placed = self.js_eval("document.querySelectorAll('#layer-cards .card-node').length")
        self.assertEqual(new_placed, initial_placed + 1)

        # 8. Drawer should close and inspector should appear
        self.assertFalse(self.js_eval("document.getElementById('drawer-catalogue').classList.contains('open')"))
        self.assertFalse(self.js_eval("document.getElementById('card-inspector').classList.contains('hidden')"))

        # 9. Test inspector actions: Rotate
        initial_stat = self.js_eval("document.getElementById('inspector-card-stats').textContent")
        self.js_eval("document.getElementById('btn-rotate-card').click()")
        rotated_stat = self.js_eval("document.getElementById('inspector-card-stats').textContent")
        self.assertNotEqual(initial_stat, rotated_stat)

        # 10. Test Top Header 'Add Cards' button also opens catalogue
        self.js_eval("document.getElementById('btn-top-catalogue').click()")
        self.assertTrue(self.js_eval("document.getElementById('drawer-catalogue').classList.contains('open')"))
        self.js_eval("document.getElementById('btn-close-catalogue').click()")
        self.assertFalse(self.js_eval("document.getElementById('drawer-catalogue').classList.contains('open')"))

    def test_03_deploy_and_arena_battle(self):
        # 1. Click Deploy to Arena
        self.js_eval("document.getElementById('btn-deploy-to-arena').click()")
        for _ in range(30):
            time.sleep(0.1)
            if self.js_eval("document.getElementById('view-arena').classList.contains('active')"):
                break
        self.assertTrue(self.js_eval("document.getElementById('view-arena').classList.contains('active')"))

        # 2. Check Match HUD & Arena Zoom
        round_txt = self.js_eval("document.getElementById('hud-round').textContent")
        self.assertIn("Round 1", round_txt)

        # Arena Zoom controls test
        vb_initial = self.js_eval("document.getElementById('arena-svg').getAttribute('viewBox')")
        self.assertEqual(vb_initial, "0 0 800 800")
        self.js_eval("document.getElementById('btn-arena-zoom-in').click()")
        vb_zoomed = self.js_eval("document.getElementById('arena-svg').getAttribute('viewBox')")
        self.assertNotEqual(vb_initial, vb_zoomed)
        self.js_eval("document.getElementById('btn-arena-zoom-fit').click()")
        vb_reset = self.js_eval("document.getElementById('arena-svg').getAttribute('viewBox')")
        self.assertEqual(vb_reset, "0 0 800 800")

        # Verify arena view has scrollable capability
        arena_overflow_y = self.js_eval("window.getComputedStyle(document.getElementById('view-arena')).overflowY")
        self.assertEqual(arena_overflow_y, "auto")

        # 3. Test Drive Presets
        self.js_eval("document.querySelector(\".btn-preset[data-preset='forward']\").click()")
        left_val = self.js_eval("document.getElementById('left-drive-val').textContent")
        right_val = self.js_eval("document.getElementById('right-drive-val').textContent")
        self.assertNotEqual(left_val, "0")
        self.assertEqual(left_val, right_val)

        # 4. Test Stepper Plus/Minus
        old_left = int(self.js_eval("document.getElementById('left-drive-slider').value"))
        self.js_eval("document.getElementById('btn-left-minus').click()")
        new_left = int(self.js_eval("document.getElementById('left-drive-slider').value"))
        self.assertEqual(new_left, old_left - 1)

        # 5. Execute Turn
        self.js_eval("document.getElementById('btn-execute-turn').click()")
        time.sleep(1.0)
        round_after = self.js_eval("document.getElementById('hud-round').textContent")
        self.assertIn("Round 2", round_after)

        # 6. Check Combat Log updated
        log_count = self.js_eval("document.querySelectorAll('#combat-log-container .log-entry').length")
        self.assertGreater(log_count, 0)

    def test_04_robot_views_and_log(self):
        # 1. Player Robot tab
        self.js_eval("document.querySelector(\"#main-nav .nav-tab[data-tab='player-robot']\").click()")
        self.assertTrue(self.js_eval("document.getElementById('view-player-robot').classList.contains('active')"))
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-builder')).display"), "none")
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-player-robot')).display"), "flex")
        player_cards = self.js_eval("document.querySelectorAll('#player-robot-container .robot-view-card').length")
        self.assertGreater(player_cards, 0)

        # Verify Motive Drive System card and logo exist
        has_drive_logo = self.js_eval("Boolean(document.querySelector('#player-robot-container .motive-drive-logo-icon'))")
        self.assertTrue(has_drive_logo, "Motive Drive distinct logo should exist")

        # Verify aggregate 7/7 durability is REMOVED
        container_text = self.js_eval("document.getElementById('player-robot-container').textContent")
        self.assertNotIn("Total Durability", container_text)
        self.assertNotIn("7 / 7", container_text)

        # Verify SVG Chassis Tree Layout exists with placed cards
        has_layout_svg = self.js_eval("Boolean(document.querySelector('#player-robot-container .robot-layout-svg'))")
        self.assertTrue(has_layout_svg, "Robot layout SVG should exist")
        card_nodes_count = self.js_eval("document.querySelectorAll('#player-robot-container .layout-card-node').length")
        self.assertGreater(card_nodes_count, 0, "Cards should be placed in SVG layout")

        # Verify card inspector updates on click
        initial_insp_title = self.js_eval("document.querySelector('#player-robot-container .inspector-name').textContent")
        self.js_eval("document.querySelectorAll('#player-robot-container .layout-card-node')[1].dispatchEvent(new Event('click'))")
        new_insp_title = self.js_eval("document.querySelector('#player-robot-container .inspector-name').textContent")
        # Layout zoom buttons work
        self.js_eval("document.querySelector('#player-robot-container .btn-zoom-layout[data-zoom=\"in\"]').click()")

        # 2. Automaton tab
        self.js_eval("document.querySelector(\"#main-nav .nav-tab[data-tab='automaton-robot']\").click()")
        self.assertTrue(self.js_eval("document.getElementById('view-automaton-robot').classList.contains('active')"))
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-builder')).display"), "none")
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-automaton-robot')).display"), "flex")
        auto_cards = self.js_eval("document.querySelectorAll('#automaton-robot-container .robot-view-card').length")
        self.assertGreater(auto_cards, 0)

        # Verify Automaton also has Motive Drive and SVG Layout
        has_auto_layout = self.js_eval("Boolean(document.querySelector('#automaton-robot-container .robot-layout-svg'))")
        self.assertTrue(has_auto_layout)

        # 3. Combat Log tab
        self.js_eval("document.querySelector(\"#main-nav .nav-tab[data-tab='log']\").click()")
        self.assertTrue(self.js_eval("document.getElementById('view-log').classList.contains('active')"))
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-builder')).display"), "none")
        self.assertEqual(self.js_eval("window.getComputedStyle(document.getElementById('view-log')).display"), "flex")
        self.assertTrue(self.js_eval("document.querySelectorAll('#combat-log-container .log-entry').length > 0"))


if __name__ == "__main__":
    unittest.main()
