"""HTTP layer over the bank.

A thin wrapper: every endpoint delegates to ``core`` and adds nothing but
request parsing and status codes. The business logic stays where it is, so it
is exercised by the same tests whether it is reached over HTTP or not.

This is now the app's only surface. It also serves the built React front end
from ``frontend/dist`` at its own root, so the interface and the API are one
process on one port; ``exam_bank.gui``, the NiceGUI layer this replaced, was
deleted once every pane had moved.
"""
