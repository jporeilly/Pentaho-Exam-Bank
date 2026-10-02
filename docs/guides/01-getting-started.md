# Getting Started

## Opening the app

The Exam Bank is a Windows desktop app. Open it from its desktop shortcut, or
from the **Questions** button in the Pentaho Content Editor, which opens it on
the course you were editing: the Generate and Bank screens start on that course.

## The window

- **The side bar** holds the screens: Courses, Generate, Import and AI Chat
  (bringing questions in, and asking about the app or about Pentaho), in blue;
  Bank, Report, Exam paper and Publish (working with them), in teal; Settings,
  Admin and Documentation (the app itself), in violet. The Bank entry shows how
  many questions the bank holds.
- **The status bar** along the bottom reads *Exam Bank v1.11.0 · Content
  Manager v0.6.0*: this app's version, and the version of the Content Manager
  whose courses it reads. If the interface and the backend ever report
  different versions, the Exam Bank part turns red — restart the app.

## What the colours mean

The same colour means the same thing on every screen:

| Colour | Buttons | Elsewhere |
| --- | --- | --- |
| Teal | The screen's main action, such as Save | The current screen in the side bar |
| Violet | Anything the AI does: rewrite, check, explanation, answer key, Generate, Ask | |
| Green | Adding or keeping: Add a distractor, Import, Save to the bank, Use this | A correct answer |
| Blue | Looking without changing: Refresh, Export, Check, Contents | |
| Red | Removing or rejecting: Remove, Delete, Reject, Stop | A distractor (a wrong answer), and problems that stop a save |

A filled button is a screen's main action; a tinted one with coloured text is
a secondary action of the same kind.

## Where the database, backups and courses live

- **The bank** is one SQLite database in your user profile:
  `%APPDATA%\com.pentaho.exam-bank\db\exam_bank.db`. Settings shows the exact
  path.
- **Backups** sit beside it in `db\backups\`, one file per backup, named with
  the time and a label.
- **The courses** are read from the Content Manager's `courses/` folder, found
  at install time. Settings shows it and lets you change it.
