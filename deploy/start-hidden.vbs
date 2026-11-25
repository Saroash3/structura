' Starts the Structura supervisor with no window at all (used by the "Structura Backend" scheduled task).
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & here & "\structura-supervisor.ps1"""
CreateObject("WScript.Shell").Run cmd, 0, False
