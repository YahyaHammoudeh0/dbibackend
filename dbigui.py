#!/usr/bin/env python3
"""Simple desktop GUI for dbibackend — install Switch titles over USB with DBI.

No Terminal required. Pick a folder of .nsp/.nsz/.xci files, press Start, then
run DBI ▸ Install title from USB on the console.
"""
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog

# Allow running both from source (repo root) and from a PyInstaller bundle.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbibackend.dbibackend import run_server  # noqa: E402

APP_NAME = 'DBI Backend'
CONFIG_DIR = os.path.expanduser('~/Library/Application Support/DBIBackend')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f)
    except Exception:
        pass


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.server_thread = None
        self._stop = threading.Event()

        cfg = load_config()
        self.titles_dir = tk.StringVar(value=cfg.get('titles_dir', ''))

        root.title(APP_NAME)
        root.minsize(560, 460)

        self._build_ui()
        self.root.after(80, self._drain_events)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ---------- UI ----------
    def _build_ui(self):
        pad = dict(padx=12, pady=6)
        main = ttk.Frame(self.root)
        main.pack(fill='both', expand=True)

        header = ttk.Label(main, text='Install Switch titles over USB', font=('', 15, 'bold'))
        header.pack(anchor='w', **pad)

        # Folder row
        folder_row = ttk.Frame(main)
        folder_row.pack(fill='x', **pad)
        ttk.Label(folder_row, text='Titles folder:').pack(side='left')
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.titles_dir)
        self.folder_entry.pack(side='left', fill='x', expand=True, padx=(8, 8))
        self.browse_btn = ttk.Button(folder_row, text='Choose…', command=self._choose_folder)
        self.browse_btn.pack(side='left')

        # Start / Stop
        control_row = ttk.Frame(main)
        control_row.pack(fill='x', **pad)
        self.start_btn = ttk.Button(control_row, text='▶  Start server', command=self._toggle)
        self.start_btn.pack(side='left')
        self.status = ttk.Label(control_row, text='Idle', foreground='#666')
        self.status.pack(side='left', padx=12)

        # Progress
        prog_row = ttk.Frame(main)
        prog_row.pack(fill='x', **pad)
        self.progress = ttk.Progressbar(prog_row, mode='determinate', maximum=1000)
        self.progress.pack(fill='x')
        self.progress_label = ttk.Label(main, text='', foreground='#666')
        self.progress_label.pack(anchor='w', padx=12)

        # Log
        ttk.Label(main, text='Log').pack(anchor='w', padx=12, pady=(8, 0))
        log_frame = ttk.Frame(main)
        log_frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(log_frame, height=12, wrap='word', state='disabled',
                           background='#111', foreground='#ddd', insertbackground='#ddd')
        self.log.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scroll.set)

    # ---------- actions ----------
    def _choose_folder(self):
        initial = self.titles_dir.get() or os.path.expanduser('~')
        chosen = filedialog.askdirectory(initialdir=initial, title='Choose folder with .nsp / .nsz / .xci files')
        if chosen:
            self.titles_dir.set(chosen)
            save_config({'titles_dir': chosen})

    def _toggle(self):
        if self.server_thread and self.server_thread.is_alive():
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        path = self.titles_dir.get().strip()
        if not path or not os.path.isdir(path):
            self._log('Please choose a valid titles folder first.')
            self._set_status('No folder selected', '#c0392b')
            return
        save_config({'titles_dir': path})
        self._stop.clear()
        self.progress['value'] = 0
        self.progress_label['text'] = ''
        self._log(f'Starting server on: {path}')
        self.start_btn['text'] = '■  Stop server'
        self.browse_btn['state'] = 'disabled'
        self.folder_entry['state'] = 'disabled'

        def worker():
            try:
                run_server(path, should_stop=self._stop.is_set, on_event=self.events.put)
            except Exception as e:  # noqa: BLE001 — surface any startup error to the UI
                self.events.put({'type': 'error', 'text': str(e)})
            finally:
                self.events.put({'type': 'stopped'})

        self.server_thread = threading.Thread(target=worker, daemon=True)
        self.server_thread.start()

    def _stop_server(self):
        self._log('Stopping…')
        self._set_status('Stopping…', '#666')
        self._stop.set()

    # ---------- event pump (runs on the Tk thread) ----------
    def _drain_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _handle(self, ev):
        kind = ev.get('type')
        if kind == 'status':
            self._set_status(ev['text'], '#2c7')
            self._log(ev['text'])
        elif kind == 'list':
            n = ev.get('count', 0)
            self._log(f'DBI requested list — {n} title(s) available')
            if n == 0:
                self._log('  (folder has no .nsp/.nsz/.xci files)')
        elif kind == 'transfer_start':
            self.progress['value'] = 0
            self._set_status(f'Installing {ev["name"]}', '#2c7')
            self._log(f'Installing {ev["name"]} ({human_size(ev["total"])})')
        elif kind == 'transfer_progress':
            total = max(1, ev['total'])
            frac = ev['done'] / total
            self.progress['value'] = frac * 1000
            self.progress_label['text'] = f'{ev["name"]}  —  {human_size(ev["done"])} / {human_size(total)}  ({frac*100:.0f}%)'
        elif kind == 'transfer_done':
            self.progress['value'] = 1000
            self._log(f'Finished sending {ev["name"]}')
            self.progress_label['text'] = f'{ev["name"]} — done'
        elif kind == 'error':
            self._set_status('Error', '#c0392b')
            self._log(f'ERROR: {ev["text"]}')
        elif kind == 'stopped':
            self._on_stopped()

    def _on_stopped(self):
        self.start_btn['text'] = '▶  Start server'
        self.browse_btn['state'] = 'normal'
        self.folder_entry['state'] = 'normal'
        self._set_status('Idle', '#666')

    # ---------- helpers ----------
    def _set_status(self, text, color='#666'):
        self.status['text'] = text
        self.status['foreground'] = color

    def _log(self, msg):
        self.log['state'] = 'normal'
        self.log.insert('end', msg + '\n')
        self.log.see('end')
        self.log['state'] = 'disabled'

    def _on_close(self):
        self._stop.set()
        self.root.after(150, self.root.destroy)


def main():
    if '--selftest' in sys.argv:
        # Headless check that the bundled libusb backend loads.
        from dbibackend.dbibackend import get_libusb_backend
        backend = get_libusb_backend()
        print(f'selftest ok: backend={backend}, meipass={getattr(sys, "_MEIPASS", None)}')
        return

    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.4)
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
