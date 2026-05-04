
# OmniClone Universal Pro

<p align="center">
  <img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Version-1.0.0-blue?style=for-the-badge" />
</p>

<p align="center">
  <img src="Screenshot 2026-05-04 212920.png" alt="OmniClone Universal Pro Interface" width="850"/>
</p>

<p align="center">
  <img src="Annotation 2026-05-04 120802.png" alt="OmniClone Universal Pro Interface" width="850"/>
</p>

<p align="center">
  <img src="Annotation 2026-05-04 120557.png" alt="OmniClone Universal Pro Interface" width="850"/>
</p>

## 📖 Overview

**OmniClone Universal Pro** is a professional, high-end Windows system cloning tool designed for IT engineers and system administrators. It allows you to clone any Windows-based operating system (Windows 7, 8, 10, 11, Server) from one machine to another **directly over Ethernet** — no external drives, no USB hubs, no extra software.

The tool embeds its own **PXE, TFTP, and DHCP servers**, intelligently transfers **only used sectors** (skipping empty space), verifies every block with **MD5 checksums**, compresses data on-the-fly with **lz4**, and automatically repairs the target's boot sector for both **BIOS and UEFI** systems. The target machine boots via PXE or WinPE, receives the cloned data, and boots into the new operating system seamlessly.

> 🚀 **One-click cloning. Zero data loss. Hardware agnostic.**

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Arabic RTL GUI** | Professional Right‑to‑Left interface built with PyQt6 |
| **Smart Block‑Level Transfer** | Copies only used sectors — skips empty space for maximum speed |
| **lz4 Compression** | Ultra‑fast compression with excellent performance |
| **MD5 Per Block** | 100% data integrity verification on every block |
| **Embedded Network Services** | Integrated PXE, TFTP, and DHCP servers — no external tools needed |
| **Safety Lock** | Automatically dismounts/locks all non‑target partitions on the destination |
| **Automatic Boot Repair** | Detects BIOS/UEFI and runs `bcdboot` automatically after clone |
| **Hardware Agnostic** | Handles different hardware between source and target |
| **Standalone EXE** | Single portable executable — no Python or dependencies required |

---

## 📥 Download

### [⬇️ Download OmniClone_Universal_Pro.exe](https://github.com/yourusername/omniclone/releases/latest)

> ⚠️ **Important**: Run the executable as **Administrator** (Right‑click → Run as Administrator)

---

## 🖥️ System Requirements

### Source Machine
| Requirement | Details |
|-------------|---------|
| OS | Windows 7 / 8 / 10 / 11 (64‑bit) |
| Privileges | Administrator |
| Network | One available Ethernet port |
| Disk Space | 50 MB + space for clone operation |

### Target Machine
| Requirement | Details |
|-------------|---------|
| Boot Method | PXE Boot or WinPE USB |
| Network | One available Ethernet port |
| BIOS/UEFI | Both supported (auto‑detected) |

---

## 🔧 How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   SOURCE MACHINE                    TARGET MACHINE                          │
│   ┌─────────────────┐              ┌─────────────────┐                      │
│   │  OmniClone GUI  │              │  PXE / WinPE    │                      │
│   │  (Admin)        │              │  Boot           │                      │
│   └────────┬────────┘              └────────┬────────┘                      │
│            │                                │                               │
│            ▼                                ▼                               │
│   ┌─────────────────┐              ┌─────────────────┐                      │
│   │  DHCP Server    │◄──Ethernet───►│  DHCP Client    │                      │
│   │  TFTP Server    │              │  (Agent)        │                      │
│   │  (Built‑in)     │              │                 │                      │
│   └────────┬────────┘              └────────┬────────┘                      │
│            │                                │                               │
│            ▼                                ▼                               │
│   ┌─────────────────┐              ┌─────────────────┐                      │
│   │  Source         │    lz4+MD5   │  Target         │                      │
│   │  Partition      │ ───────────► │  Partition      │                      │
│   │  (Read‑Only)    │   Blocks     │  (Write)        │                      │
│   └─────────────────┘              └─────────────────┘                      │
│                                                                             │
│   After transfer → Boot repair (bcdboot) → Target reboots into new OS       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📖 Usage Guide

### Quick Start (Two Physical Machines)

#### Step 1: On the Source Machine
```batch
# Run as Administrator
OmniClone_Universal_Pro.exe

# Click "Start Network Services"
# Select the source partition (e.g., C:)
```

