# Cut kinds

Each cut removes one **logical block**. "Conservative" means the kind is allowed when coverage could not be measured (conservative mode, and always in static mode). These cuts do not depend on which branches run. The other kinds need `mode: measured`, and every line they touch must be in `covered`.

| Kind | Conservative | What it is |
|---|---|---|
| Dead import | yes | An import or require whose name is never used in the file. Check for re-exports first (`__all__`, `export … from`): a re-export is part of the interface. |
| Assigned, never read | yes | A variable or attribute that is written and never read. Keep the right-hand side if it has a side effect. |
| Unreachable code | yes | Statements after `return`, `raise`, `exit`, `continue` or `break` in the same block, and `if False`-style constants. |
| Single-use abstraction | yes | A private function, class, constant or wrapper used once, inlined at its call site. Skip it if its name explains something the inlined code would not. |
| Duplication | yes | Two or more identical blocks merged into one. Accept it only when the result is shorter. |
| Unused private function | yes | A function or method with no caller in the file, and no external use according to the interface grep. |
| Unused parameter | yes, if private | A parameter no code reads. In a public signature it is an interface candidate. |
| Redundant guard | measured | A check that the oracle shows is always true or always false on every covered path, or that a previous check already covers. |
| Dead branch | measured | An `if`/`else`/`case` arm with no covered line. **Never remove it.** It is unverifiable, not dead: report it. Remove only a branch whose condition you can prove is impossible from the code itself. |
| Over-general code | measured | A loop, option or parameter that handles cases the interface cannot produce. Simplify it to the case that occurs. |
| Redundant conversion or copy | measured | `list(list(x))`, `str()` of a str, a defensive copy that nothing mutates. |
| Verbose idiom | measured | A hand-written loop that a standard idiom of the language replaces, when the idiom is the plainer read. |

Not cuts: renaming, reformatting, changing the style of comments or docstrings. Removing a comment is fine only when the code it describes is gone.

## Golf test

Reject a cut, and record it as **golf**, when the shorter version:
- replaces a meaningful name with a short or generic one, or removes a named intermediate value that explained a step;
- packs several steps into one expression that has to be read twice (nested comprehensions or ternaries, chained `and`/`or` used for control flow, walrus chains);
- relies on a trick a reader of that language would not expect (truthiness of exotic types, operator precedence puzzles, abuse of default arguments);
- deletes an error message or exit code the user sees. That one is also an output change.

If a careful reader would understand the new code as fast as the old one, the cut is not golf.

## Expected gain, to order candidates

Approximate the lines and tokens the cut removes, including what it makes dead in the same step. Try large blocks first: whole functions, then branches, then imports and variables. A large block that fails verification often hides smaller safe cuts. Those come back in the next pass.
