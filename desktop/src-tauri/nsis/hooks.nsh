; Installer hooks for the Pentaho Exam Bank.
;
; Deliberately hooks rather than a full template override. Tauri renders its
; own installer.nsi at bundle time and it already handles the webview
; bootstrapper, shortcuts, uninstall entries and per-machine elevation; the
; only things this app needs on top are a discovery key and a clean upgrade.
; Overriding the whole template would mean owning eleven hundred lines of
; someone else's NSIS to add twenty of our own.
;
; Tauri calls these macros by name. They must exist even when empty, so each
; one is defined whether or not it does anything.
;
; ASCII only - NSIS reads this in the system codepage.

; Where an installed bank registers itself, so the Content Editor's Questions
; button can find it. THE NAME AND SHAPE ARE NOT OURS TO CHOOSE: the editor
; reads the DEFAULT value of HKLM\SOFTWARE\Pentaho\ExamBank and expects an
; install DIRECTORY (api/peb.py, _PEB_KEY). PLAN.md called the key
; "QuestionBank", which is the pre-rename name and would never be read.
!define PEB_REGKEY "SOFTWARE\Pentaho\ExamBank"

!macro NSIS_HOOK_PREINSTALL
  ; Clear the two vendored trees before laying down new ones.
  ;
  ; An upgrade otherwise MERGES over the old install: a Python package removed
  ; from requirements.txt, or a module deleted from exam_bank/, stays on disk
  ; and stays importable. The app then runs against a mixture of two releases,
  ; which is the hardest kind of bug to see - everything is present, nothing
  ; is consistent.
  ;
  ; Only these two, and only because the installer owns them entirely. The
  ; user's database and config live in %APPDATA% (see PEB_STATE_DIR in
  ; src/server.rs) and must survive an upgrade untouched.
  DetailPrint "Removing the previous application files..."
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\python"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; The discovery key, in BOTH registry views.
  ;
  ; An NSIS installer is a 32-bit process, so its writes land in
  ; WOW6432Node by default. The Content Editor's backend is 64-bit Python and
  ; reads KEY_WOW64_64KEY first - so writing only the default view leaves the
  ; button unable to find an install that is definitely there. It reads both
  ; views for exactly this reason; we write both so either order works.
  DetailPrint "Registering the Exam Bank for the Content Editor..."
  SetRegView 64
  WriteRegStr HKLM "${PEB_REGKEY}" "" "$INSTDIR"
  WriteRegStr HKLM "${PEB_REGKEY}" "Version" "${VERSION}"
  SetRegView 32
  WriteRegStr HKLM "${PEB_REGKEY}" "" "$INSTDIR"
  WriteRegStr HKLM "${PEB_REGKEY}" "Version" "${VERSION}"
  SetRegView lastused
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; Nothing to do before Tauri removes its own files.
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Take the discovery key out of both views, so the Content Editor's button
  ; stops offering an install that is gone rather than launching a path that
  ; no longer exists.
  DetailPrint "Removing the Exam Bank registration..."
  SetRegView 64
  DeleteRegKey HKLM "${PEB_REGKEY}"
  SetRegView 32
  DeleteRegKey HKLM "${PEB_REGKEY}"
  SetRegView lastused

  ; The vendored trees, which the installer created and Tauri's own uninstall
  ; list does not cover: it removes what it recorded installing, and these
  ; arrived as bundled resources.
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\python"

  ; The user's bank is NOT removed. It lives in %APPDATA%\com.pentaho.exam-bank
  ; and is their work, not ours - the same rule every app in this suite
  ; follows. Uninstalling a tool must not delete what was made with it.
!macroend
