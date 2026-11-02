import queue
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

import checker_core as core

ROW_HEIGHT = 30
COL_WEIGHTS = {"server": 3, "srv_ip": 1.6, "proto": 0.8, "ip": 1.6, "dns": 0.9,
               "ttfb": 0.9, "total": 0.9, "http": 0.7, "geo": 0.6, "avail": 4}
COLS = list(COL_WEIGHTS)


def fmt(v):
    return "-" if v is None else f"{v:.0f}"


def row_values(r):
    return [r["server"], r["srv_ip"], r["proto"], r["ip"], fmt(r["dns"]), fmt(r["ttfb"]),
            fmt(r["total"]), "-" if r["http"] is None else str(r["http"]), r["geo"], r["avail"]]


COLOR_MAP = {
    "green": (0.72, 0.95, 0.72, 1),
    "yellow": (1.0, 0.95, 0.66, 1),
    "red": (0.96, 0.72, 0.72, 1),
    "pending": (0.9, 0.9, 0.9, 1),
}


class ResultRow(BoxLayout):
    def __init__(self, values, tag, **kw):
        super().__init__(**kw)
        self.size_hint_y = None
        self.height = ROW_HEIGHT
        self.padding = (dp(2), 0)
        self._bg = COLOR_MAP.get(tag, COLOR_MAP["pending"])
        for col, val in zip(COLS, values):
            lbl = Label(text=str(val), font_size="13sp", size_hint_x=COL_WEIGHTS[col],
                        color=(0, 0, 0, 1) if tag != "pending" else (0.4, 0.4, 0.4, 1))
            self.add_widget(lbl)
        self.redraw_bg()
        self.bind(pos=self.redraw_bg, size=self.redraw_bg)

    def redraw_bg(self, *a):
        from kivy.graphics import Color, Rectangle
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self._bg)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*COLOR_MAP[selftag()] if False else COLOR_MAP.get("yellow", (1, 1, 1, 1)))
            Rectangle(pos=self.pos, size=self.size)


class ResultsTable(ScrollView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.grid = GridLayout(cols=1, spacing=0, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.add_widget(self.grid)

        header = BoxLayout(size_hint_y=None, height=ROW_HEIGHT + 4, padding=(dp(2), 0))
        header_labels = ("DNS", "IP DNS", "Прот.", "IP ответа", "DNS ms", "TTFB ms",
                         "Σ ms", "HTTP", "Гео", "Доступность")
        for col, txt in zip(COLS, header_labels):
            header.add_widget(Label(text=txt, bold=True, size_hint_x=COL_WEIGHTS[col],
                                    font_size="14sp"))
        self.grid.add_widget(header)
        self.rows = {}

    def set_rows(self, items):
        self.grid.clear_widgets()
        for it in items:
            values, tag = it
            self.grid.add_widget(ResultRow(values, tag))
        if not items:
            lbl = Label(text="", size_hint_y=None, height=ROW_HEIGHT)
            self.grid.add_widget(lbl)


class DnsApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.title = f"DNS checker: {core.TARGET}"
        self.servers = core.load_server_list(core.DEFAULT_SERVERS_TEXT)
        self.done = []
        self.results = queue.Queue()
        self.stop = threading.Event()
        self.running = False
        self.clock_event = None

    def build(self):
        root = BoxLayout(orientation="vertical", padding=dp(4), spacing=dp(4))

        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.btn = Button(text="Старт", size_hint_x=None, width=dp(90))
        self.btn.bind(on_release=self.start)
        top.add_widget(self.btn)
        self.stop_btn = Button(text="Стоп", size_hint_x=None, width=dp(90), disabled=True)
        self.stop_btn.bind(on_release=self.halt)
        top.add_widget(self.stop_btn)
        top.add_widget(Label(text="IPv6 (AAAA)", size_hint_x=None, width=dp(90)))
        self.ipv6_cb = CheckBox(size_hint_x=None, width=dp(40))
        top.add_widget(self.ipv6_cb)
        self.status = Label(text=f"Серверов: {len(self.servers)}. Жми «Старт»")
        top.add_widget(self.status)
        root.add_widget(top)

        self.table = ResultsTable()
        root.add_widget(self.table)
        return root

    # --- запуск ---
    def start(self, *_):
        if not self.servers:
            self.status.text = "Список серверов пуст"
            return
        self.stop.set()
        self.stop = threading.Event()
        self.results = queue.Queue()
        self.done = []
        cfg = {"ipv6": self.ipv6_cb.active or False}
        jobs = queue.Queue()
        for s in self.servers:
            jobs.put(s)
        for _ in range(min(core.WORKERS, len(self.servers))):
            threading.Thread(target=core.worker, args=(jobs, self.results, self.stop, cfg),
                             daemon=True).start()
        self.running = True
        self.btn.disabled = True
        self.stop_btn.disabled = False
        self.render()
        self.clock_event = Clock.schedule_interval(self.poll, 0.15)

    def halt(self, *_):
        self.stop.set()
        self.finish(f"Остановлено: {len(self.done)}/{len(self.servers)}")

    def finish(self, text):
        self.running = False
        self.btn.disabled = False
        self.stop_btn.disabled = True
        self.status.text = text
        if self.clock_event:
            self.clock_event.cancel()
            self.clock_event = None

    def poll(self, dt):
        if not self.running:
            return False
        got = False
        while True:
            try:
                self.done.append(self.results.get_nowait())
                got = True
            except queue.Empty:
                break
        if got:
            self.render()
        if len(self.done) >= len(self.servers):
            ok = [r for r in self.done if r["ok"]]
            text = f"Готово: {len(self.servers)}/{len(self.servers)} | рабочих: {len(ok)}"
            if ok and all(r["geo"] == "?" for r in ok):
                text += " | гео не определено"
            self.finish(text)
            return False
        return True

    # --- отрисовка ---
    def render(self):
        ok = sorted((r for r in self.done if r["ok"]), key=lambda r: r["total"])
        groups = (("green", ok[:core.TOP_N]), ("yellow", ok[core.TOP_N:]),
                  ("red", [r for r in self.done if not r["ok"]]))
        items = []
        for g, rows in groups:
            items.extend((row_values(r), g) for r in rows)
        seen = {r["server"] for r in self.done}
        pending = "проверка..." if self.running else ""
        for s in self.servers:
            if s not in seen:
                items.append(((s, "-", "-", "-", "-", "-", "-", "-", "-", pending), "pending"))
        self.table.set_rows(items)
        ok_n = len(groups[0][1]) + len(groups[1][1])
        if self.running:
            self.status.text = (f"Проверка: {len(self.done)}/{len(self.servers)} | "
                                f"рабочих: {ok_n}, красных: {len(groups[2][1])}")


if __name__ == "__main__":
    DnsApp().run()