#### Step 2: On the Target Machine
```batch
# Option A: Run the agent directly (if Windows is already running)
OmniClone_Agent.exe

# Option B: Boot from WinPE (Hiren's BootCD PE recommended)
# Boot via PXE or USB → Run OmniClone_Agent.exe inside WinPE
```

#### Step 3: Start Cloning
- Source GUI will show target partitions
- Select source partition (left panel)
- Select target partition (right panel)
- Click **"Start Clone"**
- Double‑confirm (type the target drive letter)
- Wait for completion (progress bar + speed + ETA)

#### Step 4: After Completion
- Target will automatically repair its boot sector
- Remove the WinPE USB / disconnect ISO
- Reboot the target machine
- Target will boot from the cloned Windows!

---

## 🛠️ Building from Source

### Prerequisites
```bash
Python 3.11+ (64-bit)
pip install PyQt6 lz4 pyinstaller
```

### Build Commands
```bash
# Clone the repository
git clone https://github.com/yourusername/omniclone.git
cd omniclone

# Run the build script
build.bat
```

### Output Files
```
dist/
├── OmniClone_Universal_Pro.exe   # Source machine GUI
└── OmniClone_Agent.exe           # Target machine agent (for WinPE)
```

---

## 📂 Project Structure

```
omniclone/
├── src/
│   ├── main.py              # Entry point
│   ├── gui/                 # PyQt6 RTL interface
│   ├── engine/              # Clone engine (lz4 + MD5)
│   ├── services/            # DHCP + TFTP + PXE servers
│   └── protocol/            # Communication protocol
├── agent/
│   ├── main.py              # Target agent
│   ├── partition_scanner.py # Disk/partition enumeration
│   ├── partition_writer.py  # Block writing
│   └── lock_manager.py      # Volume locking (safety)
├── boot/                    # WinPE boot files (optional)
├── resources/               # Icons and assets
├── build.bat               # One‑command build script
└── requirements.txt        # Python dependencies
```

---

## 🔐 Security & Safety

| Safety Mechanism | Description |
|------------------|-------------|
| **Source Read‑Only** | Source partition opened with `GENERIC_READ` only — no accidental writes |
| **Target Partition Lock** | All non‑target partitions are dismounted via `FSCTL_DISMOUNT_VOLUME` |
| **MD5 Checksums** | Every block is verified before writing; corrupted blocks are retried |
| **Double Confirmation** | User must type the target drive letter before cloning starts |
| **Admin Required** | Both GUI and agent require Administrator privileges |

---

## ❓ FAQ

### Can I clone between different hardware (different motherboards, chipsets)?
**Yes.** The tool is hardware‑agnostic. After cloning, it automatically fixes the boot configuration using `bcdboot`, making the target system bootable on completely different hardware.

### Do I need a crossover Ethernet cable?
**No.** Modern network cards support Auto‑MDI/X, so a standard Ethernet cable works fine.

### What happens to other partitions on the target drive?
They are **safely locked and dismounted**. No data can be written to them. Only the selected target partition is overwritten.

### Can I clone from a larger disk to a smaller disk?
**Only if the used space fits.** The tool transfers only used sectors, so you can clone to a smaller drive as long as the compressed used data fits.

### Does this work on Linux?
**The tool is Windows‑only.** To clone a Windows system, run the tool on a Windows machine (or inside a Windows VM with direct disk access).

### Can I test without a second physical machine?
**Yes.** Use VMware or VirtualBox:
- Create two VMs on the same host‑only network
- Source VM: Windows + OmniClone GUI
- Target VM: Boot from Hiren's BootCD PE + Agent

### Why am I getting "Connection closed" or "WinError 10054"?
Disable Windows Firewall on the source machine temporarily:
```cmd
netsh advfirewall set allprofiles state off
```

---

## 🧪 Testing with VMware (No Physical Machines Required)

1. Create two VMs on the same **Host‑only** network (VMnet1)
2. Configure IPs: Source `192.168.100.1`, Target `192.168.100.3`
3. Source VM: Run `OmniClone_Universal_Pro.exe` → Start Network Services
4. Target VM: Boot from Hiren's BootCD PE → Run `OmniClone_Agent.exe`
5. Clone as described above

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## 📧 Contact & Support

- **Email**: alqyadydnan@gmail.com
- **Issues**: [GitHub Issues](https://github.com/alqyadydnan/OmniClone_Universal_Pro)

---



<p align="center">
  <img src="https://img.shields.io/badge/Made%20with-Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/UI-PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
</p>
```

