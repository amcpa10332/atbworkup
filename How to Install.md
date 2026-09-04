# How to Install — ATBWorkup (Trial Balance Workup Tool)

This is the desktop app you'll use for the trial balance workup assignments.
Follow the steps for your operating system below.

---

## Windows

1. **Download** `ATBWorkupSetup-v0.1.0.zip` from the class Team (Files tab).
2. **Extract it first**: right-click the zip → **Extract All...** → Extract.
   There's only one file inside (the installer) — it's zipped only because
   Teams won't let `.exe` files be uploaded directly, not because there's
   anything else to unpack.
3. Double-click the extracted **ATBWorkupSetup-v0.1.0.exe** to run the installer.
4. You'll almost certainly see a blue **"Windows protected your PC"** screen.
   This is normal — it appears for any app that isn't from a large,
   commercially-signed publisher, not just this one. To continue:
   - Click **More info**
   - Click **Run anyway**
5. Click through the setup wizard: **Next → Next → Install → Finish**.
   (It installs just for your own Windows account, so it won't ask for an
   admin password — this works even on school-managed lab machines.)
6. It creates a shortcut on your Desktop and in the Start Menu named
   **ATBWorkup**. Use either one to launch it from now on.
7. The first time the app opens, it will ask you to set up your **profile**
   (your name and initials). This only happens once — it identifies your
   work in the audit log, so use your real name.
8. You're in. Create a new workup or open an existing `.atbw` file to begin.

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

1. **Download** `ATBWorkup-v0.1.0-mac.zip` from the class Team (Files tab).
2. Double-click it to unzip — this produces **ATBWorkup.app**.
3. Drag **ATBWorkup.app** into your **Applications** folder (open a Finder
   window, click Applications in the sidebar, drag it in).
4. Open it from Applications. macOS will refuse the first launch with
   *"ATBWorkup can't be opened because it is from an unidentified
   developer"* — this is normal for any app that isn't distributed through
   the App Store or signed with a paid Apple developer account, not a sign
   of anything wrong. To get past it (only needed once):
   - **Right-click** (or Control-click) **ATBWorkup.app** → **Open** →
     click **Open** again in the dialog that appears.
   - If that doesn't offer an "Open" option: go to **System Settings →
     Privacy & Security**, scroll down to the security message about
     ATBWorkup, and click **Open Anyway**. Then open the app again.
5. The first time the app opens, it will ask you to set up your **profile**
   (your name and initials). This only happens once — it identifies your
   work in the audit log, so use your real name.
6. You're in. Create a new workup or open an existing `.atbw` file to begin.

### Apple Silicon vs. Intel
This build was made on one specific Mac and matches its chip type (Apple
Silicon/M-series, or Intel — whichever the instructor's test machine
used). If the app won't open at all and you don't see the "unidentified
developer" message described above, it may be built for the other chip
type — contact the instructor rather than troubleshooting this yourself.

### Uninstalling / reinstalling
Drag **ATBWorkup.app** from Applications to the Trash, same as any other
Mac app. Your workup files (`.atbw`) are untouched — they're separate
files, not stored inside the app.

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
