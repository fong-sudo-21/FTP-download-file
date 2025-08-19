#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FTP RAR Downloader (Tkinter) - Fixed & Improved
- Responsive UI (entries/buttons don't disappear when resizing)
- Remembers FTP settings & last folders in ~/.ftp_rar_gui.json
- Safer RAR extraction (path traversal guard)
- Better progress behavior (indeterminate when size unknown)
- Optional resume download if local file exists
- Fixed: format_size and format_date implemented and used in listing

Dependencies:
    pip install rarfile
System requirement:
    Install an UnRAR backend (unrar/unar/bsdtar). On Windows, install "UnRAR for Windows" and ensure 'unrar.exe' is in PATH.
"""
import os
import sys
import ftplib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import queue
import rarfile
import shutil
import time
import json
from datetime import datetime

APP_TITLE = "FTP RAR Downloader"
DEFAULT_PORT = 21
CONFIG_PATH = Path.home() / ".ftp_rar_gui.json"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class FTPClient:
    def __init__(self):
        self.ftp: ftplib.FTP | None = None
        self.current_path = "/"

    def connect(self, host: str, port: int, user: str, password: str, timeout: int = 20):
        self.close()
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=timeout)
        ftp.login(user=user, passwd=password)
        _ = ftp.getwelcome()
        ftp.voidcmd("TYPE I")
        self.ftp = ftp
        try:
            self.current_path = ftp.pwd()
        except Exception:
            self.current_path = "/"
        return True

    def close(self):
        if self.ftp is not None:
            try:
                self.ftp.quit()
            except Exception:
                try:
                    self.ftp.close()
                except Exception:
                    pass
            self.ftp = None

    def cwd(self, path: str):
        assert self.ftp is not None, "Not connected"
        self.ftp.cwd(path)
        self.current_path = self.ftp.pwd()

    def listdir(self, path: str = None):
        assert self.ftp is not None, "Not connected"
        if path is None:
            path = self.current_path
        entries = []
        try:
            for name, facts in self.ftp.mlsd(path):
                entries.append({
                    "name": name,
                    "type": facts.get("type", "file"),
                    "size": int(facts.get("size", 0)) if facts.get("size") else 0,
                    "modify": facts.get("modify", ""),
                })
        except (ftplib.error_perm, AttributeError):
            lines = []
            self.ftp.retrlines(f"LIST {path}", lines.append)
            for line in lines:
                parts = line.split(maxsplit=8)
                if len(parts) < 9:
                    name = parts[-1] if parts else line
                    entries.append({"name": name, "type": "file", "size": 0, "modify": ""})
                    continue
                mode, _, _, _, size, month, day, time_or_year, name = parts
                is_dir = mode.startswith("d")
                entries.append({
                    "name": name,
                    "type": "dir" if is_dir else "file",
                    "size": int(size) if size.isdigit() else 0,
                    "modify": f"{day} {month} {time_or_year}",
                })
        entries = [e for e in entries if e["name"] not in (".",)]
        dirs = [e for e in entries if e["type"] == "dir"]
        files = [e for e in entries if e["type"] != "dir"]
        dirs.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["name"].lower())
        return [{"name": "..", "type": "up", "size": 0, "modify": ""}] + dirs + files

    def download_file(self, remote_path: str, local_path: str, progress_cb=None, blocksize: int = 64*1024, rest: int = 0):
        assert self.ftp is not None, "Not connected"
        total_size = None
        try:
            total_size = self.ftp.size(remote_path)
        except Exception:
            pass

        mode = "ab" if rest > 0 else "wb"
        with open(local_path, mode) as f:
            bytes_done = rest
            def _writer(block):
                nonlocal bytes_done, total_size
                f.write(block)
                bytes_done += len(block)
                if progress_cb:
                    progress_cb(bytes_done, total_size)
            if rest > 0:
                self.ftp.retrbinary(f"RETR {remote_path}", _writer, blocksize=blocksize, rest=rest)
            else:
                self.ftp.retrbinary(f"RETR {remote_path}", _writer, blocksize=blocksize)

    @staticmethod
    def format_size(size: int) -> str:
        # size tính bằng byte
        try:
            size = float(size)
        except Exception:
            return ""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    @staticmethod
    def format_date(date_str: str) -> str:
        try:
            # Cắt bỏ phần mili-giây nếu có
            if "." in date_str:
                date_str = date_str.split(".")[0]
            dt = datetime.strptime(date_str, "%Y%m%d%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except:
            return date_str


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)

        # căn giữa cửa sổ chính khi mở
        self.center_window(1000, 680)

        # đổi icon app
        try:
            icon_path = Path(__file__).parent / "app.ico"
            if icon_path.exists():
                self.iconbitmap(default=icon_path)
        except Exception:
            # fallback dùng png
            try:
                icon_path = Path(__file__).parent / "app.png"
                if icon_path.exists():
                    self.iconphoto(False, tk.PhotoImage(file=icon_path))
            except:
                pass

        self.minsize(820, 560)
            
        self.ftp = FTPClient()
        self.bg_queue = queue.Queue()
        self.cfg = load_config()

        self._build_ui()
        self._poll_queue()

        # preload config
        self.host_var.set(self.cfg.get("host", ""))
        self.port_var.set(self.cfg.get("port", DEFAULT_PORT))
        self.user_var.set(self.cfg.get("user", "anonymous"))
        self.pass_var.set(self.cfg.get("password", ""))
        self.download_dir.set(self.cfg.get("download_dir", str(Path.home() / "Downloads")))
        self.extract_dir.set(self.cfg.get("extract_dir", str(Path.home() / "Downloads")))
        self.remember_var.set(bool(self.cfg.get("remember", True)))

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def center_window(self, width=800, height=600):
        """Căn giữa cửa sổ ứng dụng"""
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(width, height)  # chống resize quá nhỏ


    def _build_ui(self):
        # ===== Connection Frame (grid, responsive) =====
        conn = ttk.LabelFrame(self, text="Kết nối FTP")
        conn.pack(fill="x", padx=10, pady=10)

        self.host_var = tk.StringVar()
        self.port_var = tk.IntVar(value=DEFAULT_PORT)
        self.user_var = tk.StringVar(value="anonymous")
        self.pass_var = tk.StringVar(value="")
        self.remember_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Chưa kết nối")

        labels = [("Host", 0), ("Port", 2), ("User", 4), ("Password", 6)]
        for text, col in labels:
            ttk.Label(conn, text=text).grid(row=0, column=col, padx=5, pady=6, sticky="e")

        e_host = ttk.Entry(conn, textvariable=self.host_var)
        e_host.grid(row=0, column=1, padx=5, pady=6, sticky="ew")
        e_port = ttk.Entry(conn, textvariable=self.port_var, width=6)
        e_port.grid(row=0, column=3, padx=5, pady=6, sticky="ew")
        e_user = ttk.Entry(conn, textvariable=self.user_var)
        e_user.grid(row=0, column=5, padx=5, pady=6, sticky="ew")
        e_pass = ttk.Entry(conn, textvariable=self.pass_var, show="•")
        e_pass.grid(row=0, column=7, padx=5, pady=6, sticky="ew")

        self.btn_connect = ttk.Button(conn, text="Kết nối", command=self.on_connect)
        self.btn_connect.grid(row=0, column=8, padx=8, pady=6, sticky="ew")

        ttk.Checkbutton(conn, text="Nhớ thông tin", variable=self.remember_var).grid(row=0, column=9, padx=(5,10), pady=6, sticky="w")
        ttk.Label(conn, textvariable=self.status_var).grid(row=0, column=10, padx=5, pady=6, sticky="w")

        # Configure responsive columns
        for i in range(11):
            weight = 1 if i in (1,5,7,10) else (0 if i in (3,8,9) else 0)
            conn.grid_columnconfigure(i, weight=weight)
        conn.grid_columnconfigure(1, weight=2)
        conn.grid_columnconfigure(5, weight=1)
        conn.grid_columnconfigure(7, weight=1)
        conn.grid_columnconfigure(10, weight=2)

        # ===== Remote Browser =====
        browser = ttk.LabelFrame(self, text="Trình duyệt FTP (chọn file .rar)")
        browser.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("name", "type", "size", "modify")
        self.tree = ttk.Treeview(browser, columns=columns, show="headings")
        self.tree.heading("name", text="Tên")
        self.tree.heading("type", text="Loại")
        # Đổi tiêu đề cột size vì sẽ hiển thị dạng KB/MB
        self.tree.heading("size", text="Kích thước")
        self.tree.heading("modify", text="Sửa đổi")
        self.tree.column("name", width=320, anchor="w")
        self.tree.column("type", width=90, anchor="center")
        self.tree.column("size", width=150, anchor="e")
        self.tree.column("modify", width=160, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True, padx=(10,0), pady=10)

        vsb = ttk.Scrollbar(browser, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="left", fill="y", padx=(0,10), pady=10)

        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        right = ttk.Frame(browser)
        right.pack(side="left", fill="y", padx=10, pady=10)

        self.lbl_pwd = ttk.Label(right, text="Đường dẫn hiện tại: /", wraplength=260, justify="left")
        self.lbl_pwd.pack(anchor="w", pady=(0,8))

        self.btn_refresh = ttk.Button(right, text="Làm mới", command=self.refresh_listing, state="disabled")
        self.btn_refresh.pack(fill="x")

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=10)

        self.download_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.extract_dir = tk.StringVar(value=str(Path.home() / "Downloads"))

        ttk.Label(right, text="Thư mục tải về").pack(anchor="w")
        row = ttk.Frame(right); row.pack(fill="x", pady=2)
        ttk.Entry(row, textvariable=self.download_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn...", command=self.choose_download_dir).pack(side="left", padx=5)

        ttk.Label(right, text="Thư mục giải nén").pack(anchor="w", pady=(8,0))
        row2 = ttk.Frame(right); row2.pack(fill="x", pady=2)
        ttk.Entry(row2, textvariable=self.extract_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Chọn...", command=self.choose_extract_dir).pack(side="left", padx=5)

        self.overwrite_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(right, text="Ghi đè nếu trùng file / folder", variable=self.overwrite_var).pack(anchor="w", pady=8)

        self.selected_remote = tk.StringVar(value="")
        self.lbl_selected = ttk.Label(right, text="Chưa chọn file .rar", wraplength=260, justify="left")
        self.lbl_selected.pack(anchor="w", pady=(10,6))

        self.progress = ttk.Progressbar(right, orient="horizontal", mode="determinate", length=220)
        self.progress.pack(fill="x")

        self.btn_download = ttk.Button(right, text="Tải về & Giải nén", command=self.on_download_extract, state="disabled")
        self.btn_download.pack(fill="x", pady=(10,0))

        self.log_text = tk.Text(self, height=7, state="disabled")
        self.log_text.pack(fill="x", padx=10, pady=(0,10))

        self._set_state_connected(False)

    def log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_state_connected(self, connected: bool):
        self.btn_refresh.config(state="normal" if connected else "disabled")
        if connected:
            self.status_var.set(f"Đã kết nối: {self.ftp.current_path}")
        else:
            self.status_var.set("Chưa kết nối")

    def on_connect(self):
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get() or DEFAULT_PORT)
        except Exception:
            port = DEFAULT_PORT
            self.port_var.set(DEFAULT_PORT)
        user = self.user_var.get()
        password = self.pass_var.get()

        if not host:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập Host.")
            return

        def worker():
            try:
                self.log(f"Kết nối tới {host}:{port} ...")
                self.ftp.connect(host, port, user, password)
                if self.remember_var.get():
                    self.cfg.update({
                        "host": host, "port": port, "user": user, "password": password,
                        "download_dir": self.download_dir.get(),
                        "extract_dir": self.extract_dir.get(),
                        "remember": True
                    })
                    save_config(self.cfg)
                self.bg_queue.put(("connected", None))
                self.log("Kết nối thành công.")
                self.refresh_listing()
            except Exception as e:
                self.bg_queue.put(("error", f"Lỗi kết nối: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_listing(self):
        def worker():
            try:
                entries = self.ftp.listdir()
                self.bg_queue.put(("listing", entries))
            except Exception as e:
                self.bg_queue.put(("error", f"Lỗi liệt kê: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def on_tree_double_click(self, event=None):
        item_id = self.tree.focus()
        if not item_id:
            return
        item = self.tree.item(item_id)
        name, typ = item["values"][0], item["values"][1]
        if typ in ("dir", "up"):
            def worker():
                try:
                    if typ == "up":
                        cur = self.ftp.current_path
                        parent = "/" if cur == "/" else os.path.dirname(cur.rstrip("/"))
                        if not parent:
                            parent = "/"
                        self.ftp.cwd(parent)
                    else:
                        self.ftp.cwd(os.path.join(self.ftp.current_path, name).replace("\\", "/"))
                    entries = self.ftp.listdir()
                    self.bg_queue.put(("listing", entries))
                except Exception as e:
                    self.bg_queue.put(("error", f"Không thể chuyển thư mục: {e}"))
            threading.Thread(target=worker, daemon=True).start()

    def on_tree_select(self, event=None):
        sel = self.tree.selection()
        path = ""
        enable = False
        if sel:
            item = self.tree.item(sel[0])
            name, typ = item["values"][0], item["values"][1]
            if typ == "file" and name.lower().endswith(".rar"):
                path = os.path.join(self.ftp.current_path, name).replace("\\", "/")
                enable = True
        self.selected_remote.set(path)
        if path:
            self.lbl_selected.config(text=f"Đã chọn: {path}")
        else:
            self.lbl_selected.config(text="Chưa chọn file .rar")
        self.btn_download.config(state="normal" if enable else "disabled")

    def choose_download_dir(self):
        d = filedialog.askdirectory(title="Chọn thư mục tải về", initialdir=self.download_dir.get())
        if d:
            self.download_dir.set(d)

    def choose_extract_dir(self):
        d = filedialog.askdirectory(title="Chọn thư mục giải nén", initialdir=self.extract_dir.get())
        if d:
            self.extract_dir.set(d)

    def on_download_extract(self):
        remote_path = self.selected_remote.get()
        if not remote_path:
            messagebox.showinfo("Chọn file", "Hãy chọn một file .rar trước.")
            return
        dl_dir = Path(self.download_dir.get()).expanduser()
        ex_dir = Path(self.extract_dir.get()).expanduser()
        dl_dir.mkdir(parents=True, exist_ok=True)
        ex_dir.mkdir(parents=True, exist_ok=True)

        local_path = dl_dir / Path(remote_path).name
        overwrite = self.overwrite_var.get()

        # Resume option if file exists
        rest = 0
        if local_path.exists():
            ans = messagebox.askyesnocancel("Tệp đã tồn tại",
                                            "Tệp đã tồn tại.\nYes: Tiếp tục tải (resume)\nNo: Tải lại từ đầu (ghi đè)\nCancel: Hủy")
            if ans is None:
                return
            if ans is True:
                rest = local_path.stat().st_size
            else:
                try:
                    local_path.unlink()
                except Exception:
                    pass
                rest = 0

        # Start progress
        self.progress.configure(mode="indeterminate" if rest == 0 else "determinate", value=0, maximum=100)
        if self.progress["mode"] == "indeterminate":
            self.progress.start(100)
        self.btn_download.configure(state="disabled")

        def worker():
            try:
                self.log(f"Tải xuống: {remote_path} -> {local_path}")
                def prog(done, total):
                    # Switch to determinate if total known
                    if total and total > 0:
                        if self.progress["mode"] != "determinate":
                            self.bg_queue.put(("progress_mode", "determinate"))
                        pct = int(done * 100 / total)
                        self.bg_queue.put(("progress", pct))
                self.ftp.download_file(remote_path, str(local_path), progress_cb=prog, rest=rest)

                self.bg_queue.put(("progress", 100))
                self.log("Tải xong. Bắt đầu giải nén...")
                self._extract_rar(local_path, ex_dir, overwrite)
                self.bg_queue.put(("done", f"Hoàn tất: Đã tải và giải nén vào {ex_dir}"))
            except rarfile.NeedFirstVolume:
                self.bg_queue.put(("error", "Tập tin là RAR nhiều phần. Hãy tải đủ các phần (chọn *.part1.rar hoặc .rar đầu tiên)."))
            except rarfile.RarCannotExec:
                self.bg_queue.put(("error", "Không tìm thấy chương trình giải nén (unrar/unar/bsdtar). Hãy cài đặt và thêm vào PATH."))
            except Exception as e:
                self.bg_queue.put(("error", f"Lỗi: {e}"))
            finally:
                self.bg_queue.put(("enable_download", None))

        threading.Thread(target=worker, daemon=True).start()

    def _extract_rar(self, rar_path: Path, dest_dir: Path, overwrite: bool):
        with rarfile.RarFile(rar_path) as rf:
            for m in rf.infolist():
                name_posix = Path(m.filename).as_posix().lstrip("/")
                target = dest_dir / name_posix
                # Guard against path traversal
                try:
                    target_resolved_parent = (target.parent if m.is_dir() else target).resolve().parent
                except FileNotFoundError:
                    target_resolved_parent = target.parent.resolve()
                if not str(target_resolved_parent).startswith(str(dest_dir.resolve())):
                    raise Exception(f"Unsafe path in archive: {m.filename}")
                if m.is_dir():
                    (dest_dir / name_posix).mkdir(parents=True, exist_ok=True)
                    continue
                # Ensure parent
                (dest_dir / name_posix).parent.mkdir(parents=True, exist_ok=True)
                # Overwrite logic
                target_file = dest_dir / name_posix
                if target_file.exists() and overwrite:
                    try:
                        if target_file.is_file():
                            target_file.unlink()
                        else:
                            shutil.rmtree(target_file)
                    except Exception:
                        pass
                if (not target_file.exists()) or overwrite:
                    # Extract (rarfile will honor member path relative to 'path')
                    rf.extract(m, path=dest_dir)

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.bg_queue.get_nowait()
                if kind == "connected":
                    self._set_state_connected(True)
                    self.lbl_pwd.config(text=f"Đường dẫn hiện tại: {self.ftp.current_path}")
                elif kind == "listing":
                    for i in self.tree.get_children():
                        self.tree.delete(i)
                    for e in payload:
                        size_str = FTPClient.format_size(e.get("size", 0)) if e.get("size") else ""
                        date_str = FTPClient.format_date(e.get("modify", "")) if e.get("modify") else ""
                        self.tree.insert("", "end", values=(e["name"], e["type"], size_str, date_str))
                    self.lbl_pwd.config(text=f"Đường dẫn hiện tại: {self.ftp.current_path}")
                elif kind == "progress_mode":
                    # switch from indeterminate to determinate
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0, maximum=100)
                elif kind == "progress":
                    self.progress.configure(value=int(payload))
                elif kind == "done":
                    self.progress.stop()
                    self.progress.configure(value=100)
                    self.log(str(payload))
                    messagebox.showinfo("Hoàn tất", str(payload))
                elif kind == "enable_download":
                    self.on_tree_select()
                elif kind == "error":
                    self.progress.stop()
                    self.log(str(payload))
                    messagebox.showerror("Lỗi", str(payload))
                else:
                    pass
        except queue.Empty:
            pass
        finally:
            self.after(120, self._poll_queue)

    def on_close(self):
        try:
            if self.remember_var.get():
                self.cfg.update({
                    "host": self.host_var.get().strip(),
                    "port": int(self.port_var.get() or DEFAULT_PORT),
                    "user": self.user_var.get(),
                    "password": self.pass_var.get(),
                    "download_dir": self.download_dir.get(),
                    "extract_dir": self.extract_dir.get(),
                    "remember": True
                })
                save_config(self.cfg)
        except Exception:
            pass
        try:
            self.ftp.close()
        except Exception:
            pass
        self.destroy()


def main():
    root = App()
    root.mainloop()


if __name__ == "__main__":
    main()
