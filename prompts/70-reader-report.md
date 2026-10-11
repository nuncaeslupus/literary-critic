# Reader report (agency or editor assessment)

Use this when the profile's mode is `reader-report`: the user is assessing a
manuscript, not revising their own. The same index, metrics and findings are
used; the output is an assessment, not a revision plan.

1. Make sure L0 exists (`<ws>/analysis/synopsis.md`, see `25-summaries.md`)
   and that the developmental and holistic checks have been run
   (`40-checks.md`), including strength checks.
2. Write your judgment to `<ws>/analysis/report.json`:

   ```json
   {
     "schema_version": 1,
     "logline": "One or two sentences, at most 50 words.",
     "genre": "Genre and subgenre as a bookseller would shelve it",
     "readership": "Who will read it and why",
     "comparables": ["Two to four recent comparable titles, with author"],
     "market_fit": "Where it sits in the current market, what helps and hurts it",
     "verdict": "recommend | consider | pass",
     "verdict_reason": "Why, in a few sentences, citing the main strengths and weaknesses"
   }
   ```

   Validate: `lc validate report <ws>/analysis/report.json`.
3. Render it: `lc report --workspace <slug>` writes
   `<ws>/analysis/reader-report.md` in the novel's language, with strengths
   and weaknesses from the findings (located in the text), the synopsis and
   the manuscript facts. It warns about any section that came out empty.
4. Be fair and specific: every weakness needs evidence, every strength too,
   and the verdict follows from them. Do not rewrite passages to show how they
   should read.
