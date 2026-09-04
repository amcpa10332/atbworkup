# How to Install — ATBWorkup (Trial Balance Workup Tool)

This is the desktop app you'll use for the trial balance workup assignments.
Follow the steps for your operating system below.

---

## Windows

1. **Download** `ATBWorkupSetup-v0.1.0.exe` from the link your instructor shared.
2. Double-click it to run the installer.
3. You'll almost certainly see a blue **"Windows protected your PC"** screen.
   This is normal — it appears for any app that isn't from a large,
   commercially-signed publisher, not just this one. To continue:
   - Click **More info**
   - Click **Run anyway**
4. Click through the setup wizard: **Next → Next → Install → Finish**.
   (It installs just for your own Windows account, so it won't ask for an
   admin password — this works even on school-managed lab machines.)
5. It creates a shortcut on your Desktop and in the Start Menu named
   **ATBWorkup**. Use either one to launch it from now on.
6. The first time the app opens, it will ask you to set up your **profile**
   (your name and initials). This only happens once — it identifies your
   work in the audit log, so use your real name.
7. You're in. Create a new workup or open an existing `.atbw` file to begin.

### If your antivirus quarantines or deletes the installer
Some antivirus tools flag unsigned apps from unfamiliar publishers, even
when they're harmless — this is common for small/student-distributed
software, not a sign of infection. If the installer or the app disappears
after you run it, check your antivirus's quarantine/history and restore it,
or add an exception. If your school-managed laptop won't let you override
this, contact the instructor rather than trying to disable your antivirus
entirely.

### Uninstalling / reinstalling
Use **Settings → Apps → Installed apps → ATBWorkup → Uninstall**, same as
any other Windows program — no need to hunt down files by hand.

---

## Mac

1. **Download** `ATBWorkup-Installer-apple-silicon.pkg` from the link your
   instructor shared. (If you're on an older Intel Mac rather than Apple
   Silicon/M-series, ask the instructor — that build may not be ready yet.
   Not sure which you have? Apple menu → **About This Mac** → check the
   "Chip" line.)

2. **Before you double-click it**, clear the download flag that makes macOS
   distrust it — this step is required, not optional, and skipping it is
   the single most common thing that goes wrong here:
   - Open **Terminal** (press `Cmd + Space`, type `Terminal`, press Enter)
   - Type `xattr -cr ` (with a trailing space after it) — **don't press
     Enter yet**
   - Drag the downloaded `.pkg` file from your **Downloads** folder into
     the Terminal window — this fills in its file path for you
   - Press **Enter**. No output means it worked.

3. Now double-click the `.pkg` file. It should open straight into the
   installer with no warning. (If you skipped step 2, or it still refuses
   with a message about being "damaged" or from an "unidentified
   developer," go back and do step 2 — that fixes it.)

4. The standard macOS installer window opens. Click through
   **Continue → Install → Close**. It may ask for your Mac's own login
   password partway through — that's normal for installing any app into
   Applications, not something specific to this one.

5. Open **ATBWorkup** from Launchpad or your Applications folder.

6. The first time the app opens, it will ask you to set up your **profile**
   (your name and initials). This only happens once — it identifies your
   work in the audit log, so use your real name.

7. You're in. Create a new workup or open an existing `.atbw` file to begin.

### Uninstalling / reinstalling
Drag **ATBWorkup** from Applications to the Trash, same as any other Mac
app. Your workup files (`.atbw`) are untouched — they're separate files,
not stored inside the app.

---

## Where your data lives

Each workup is a single `.atbw` file — keep it wherever you'd keep any other
class file (Desktop, a synced folder, a flash drive). The app also keeps a
small settings file (your profile, custom templates) at:

- Windows: `%APPDATA%\ATBWorkup\`
- Mac: `~/Library/Application Support/ATBWorkup/`

You don't need to touch this yourself; it's mentioned here only so you know
it exists if something looks like it "forgot" your profile after moving to
a different computer.

## Submitting your work

Turn in the exported **`.atbr.xlsx`** review package (via the app's export/
submit workflow), not the raw `.atbw` file, unless the assignment says
otherwise. The exported file carries an internal audit trail of your work —
don't edit it by hand after exporting, or after unhiding any worksheet tabs.

## Getting help

If the app won't launch, crashes, or you get an error you don't understand,
email the instructor with:
- A screenshot of the error
- Whether you're on Windows or Mac
- What you were doing right before it happened

Don't try to fix database or settings files by hand — send the `.atbw` file
along with your email instead.
