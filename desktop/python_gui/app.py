from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from urllib.request import Request, urlopen

API_BASE = 'http://127.0.0.1:8080'


def fetch_json(path: str, payload: dict | None = None):
    url = API_BASE + path
    data = None
    headers = {'Content-Type': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
    req = Request(url, data=data, headers=headers, method='POST' if payload is not None else 'GET')
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Text Watermark Studio Desktop')
        self.geometry('1180x760')
        self.configure(bg='#10151d')
        self._build()

    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        top = tk.Frame(self, bg='#10151d')
        top.pack(fill='x', padx=12, pady=12)
        tk.Label(top, text='Text Watermark Studio Desktop', font=('Segoe UI', 20, 'bold'), fg='white', bg='#10151d').pack(anchor='w')
        tk.Label(top, text='Cross-platform desktop GUI for the local API', fg='#aab7c7', bg='#10151d').pack(anchor='w')

        controls = tk.Frame(self, bg='#10151d')
        controls.pack(fill='x', padx=12)
        self.mode = tk.StringVar(value='pipeline')
        self.lang = tk.StringVar(value='auto')
        self.intensity = tk.StringVar(value='standard')
        self.api_base = tk.StringVar(value=API_BASE)
        ttk.Entry(controls, textvariable=self.api_base, width=42).grid(row=0, column=0, padx=6, pady=6, sticky='ew')
        ttk.Combobox(controls, textvariable=self.mode, values=['detect', 'clean', 'dilute', 'pipeline'], width=18).grid(row=0, column=1, padx=6, pady=6)
        ttk.Combobox(controls, textvariable=self.lang, values=['auto', 'de', 'en'], width=10).grid(row=0, column=2, padx=6, pady=6)
        ttk.Combobox(controls, textvariable=self.intensity, values=['light', 'standard', 'aggressive'], width=12).grid(row=0, column=3, padx=6, pady=6)
        ttk.Button(controls, text='Run', command=self.run_main).grid(row=0, column=4, padx=6, pady=6)
        ttk.Button(controls, text='Forensics', command=self.run_forensics).grid(row=0, column=5, padx=6, pady=6)
        ttk.Button(controls, text='Ops Status', command=self.run_ops).grid(row=0, column=6, padx=6, pady=6)
        ttk.Button(controls, text='Health', command=self.run_health).grid(row=0, column=7, padx=6, pady=6)
        controls.grid_columnconfigure(0, weight=1)

        body = tk.PanedWindow(self, orient='horizontal', sashwidth=8, bg='#10151d')
        body.pack(fill='both', expand=True, padx=12, pady=12)
        left = tk.Frame(body, bg='#10151d')
        right = tk.Frame(body, bg='#10151d')
        body.add(left, stretch='always')
        body.add(right, stretch='always')

        tk.Label(left, text='Input text', fg='white', bg='#10151d').pack(anchor='w')
        self.input_text = tk.Text(left, wrap='word', bg='#171d27', fg='white', insertbackground='white')
        self.input_text.pack(fill='both', expand=True)
        self.input_text.insert('1.0', 'Furthermore, this is a test text for local desktop usage.')

        tk.Label(right, text='Output', fg='white', bg='#10151d').pack(anchor='w')
        self.output_text = tk.Text(right, wrap='word', bg='#171d27', fg='#d8e1eb', insertbackground='white')
        self.output_text.pack(fill='both', expand=True)

    def set_output(self, value: str):
        self.output_text.delete('1.0', 'end')
        self.output_text.insert('1.0', value)

    def _async(self, fn):
        def runner():
            try:
                fn()
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror('Error', str(exc)))
        threading.Thread(target=runner, daemon=True).start()

    def run_main(self):
        def task():
            global API_BASE
            API_BASE = self.api_base.get().strip()
            payload = {'text': self.input_text.get('1.0', 'end').strip(), 'lang': self.lang.get(), 'intensity': self.intensity.get()}
            data = fetch_json('/api/' + self.mode.get(), payload)
            self.after(0, lambda: self.set_output(json.dumps(data, ensure_ascii=False, indent=2)))
        self._async(task)

    def run_forensics(self):
        def task():
            global API_BASE
            API_BASE = self.api_base.get().strip()
            payload = {'text': self.input_text.get('1.0', 'end').strip(), 'operator': 'desktop-user', 'window': 400}
            data = fetch_json('/api/forensics/detect', payload)
            self.after(0, lambda: self.set_output(json.dumps(data, ensure_ascii=False, indent=2)))
        self._async(task)

    def run_ops(self):
        def task():
            global API_BASE
            API_BASE = self.api_base.get().strip()
            data = fetch_json('/api/ops/status')
            self.after(0, lambda: self.set_output(json.dumps(data, ensure_ascii=False, indent=2)))
        self._async(task)

    def run_health(self):
        def task():
            global API_BASE
            API_BASE = self.api_base.get().strip()
            data = fetch_json('/health')
            self.after(0, lambda: self.set_output(json.dumps(data, ensure_ascii=False, indent=2)))
        self._async(task)


if __name__ == '__main__':
    App().mainloop()
