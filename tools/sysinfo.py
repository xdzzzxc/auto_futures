# -*- coding: utf-8 -*-
import subprocess, json, sys

def ps(query):
    """执行 PowerShell CIM 查询，返回 list[dict]"""
    cmd = ["powershell", "-NoProfile", "-Command",
           query + " | ConvertTo-Json -Compress"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="gbk",
                         errors="ignore").stdout.strip()
    if not out:
        return []
    try:
        d = json.loads(out)
        return d if isinstance(d, list) else [d]
    except Exception:
        return []

def section(title, rows):
    print(f"\n===== {title} =====")
    for k, v in rows:
        print(f"  {k:<10}: {v}")

# 机型 / 主板 / BIOS
cs   = ps("Get-CimInstance Win32_ComputerSystem")[0]
bb   = ps("Get-CimInstance Win32_BaseBoard")[0]
bios = ps("Get-CimInstance Win32_BIOS")[0]
section("机型 / 主板 / BIOS", [
    ("机型",   f"{cs.get('Manufacturer','')} {cs.get('Model','')}"),
    ("主板",   f"{bb.get('Manufacturer','')} {bb.get('Product','')}"),
    ("版本",   bb.get('Version','')),
    ("BIOS",   f"{bios.get('Manufacturer','')} {bios.get('SMBIOSBIOSVersion','')} ({bios.get('ReleaseDate','')})"),
    ("开机启动", bios.get('PrimaryBIOS','')),
])

# CPU
for c in ps("Get-CimInstance Win32_Processor"):
    section("CPU", [
        ("名称",   c.get('Name','').strip()),
        ("核心/线程", f"{c.get('NumberOfCores','?')}C / {c.get('NumberOfLogicalProcessors','?')}T"),
        ("主频",   f"{c.get('MaxClockSpeed','?')} MHz"),
    ])

# 内存
mems = ps("Get-CimInstance Win32_PhysicalMemory")
total = sum(int(m.get('Capacity',0) or 0) for m in mems) / 1024**3
section("内存", [
    ("总容量", f"{total:.1f} GB"),
    ("条数",   str(len(mems))),
])
for i, m in enumerate(mems, 1):
    cap = int(m.get('Capacity',0) or 0)/1024**3
    print(f"  #{i}: {cap:.0f}GB  {m.get('Manufacturer','')}  "
          f"{m.get('Speed','')}MHz  PN={m.get('PartNumber','').strip()}")

# 显卡
for g in ps("Get-CimInstance Win32_VideoController"):
    vram = int(g.get('AdapterRAM',0) or 0)/1024**3
    section("显卡", [
        ("名称", g.get('Name','')),
        ("显存", f"{vram:.1f} GB"),
        ("驱动", g.get('DriverVersion','')),
    ])

# 磁盘(顺带，判断休眠/快速启动相关)
for d in ps("Get-CimInstance Win32_DiskDrive"):
    section("磁盘", [("型号", d.get('Model','')),
                     ("容量", f"{int(d.get('Size',0) or 0)/1024**3:.0f} GB")])

print("\n把以上输出整段发给我即可。")
