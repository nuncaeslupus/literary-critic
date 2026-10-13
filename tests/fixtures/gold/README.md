# Gold entity lists for the corpus texts

`jekyll-hyde.json` and `marianela.json` list the named characters, places and
groups of the two public-domain corpus texts (`corpus/jekyll-hyde`,
`corpus/marianela`), with every surface form the text uses and an exact count
of references. They are the reference for measuring entity discovery, alias
merging and the deterministic reference index.

## Format

```json
{"entities": [{"kind": "character|place|group|object",
               "name": "canonical name",
               "aliases": ["every form the text uses"],
               "occurrences": 0}],
 "minor": [{"kind": "...", "name": "...", "occurrences": 1, "note": "..."}]}
```

`minor` holds one-off names (fewer than 2 references), allusions, figurative
uses and names deliberately not counted (for example the exclamatory `Dios`).
Scoring should treat a candidate that matches a minor entry as neutral: it is
neither a hit nor a false positive.

## How they were built

1. Scripts over the text produced capitalised-token frequencies (with the
   number of mid-sentence uses and whether the lower-case form also occurs),
   honorific + name patterns (`Mr.`, `Dr.`, `Sir`, `D.`, `Sr.`, `don`, `doña`,
   `señor`, `señorita`, ...), and keyword-in-context listings for every
   ambiguous form.
2. Reading judgment then merged aliases into entities, dropped false positives
   (sentence-initial words, interjections, months, weekdays, God as an
   exclamation, chapter-title capitals) and decided each ambiguous form by
   reading its contexts (see below).
3. A script counted references. All alias patterns of all entities are pooled
   and matched case-sensitively against the text with line breaks turned into
   spaces. At each position the longest match wins and overlapping matches are
   dropped, so `Mr. Utterson` is one reference to one entity, never two.
   Possessives (`Hyde's`) count as the name. The counts were sanity-checked
   against the raw capitalised-token frequencies.

## What counts as a reference

- Any use of a listed alias that refers to that entity in the narration or in
  speech, including vocatives (`querido Golfín`) and possessives.
- Honorific or title + name is a single reference (`Dr. Henry Jekyll`,
  `la señorita Florentina`).
- An apposition counts separately from its name (`Mr. Utterson the lawyer` is
  two references to the same entity).
- Role titles are listed as aliases only where they clearly stand for one
  character in this text: `the lawyer`, `the butler`, `the clerk`,
  `the footman`, `the doctor` (Jekyll), `el ciego` (Pablo), `el doctor` and
  `el médico` (Teodoro Golfín), `el ingeniero` (Carlos Golfín), `la señorita`
  (Florentina). Individual uses that refer to someone else are excluded.
- Not counted: pronouns, first-person narration (the closing Jekyll statement
  is all `I`), all-caps chapter titles and running heads, the title page.

## Known ambiguities (decisions taken)

- Jekyll and Hyde are one person but kept as two entities, because the text
  presents them under separate names. The reader of the index has to decide
  how to relate them; references are counted by the name used.
- `the doctor` in Jekyll-Hyde is Jekyll except six uses that stand for the
  doctor of the opening anecdote ("Sawbones") and for Lanyon; those are
  excluded. `the servant` is Poole in three uses only.
- Marianela: bare `Golfín` is Teodoro (the doctor); his brother is always
  `Carlos` or `Carlos Golfín`. `Penáguilas` is a surname shared by Francisco,
  Manuel, Pablo and Florentina: `señorita de Penáguilas` / `la de Penáguilas`
  is Florentina, `el señor de Penáguilas` and the three bare narrative uses
  are Francisco, `el señorito de Penáguilas` is Pablo. `la casa de Penáguilas`
  and `la señora de Penáguilas` (a dead wife) are left unassigned.
- Marianela: `María` alone is Nela (the heroine's baptismal name) unless
  `Virgen María`, `María Santísima` or `señá María Canela` (Nela's dead
  mother). `la hija de la Canela` and `la de la Canela` are Nela.
  `Mariquita` is Nela in two of its three uses (the third is a historical
  noblewoman in the closing note, listed as minor).
- Marianela: the Virgin Mary is kept as a character because the heroine
  talks to and about her throughout; addresses such as `Madre de Dios`,
  `Señora` and `Señor` used to her or to God are not counted.
- Generic descriptors that switch referent (`el joven`, `la muchacha`,
  `el chico`, `el señor`) are not aliases of anything.
- `Centeno` is Sinforoso Centeno except in `los esposos Centeno` (group),
  `Cilipín Centeno` (Celipín) and `la casa de Centeno`.
- `Madrid` and the heroine's `los Madriles` are one place. `Santa Irene de
  Campó` and `Campó` are one place.
- The gold is about discovery and reference counting, not coreference: it
  does not assign pronouns.

Counts are reproducible only through this method; if the text of a corpus
file changes (its checksum is in `source.toml`), regenerate the list.
