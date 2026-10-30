# Writing style

All prose of taskflow follows ASD-STE100 (Simplified Technical English), in
the language it is written in, Italian included. This covers the task files
(Goal, Context, Steps, Acceptance criteria, Verification, Outcome), the grill
questions, the reports and the closing summaries of every skill, and the
final answers of the implementer and the verifier. The aim is 80% of the
standard: clear and short, not a legal exercise.

## Rules

1. **One idea per sentence.** About 20 words for a description, 15 for a
   step. A sentence with "and", "but" or "which" that holds two ideas becomes
   two sentences.
2. **Active voice.** Name the actor: "The verifier moves the task", not "The
   task is moved".
3. **Steps in the imperative, one action per step.** "Add the field. Run the
   suite." Not "Add the field and then run the suite".
4. **Common words, one meaning per word.** "Use", not "utilize". "Start", not
   "initiate". A word keeps one meaning in the whole task.
5. **The same term for the same thing.** Do not alternate "task", "ticket"
   and "item", or "folder" and "directory". Use the repo's own vocabulary
   (its glossary, if it has one).
6. **Concrete before abstract.** Give the file, the command, the number, the
   observed result. Avoid "appropriate", "properly", "as needed".

## Not touched by the style

- Headings, field names and stage names that the Tool parses or generates.
- The `Depends on`, `Status`, `Who`, `Files` and `Type` header lines: they
  keep the format of [task-format.md](task-format.md).
- Ids, paths, commands, code, quoted error text and quoted user words.
- The `VERDICT:` and `BLOCKED:` first lines of the subagents.

## Example

Before:
> The endpoint should be updated so that it properly handles the case where
> the batch is empty, which was previously causing an error to be raised.

After:
> Change `post_batch` in `api/batch.py`. Return an empty list when the batch
> is empty. Today it raises `ValueError`.
