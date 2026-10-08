# Results: How Questions Perform

The **Results** screen shows how each question does with real candidates:
how many get it right, whether it separates strong candidates from weak ones,
and how often each option is picked.

## Bringing results in

Candidates' answers reach the results Google Sheet; the **Detail** tab holds
one row per question per attempt. In the Sheet, open **Detail**, choose
**File › Download › Comma-separated values**, then in the Exam Bank press
**Import results CSV** and pick the file.

Importing the same export again only adds what is new, so download and import
whenever you want fresh numbers. The candidates' emails in the file are never
kept: an attempt is known only by its id.

## Reading a question's row

- **Correct**: the share of candidates who answered it right. *plays easy* or
  *plays hard* appears when that share disagrees with the difficulty the
  question is marked with.
- **Discrimination**: whether getting this question right goes with doing
  well on the rest of the exam, from −1 to 1. Above 0.3 is good; below 0.15
  the question barely separates strong candidates from weak ones; clearly
  below 0 means stronger candidates do *worse*, which usually means a wrong
  key or a misleading wording. The two percentages under it are the share
  correct among the strongest and the weakest quarter of candidates.
- **Options picked**: one bar per option, the correct one in green.

## Flags

Below 20 attempts a question's numbers are shown but not judged: a dozen
candidates is too few for one lucky guess not to matter. From 20:

- **Very easy** (90% or more right) and **very hard** (30% or fewer).
- **Barely separates** strong candidates from weak ones.
- **Stronger candidates get it wrong more often** - check the key.
- **The strongest candidates prefer a distractor to the key** - check the key.
- **Distractor rarely chosen** (under 5%): it is not doing any work; replace
  it with a mistake candidates actually make.

Two notes appear whatever the count: answers marked against an **earlier
correct answer** (the question was edited after those attempts), and answers
naming an option the question **no longer has**. **Only flagged questions**
hides the rest.
