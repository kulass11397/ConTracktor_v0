# Pending Microsoft detection review

Reported detection: Trojan:Win32/Wacatac.B!ml, removed on the affected client PC on 18 September 2026. The provided screenshot is incomplete and does not show a usable full file path/hash. It shows a reported detection associated with the prior updater download. Do not restore that file or treat the report as proven false positive.

Original public updater: ConTracktor_v1_Update_1.7.1.exe
SHA-256: 7e8a59be4df5e55b1ea6b40722c35314b70bd022ea5658b48be09190fb24ad8a

Candidate replacement: ConTracktor_v1_Update_1.7.6.exe
SHA-256: a08bba5dd18acecc4c0b8db477c1c8a5837f74e82bf56b0ae2a858620dad0600

The old hash matches the tested local build and GitHub's uploaded asset digest. Local Defender scans did not reproduce the client detection. This disagreement is not a verdict.

The replacement retains standard Inno Setup packaging, adding project-aware cash-advance attribution to the existing weekly attendance and expense reporting. Components are visible after installation, and it implements backup/in-use checks without AV exemptions. Packaging remediation is not malware clearance.

Local verification for v1.7.6: Microsoft Defender's on-demand scan of the completed installer on 23 September 2026 found no matching detections. The isolated installer test preserved the supplied 23 September client database byte-for-byte, created application/data backups, and launched the installed app. The locked-database test correctly blocked installation. The payload contains no database files. These checks do not establish Microsoft cloud/download clearance for this build or another computer.

Microsoft developer sample-review portal: https://www.microsoft.com/en-us/wdsi/filesubmission
Microsoft developer guidance: https://learn.microsoft.com/en-us/defender-xdr/developer-faq

The original EXE should be submitted as a software-developer sample with the reported threat and detection context. The replacement can be submitted alongside it. Only public build artifacts are relevant; no client database or private records should be uploaded. Obtain the owner's approval and complete Microsoft sign-in/consent before submission. No sample submission has been made and no Microsoft verdict is available.

Trusted publisher code signing is a separate deployment improvement; no signing certificate is available in the current workspace. Signing alone is not a malware verdict or a guaranteed warning bypass.

When client testing is permitted, record the full affected-file path, SHA-256, threat name, Defender signature version and time, and whether detection occurs during download, installation or first launch. If the candidate is detected, stop and retain the evidence; do not disable protection.
