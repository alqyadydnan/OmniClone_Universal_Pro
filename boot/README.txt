Place WinPE PXE boot files here before running build.bat

Required files:
  pxelinux.0   (copy of pxeboot.n12 from Windows ADK)
  boot.wim     (WinPE image with OmniClone_Agent.exe injected)
  BCD          (Boot Configuration Data)
  bootmgr      (Windows Boot Manager)
  bootmgr.efi  (UEFI Boot Manager)
  EFI/         (EFI directory from WinPE media)

See WINPE_SETUP.md for full step-by-step instructions.
