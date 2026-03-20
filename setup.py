import os
import sys
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import time

# --- Configuration ---
APP_NAME = "KICE Lynx"
DEFAULT_INSTALL_DIR = os.path.join("C:\\", APP_NAME)
ICON_NAME = "icon.ico"

class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} 설치")
        self.root.geometry("500x350")
        self.root.resizable(False, False)
        
        # Colors & Fonts
        self.bg_color = "#f8fafc"
        self.accent_color = "#06b6d4"
        self.text_color = "#1e293b"
        self.root.configure(bg=self.bg_color)
        
        # Pre-initialize for linter
        self.path_var = None
        self.path_entry = None
        self.progress = None
        self.install_btn = None
        
        self.create_widgets()
        
    def create_widgets(self):
        # Header
        header = tk.Label(self.root, text=f"{APP_NAME} 설치", font=("Malgun Gothic", 20, "bold"), 
                         bg=self.bg_color, fg=self.accent_color)
        header.pack(pady=(30, 10))
        
        sub_text = tk.Label(self.root, text="KICE Lynx를 컴퓨터에 설치합니다.\n보관할 위치를 선택해 주세요.", 
                           font=("Malgun Gothic", 10), bg=self.bg_color, fg="#64748b")
        sub_text.pack(pady=(0, 25))
        
        # Path Selection
        path_frame = tk.Frame(self.root, bg=self.bg_color)
        path_frame.pack(pady=10, px=20, fill="x")
        
        self.path_var = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.path_entry = tk.Entry(path_frame, textvariable=self.path_var, font=("Malgun Gothic", 10), 
                                  relief="solid", bd=1)
        self.path_entry.pack(side="left", padx=(20, 5), pady=5, fill="x", expand=True)
        
        browse_btn = tk.Button(path_frame, text="찾아보기...", command=self.browse_path, 
                              font=("Malgun Gothic", 9), bg="#e2e8f0", relief="flat")
        browse_btn.pack(side="right", padx=(5, 20), pady=5)
        
        # Progress Bar (Hidden initially)
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        
        # Footer Buttons
        btn_frame = tk.Frame(self.root, bg=self.bg_color)
        btn_frame.pack(side="bottom", pady=30)
        
        self.install_btn = tk.Button(btn_frame, text="설치 시작", command=self.start_installation, 
                                   font=("Malgun Gothic", 11, "bold"), bg=self.accent_color, 
                                   fg="white", padx=30, pady=8, relief="flat", cursor="hand2")
        self.install_btn.pack()
        
    def browse_path(self):
        path = filedialog.askdirectory(initialdir=self.path_var.get())
        if path:
            # Normalize to Windows style
            path = os.path.normpath(path)
            if not path.endswith(APP_NAME):
                path = os.path.join(path, APP_NAME)
            self.path_var.set(path)
            
    def start_installation(self):
        target_dir = self.path_var.get()
        source_dir = os.path.dirname(os.path.abspath(__file__))
        
        if os.path.exists(target_dir):
            if not messagebox.askyesno("경고", f"선택한 폴더({target_dir})가 이미 존재합니다.\n덮어쓰시겠습니까?"):
                return
        
        self.install_btn.config(state="disabled", text="설치 중...")
        self.progress.pack(pady=10)
        self.root.update()
        
        try:
            # 1. Copy Files
            self.copy_files(source_dir, target_dir)
            
            # 2. Create Shortcut
            self.create_shortcut(target_dir)
            
            # 3. Success Notification
            messagebox.showinfo("성공", f"{APP_NAME} 설치가 완료되었습니다!\n바탕화면의 바로가기를 사용해 주세요.")
            
            # 4. Trigger Self-Cleanup (Automatic)
            self.trigger_cleanup(source_dir)
            
            self.root.destroy()
            
        except Exception as e:
            messagebox.showerror("오류", f"설치 중 오류가 발생했습니다: {str(e)}")
            self.install_btn.config(state="normal", text="설치 시작")
            self.progress.pack_forget()

    def copy_files(self, src, dst):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        
        # We don't want to copy everything blindly if we are inside the src
        # But for the pseudo-installer, 'src' is the extracted folder.
        # We should skip the installation script itself if we want, but it's fine to keep it.
        
        files = [f for f in os.listdir(src) if f not in ['.git', '__pycache__']]
        total = len(files)
        
        if not os.path.exists(dst):
            os.makedirs(dst)
            
        for i, item in enumerate(files):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
            
            self.progress['value'] = ((i + 1) / total) * 100
            self.root.update()
            
    def create_shortcut(self, target_dir):
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        shortcut_path = os.path.join(desktop, f"{APP_NAME}.lnk")
        
        # Launcher script path in the installed folder
        # We assume start.vbs or a similar launcher is in the root
        # For now, let's point to 'launcher.py' via 'pythonw.exe'
        pythonw_exe = os.path.join(target_dir, "app", "python", "pythonw.exe")
        launcher_py = os.path.join(target_dir, "launcher.py")
        icon_path = os.path.join(target_dir, ICON_NAME)
        
        vbs_script = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{pythonw_exe}"
oLink.Arguments = "{launcher_py}"
oLink.IconLocation = "{icon_path}, 0"
oLink.WorkingDirectory = "{target_dir}"
oLink.Description = "{APP_NAME}"
oLink.Save
'''
        vbs_file = os.path.join(target_dir, "temp_shortcut.vbs")
        with open(vbs_file, "w", encoding="cp949") as f:
            f.write(vbs_script)
            
        subprocess.run(["cscript", "//nologo", vbs_file], shell=True)
        os.remove(vbs_file)

    def trigger_cleanup(self, source_dir):
        # Create a batch file that waits for this process to exit and then deletes the folder
        cleanup_bat = os.path.join(os.environ["TEMP"], "lynx_cleanup.bat")
        pid = os.getpid()
        
        batch_content = f'''
@echo off
chcp 65001 >nul
set "tasklist=%SystemRoot%\System32\tasklist.exe"
set "find=%SystemRoot%\System32\find.exe"
set "timeout=%SystemRoot%\System32\timeout.exe"

:wait
"%tasklist%" /fi "PID eq {pid}" | "%find%" ":" > nul
if errorlevel 1 (
    "%timeout%" /t 2 /nobreak > nul
    rd /s /q "{source_dir}"
    del "%~f0"
) else (
    "%timeout%" /t 1 /nobreak > nul
    goto wait
)
'''
        with open(cleanup_bat, "w", encoding="cp949") as f:
            f.write(batch_content)
        
        # Start the batch file in a separate process
        # 0x00000010 is CREATE_NEW_CONSOLE, 0x00000008 is DETACHED_PROCESS
        try:
            subprocess.Popen(["cmd.exe", "/c", cleanup_bat], shell=True, 
                             creationflags=0x00000010 | 0x00000008)
        except Exception:
            # If for some reason Popen fails, we don't want to crash the installer
            pass

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = InstallerGUI(root)
        root.mainloop()
    except Exception as e:
        # Emergency error reporting
        with open("install_error.log", "w", encoding="utf-8") as f:
            f.write(str(e))
