# Getting Started

## Opening the app

The Exam Bank is a Windows desktop app. Open it from its desktop shortcut, or
from the **Questions** button in the Pentaho Content Editor, which opens it on
the course you were editing: the Generate and Bank screens start on that course.

## The window

- **The side bar** holds the screens: Courses, Generate, Import and AI Chat
  (bringing questions in, and asking about the app or about Pentaho); Bank,
  Report, Exam paper and Publish (working with them); Settings, Admin and
  Documentation (the app itself). The Bank entry shows how many questions the
  bank holds.
- **The status bar** along the bottom reads *Exam Bank v1.7.2 · Content Manager
  v0.5.0*: this app's version, and the version of the Content Manager whose
  courses it reads. If the interface and the backend ever report different
  versions, the Exam Bank part turns red — restart the app.

## Where the database, backups and courses live

- **The bank** is one SQLite database in your user profile:
  `%APPDATA%\com.pentaho.exam-bank\db\exam_bank.db`. Settings shows the exact
  path.
- **Backups** sit beside it in `db\backups\`, one file per backup, named with
  the time and a label.
- **The courses** are read from the Content Manager's `courses/` folder, found
  at install time. Settings shows it and lets you change it.
