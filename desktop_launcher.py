"""Small desktop launcher for the OpenCL prototype."""
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

root=tk.Tk()
root.title('OpenCL compression prototype')
root.geometry('740x490')
root.minsize(560,350)
messages=queue.Queue()
frame=ttk.Frame(root,padding=16); frame.pack(fill='both',expand=True)
ttk.Label(frame,text='File and folder compression',font=('Segoe UI',16)).pack(anchor='w')
ttk.Label(frame,text='Choose CPU or a GPU for file and folder compression.\nCPU and GPU both create standard ZIP files. ZIP extraction currently uses CPU.').pack(anchor='w',pady=10)
from hardware import discover
device_options,detection_notices=discover()
device=tk.StringVar(value=next((label for label in device_options if label.startswith('GPU')), next(iter(device_options))))
ttk.Label(frame,text='Processing device:').pack(anchor='w')
selector=ttk.Combobox(frame,textvariable=device,values=list(device_options),state='readonly',width=65)
selector.pack(anchor='w',pady=(0,12))
def refresh_devices():
    global device_options
    previous=device.get()
    device_options,notices=discover()
    selector.configure(values=list(device_options))
    device.set(previous if previous in device_options else next(iter(device_options)))
    status.set('Devices refreshed' if not notices else ' '.join(notices))
refresh_button=ttk.Button(frame,text='Refresh devices',command=refresh_devices)
refresh_button.pack(anchor='w',pady=(0,8))
buttons=ttk.Frame(frame); buttons.pack(anchor='w')
log=tk.Text(frame,wrap='word',height=14); log.pack(fill='both',expand=True,pady=12)
status=tk.StringVar(value='Ready' if not detection_notices else ' '.join(detection_notices))
ttk.Label(frame,textvariable=status).pack(anchor='w')
active=[]

def run(action):
    folder=action=='folder'
    source=filedialog.askdirectory(title='Select folder to compress') if folder else filedialog.askopenfilename(title='Select ZIP or OCLR archive' if action=='decompress' else 'Select file')
    if not source:return
    name=Path(source).name
    selected_device=device_options[device.get()]
    use_cpu=selected_device=='CPU'
    gpu_folder=action=='decompress' and source.lower().endswith('.folder.oclr')
    is_zip=action in ('compress','folder') or (action=='decompress' and Path(source).suffix.lower()=='.zip')
    if action=='decompress' and (is_zip or gpu_folder):
        parent=filedialog.askdirectory(title='Choose parent folder for restored files')
        if not parent:return
        from tkinter import simpledialog
        newname=simpledialog.askstring('Restore folder','Name for a NEW destination folder:',initialvalue=Path(source).stem+'-restored')
        if not newname:return
        if newname in ('.','..') or any(c in newname for c in '/\\:'):
            messagebox.showerror('Invalid folder name','Enter a single folder name.');return
        target=str(Path(parent)/newname)
    else:
        suggested=name+('.zip' if is_zip else '.oclr') if action!='decompress' else (name[:-5] if name.endswith('.oclr') else name+'.restored')
        while True:
            target=filedialog.asksaveasfilename(
                title='Save archive outside the source folder' if folder else 'Save output as',
                initialfile=suggested, initialdir=str(Path(source).resolve().parent),
                defaultextension='.zip' if is_zip else '',
                filetypes=[('ZIP archive','*.zip')] if is_zip else [('All files','*.*')])
            if not target:return
            if folder and Path(target).resolve().is_relative_to(Path(source).resolve()):
                messagebox.showinfo('Choose a different save location',
                    'Save the archive outside the folder you are compressing.\n\nFor example, choose its parent folder or your Desktop. Your source folder has not been changed.')
                continue
            break
    if Path(target).exists():
        messagebox.showinfo('Choose a new name','Choose an output name that does not exist.');return
    for button in active:button.configure(state='disabled')
    selector.configure(state='disabled')
    refresh_button.configure(state='disabled')
    status.set('Working…'); log.delete('1.0','end')
    gpu_zip=is_zip and action!='decompress' and not use_cpu
    tool='gpu_zip.py' if gpu_zip else 'gpu_folder.py' if gpu_folder else 'folder_archive.py' if is_zip else 'opencl_lz.py'
    command=[sys.executable,'-X','utf8',str(Path(__file__).with_name(tool)),'compress' if folder else action,source,target]
    if gpu_zip or not is_zip:command+=['--device',selected_device]
    def worker():
        try:
            result=subprocess.run(command,capture_output=True,text=True,encoding="utf-8",errors="replace",creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            messages.put((result.returncode,result.stdout+result.stderr))
        except Exception as exc:messages.put((1,str(exc)))
    threading.Thread(target=worker,daemon=True).start()

def poll():
    try:
        code,text=messages.get_nowait();log.insert('end',text)
        status.set(('No space saved — output is larger' if 'NO SPACE SAVED' in text else 'Finished') if code==0 else 'Failed — see details above')
        selector.configure(state='readonly')
        refresh_button.configure(state='normal')
        for button in active:button.configure(state='normal')
    except queue.Empty:pass
    root.after(100,poll)

def close():
    if active and str(active[0]['state'])=='disabled':
        messagebox.showinfo('Still working','Please wait for the operation to finish before closing.');return
    root.destroy()

for label,action in [('Compress file','compress'),('Compress folder','folder'),('Restore archive','decompress')]:
    button=ttk.Button(buttons,text=label,command=lambda a=action:run(a));button.pack(side='left',padx=(0,10));active.append(button)
root.protocol('WM_DELETE_WINDOW',close)
root.after(100,poll)
if '--smoke-test' in sys.argv:root.after(300,root.destroy)
root.mainloop()
