# Orientation: the first reading

Goal: understand what the novel is trying to do before judging how well it
does it. Run the `orientation` stage of the checklist.

1. Ask the writer for their brief, briefly and kindly: what the novel is about
   for them, intended readers, comparable books, what they are unsure about,
   anything deliberate that might look like a mistake, and any limits (no
   structural changes, a deadline). Record it in `analysis/brief.md`.
2. Read L0 (`<ws>/analysis/synopsis.md` and the profile, if they exist) and
   L1, the table of contents with chapter summaries:
   `lc show --workspace <slug> --budget 8000`. Then the opening and the last
   chapter in full, and skim metrics (`<ws>/metrics/<version>.json`).
3. Write `<ws>/analysis/profile.toml`:

   ```toml
   mode = "revision"
   language = "es"
   traits = ["first_person", "retrospective_narrator"]
   disabled = []
   [weights]
   ```

   Traits come from `checklist/traits.toml`; pick only those that clearly
   apply. Validate: `lc validate profile <ws>/analysis/profile.toml`.
4. See which checks apply and in what order:
   `lc checklist plan --profile <ws>/analysis/profile.toml`.
5. Tell the writer, in a few lines, what you understand the novel to be and
   to want, what you will look at first, and ask them to correct you.
