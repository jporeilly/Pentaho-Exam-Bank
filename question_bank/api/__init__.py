"""HTTP layer over the bank.

A thin wrapper: every endpoint delegates to ``core`` and adds nothing but
request parsing and status codes. The business logic stays where it is, so it
is exercised by the same tests whether it is reached over HTTP or not.

This package must never import ``question_bank.gui`` — the NiceGUI layer is
being replaced, and the API is what replaces the need for it.
"""
