# Analysis frameworks for LLM manuscript critique: raw material for a check catalogue

Scope: generic (any genre, any language). Tags: **[S]** script-measurable, **[L]** LLM-judged, **[H]** hybrid (script finds candidates or computes a signal, LLM interprets). Items marked (heuristic) come from craft-practice consensus, not a single citable study. Treat every numeric threshold as a prompt for inspection, never a verdict.

---

## 1. Editing levels and editor workflow

**Levels (order matters; do big things first, small things last).**
1. Manuscript assessment / critique: short, high-level verdict; letter only, little or no marginalia. Suits early drafts.
2. Developmental (structural/substantive) edit: structure, plot or argument, pacing, character, POV, theme, worldbuilding, genre fit. Delivered as an editorial letter, often plus margin comments or a scene/chapter map.
3. Line edit: sentence-level style, voice, rhythm, clarity, redundancy, word choice.
4. Copyedit: grammar, spelling, punctuation, consistency (names, dates, spelling variants), fact-check flags, style sheet.
5. Proofread: final typos/layout after typesetting.
Terminology is not uniform across editors and agencies. Rule shared by all sources: never polish prose (3-5) in scenes that structural edits may cut.

**Implication for the tool.** Output must be tiered: (A) book-level diagnosis, (B) chapter/scene-level actions, (C) line-level patterns with examples. Never lead with typos or tics. Suppress copyedit noise unless asked.

**Editorial letter anatomy (typical, 3-10 pages).**
- Opening: brief, specific praise of what works (genuine strengths the writer should protect), plus a one-paragraph read of what the book is trying to be (premise, genre, intended reader). This proves the manuscript was understood.
- Big-picture issues, ranked by impact (typically 3-7): each = observation, evidence (scenes/chapters), why it matters to the reader, concrete fix options. Order: structure/premise/stakes, character arc and motivation, plot causality, pacing, POV/voice, theme, worldbuilding.
- Secondary issues: subplots, secondary characters, setups/payoffs, continuity, dialogue, recurring prose habits (3-5 representative examples, not exhaustive lists).
- Revision plan: ordered steps ("fix the midpoint before touching chapter 3"), what to leave alone, optional scene-by-scene notes appended.
- Tone: diagnose the reading experience ("I lost track of what she wants in ch. 12-18"), not the writer; offer options, not a single mandated fix; distinguish "problem" from "preference".
- Prioritisation heuristics: issues that cause downstream rewrites rank first; issues present in many chapters become one pattern note; limit total headline problems so the writer can act.

**Action format for the tool** (each finding): `area | severity (blocker/major/minor) | location | evidence quote | why it hurts the reader | 1-3 revision actions | confidence | measurable? `. Add a "confidence/uncertainty" field because LLM structural judgments over long text are fallible; require quote-backed evidence.

---

## 2. Check areas

### 2.1 Structure (macro)
Questions:
- Can the book be summarised as inciting disruption -> escalating complications -> crisis -> climax -> resolution (or the genre's equivalent)? Where is each beat, as % of word count? [H]
- Is there a clear protagonist goal/question that organises the book (dramatic question)? When is it posed and when answered? [L]
- Do the major turning points change the situation irreversibly, and do they escalate (rising stakes, narrowing options)? [L]
- Is there a midpoint shift (reversal, revelation, false victory/defeat) that changes the strategy of the protagonist? (Optional; see limits.) [L]
- Does the "all is lost"/lowest point follow from the protagonist's own choices and flaw? [L]
- Do proportions look plausible (Act I roughly 20-25%, middle 50%, final 25%) and are deviations deliberate? [H, positions by script, judgment by LLM]
- Chapter/scene inventory: summary, POV, location, time, goal, conflict, outcome, value shift. [H]
Failure symptoms: sagging middle (episodic, repeated confrontation type); late inciting incident (>25-30% before anything changes); climax unprepared or diminished by earlier bigger set pieces; resolution that undoes the arc; protagonist passive at turning points (things happen to them); multiple competing spines with no hierarchy.

### 2.2 Opening
- Does page 1 / first chapter establish voice, a person with a problem or desire, a sense of genre, and a reason to turn the page (question, tension, promise)? [L]
- Is time/place/person oriented fast enough without front-loaded backstory? [H]
- Does the opening promise match what the book delivers (tone, genre, stakes)? [L]
- Does the first chapter pose the central or an early dramatic question? [L]
Symptoms: weather/waking-up/mirror openings; prologue that is info dump; protagonist reflecting instead of acting; cast flood in ch. 1; mismatch of tone with rest of book. Script aid: count named characters and proper nouns introduced in first N words; dialogue/action vs exposition ratio in the first 2,000 words [S].

### 2.3 Ending
- Is the central question answered, and is it earned by choices made in the final act? [L]
- Is the protagonist's internal change (or deliberate refusal to change) shown in a decisive action? [L]
- Are major threads and promises (genre, setups) paid off or consciously left open? [H]
- Emotional register of the last chapter fits the book's promise; resolution is neither rushed (deus ex machina, summary) nor over-extended (multiple false endings, epilogue that re-explains). [L]
- Final image resonates with opening/theme. [L]
Symptoms: coincidence-driven rescue; antagonist defeated offstage; tone shift; last 5% is summary; unresolved subplots without intent. Script: proportion of text after the climax scene (denouement length), summary-vs-scene ratio in final chapters [H].

### 2.4 Pacing
- Scene/chapter length distribution; are long stretches of similar mode (all dialogue, all introspection, all travel)? [S]
- Does tension vary (peaks and valleys, sequel/reaction beats after high points)? [H]
- Is each scene's information/emotion new, or does it repeat a previous scene's function? [L]
- Speed of time: ratio of scene (real-time) to summary, and whether summary is used for dull parts and scene for pivotal ones. [H]
- Does the story start late, end early within scenes (enter late, leave early)? [L]
Symptoms: front-loaded setup, slow first quarter; rushed ending; every chapter ends on the same hook type; stasis scenes (characters discuss what they will do); repeated recap of known facts. Measurable proxies: scene length variance, sentence-length trend by chapter, dialogue ratio by chapter, "action verb" density, proportion of text in summary mode (LLM-tagged) [S/H].

### 2.5 Plot causality
- Does each major event follow from a prior event/choice ("therefore/but", not "and then")? [L]
- Are character decisions plausible given established motives and knowledge? [L]
- Who knows what when (information ledger); do characters act on information they lack? [H]
- Is the antagonist's plan/force coherent and active, and do protagonist actions have consequences? [L]
- Coincidences: do they get the protagonist into trouble (acceptable) or out of it (weak)? [L]
- Mystery/puzzle plots: fair-play clues, red herrings, solution derivable. [L]
Symptoms: plot holes; characters stupid for plot's sake; convenient exposition; timeline impossibilities; stakes asserted not shown; resolution via deus ex machina.

### 2.6 Setups and payoffs
- Extract all promises (Chekhov's gun objects, foreshadowing, prophecies, questions raised, skills introduced, rules of magic/tech) and track payoff chapter. [H: LLM extraction, script ledger/distance]
- Unfired guns (introduced prominently, never used); unprepared payoffs (solution uses an unmentioned ability/object); payoff too close to setup (obvious) or too far (forgotten). [H]
- Red herrings: deliberate or accidental? [L]
Output: table `promise | introduced at | paid at | status (paid/dangling/unplanted)`.

### 2.7 Subplots and secondary threads
- Does each subplot have its own want/obstacle/outcome and touch the main plot (cause, mirror, complicate, or thematically counterpoint)? [L]
- Distribution: where does each thread appear and disappear (gaps > ~25% of the book)? [H]
- Are subplots resolved before or at the main climax, or converge in it? [L]
Symptoms: orphan threads; subplot only delays; secondary POV chapters that restate main plot; cast bloat.

### 2.8 Character (protagonist and cast)
- Want (conscious goal) vs need (unconscious lack/flaw/lie); is the gap shown and does it drive choices? Note: Not all stories use want/need or lie/truth. [L]
- Arc type: positive change, negative/tragic, flat/testing arc (character holds truth and changes the world), static/episodic; is the chosen arc executed consistently? [L]
- Agency: share of key turning points caused by protagonist decisions. [L]
- Stakes: what does the protagonist lose if they fail, is it personal as well as external? [L]
- Contradictions/specificity: distinct voice, habits, history that influence choices; avoidance of types. [L]
- Antagonist: coherent motive, capability, own logic; opposes protagonist's specific want. [L]
- Consistency: behaviour out of character without cause. [H]
- Cast economy: number of named characters, first-appearance clustering, characters with overlapping functions or near-identical names (similar initials) [S for counts/names, L for function].
Symptoms: passive protagonist; unmotivated change; telling traits vs showing choices; "perfect" or flawless hero; villain monologue; interchangeable secondary characters; an arc resolved by a speech.

### 2.9 Relationships
- Central relationship(s) have an evolution (attraction/conflict/escalation/crisis/resolution) with causal scenes, not just stated feeling. [L]
- Do relationship shifts coincide with plot turns? [L]
- Power dynamics, chemistry, subtext in interactions; are conflicts about something specific? [L]
- Genre-specific (romance: meet, barrier, intimacy escalation, black moment, commitment). [L]
Symptoms: told-not-shown affection, sudden love/hate, conflict created by miscommunication that a sentence would solve.

### 2.10 POV, voice, narrative distance
- Which POV (first, close third, omniscient, second; single or multiple)? List POV per scene and check consistency. [H: script flags pronoun/name patterns, LLM confirms]
- Head-hopping within scenes; POV characters whose perception is violated (knowing what they cannot). [L/H]
- Psychic distance (Gardner): ladder from distant ("It was winter of 1941") to deep interior; is distance deliberately modulated and matched to emotion? [L]
- Filter words / perception verbs (saw, felt, noticed, realised, wondered, seemed) as distance-creating habit. [S density, L judgement]
- Voice distinctiveness between POV characters; narrator reliability; tense consistency (accidental shifts). [H]
- Multiple POV: does each POV earn its place, balanced share, introduced early enough? [H: share of words per POV by script]
Symptoms: unmotivated omniscient intrusions; all POV characters sound alike; info the POV character would not think; tense drift.

### 2.11 Scene craft
- For each scene: whose goal, what opposes, what changes (value shift: positive/negative, e.g. safe->danger), what is the turning point, does it end with a different situation from its start? (Story Grid/McKee test; if no value changes, scene is candidate for cut/merge.) [L, on tagged scene list]
- Scene vs sequel (Swain): action scenes (goal, conflict, disaster) followed by reaction (emotion, dilemma, decision) — present where needed? [L]
- Entry and exit points, hooks, scene transitions, orientation (who/where/when in first paragraph). [H]
- Does the scene use all channels: dialogue, action, interior, setting, with subtext? [L]
- Redundant function (two scenes doing the same job). [L]
Symptoms: scenes of pure conversation/exposition; "waking-up" and "travelling" scenes; endings without consequence; arrival/departure padding.

### 2.12 Setting and worldbuilding
- Is place concrete and used (affects action, mood, conflict), or generic? [L]
- Rules of the world (magic, tech, society, institutions) established before use, consistent, with costs and limits. [H]
- Exposition delivery: dosage, in-scene integration vs lecture; terms introduced per chapter (new proper-noun density) [S]. 
- Period/cultural plausibility, anachronism, language register fit. [L]
- Sensory range (sight-dominance only?). [H]
Symptoms: info-dump prologue, glossary-dependence, invented terms >N per page, worldbuilding contradicting itself, "white room" dialogue.

### 2.13 Theme and motif
- What does the book argue or ask? Is it embodied in plot choices and consequences rather than stated? [L]
- Recurring images/motifs/symbols: list, frequency, placement, evolution (do they change meaning at the climax?). [H: script counts lexical recurrence, LLM interprets]
- Do character arcs, subplots and ending reinforce or contradict the thematic position? [L]
- Preachiness: characters or narrator stating the moral. [L]
Symptoms: theme only stated in a speech; motif over-repeated mechanically; ending contradicts theme without intention.

### 2.14 Dialogue
- Distinct speaker voices (diction, rhythm, length); can lines be attributed without tags? [H]
- Subtext: do characters want things from each other, avoid, interrupt, lie? [L]
- "As you know, Bob" exposition, on-the-nose emotion statements, small talk padding. [L]
- Tags and beats: said-bookisms, adverb-laden tags, excess of beats, floating dialogue without grounding. [S]
- Dialogue ratio per chapter, average line length, long speeches (> ~150 words). [S]
- Punctuation convention consistency (English quotes vs Spanish raya/em-dash style, guillemets). [S]
Symptoms: everyone same register; talking heads; information delivered via dialogue only; unrealistic completeness.

### 2.15 Prose and style (line-level patterns, report as patterns with examples)
- Filter words, weak verbs, adverbs (-ly / -mente), stacked adjectives, nominalisations. [S/H]
- Telling vs showing: emotion labelled ("she felt sad") in place of dramatised. Not a rule: summary is legitimate. [L]
- Info-dumps and backstory blocks: long passages with past perfect/ no scene action. [H]
- Repetition: repeated words/phrases within windows, repeated sentence openers, repeated gestures (nodded, sighed, smiled, shrug, "suspiró"), repeated similes/images, character tics, n-gram recurrence across book. [S]
- Rhythm: sentence-length variance, runs of same structure, paragraph length. [S]
- Clichés, purple prose, mixed metaphors, unintended rhyme/echo. [L/H]
- Lexical range and register consistent with narrator/era. [S/L]
- Passive voice density (language dependent; weak signal). [S]
- Consistency of tense, spelling variant (UK/US; es-ES/es-MX), punctuation, italics. [S]
Symptoms: reader fatigue from same-structure sentences; emotional flatness; over-explaining. 

### 2.16 Continuity and consistency
- Characters: name, age, appearance, eye colour, relationships, backstory, skills, injuries over time. [H: LLM extracts facts, script compares]
- Timeline: dates, seasons, day/night, travel durations, ages vs events. [H]
- Geography/layout, object location, who is present in a scene. [H]
- Name variants and spelling drift; minor characters renamed. [S]
- Facts revealed vs previously stated; rules of the world. [H]
- Knowledge continuity (see 2.5). 
Output: fact-ledger with first mention and contradictions; severity by prominence.

### 2.17 Genre conventions and market
- Which genre/subgenre/shelf and what promises does it make to readers (e.g. romance: HEA/HFN; mystery: solvable puzzle and justice; thriller: ticking clock, escalating threat; fantasy/SF: wonder, coherent rules; horror: dread and violation; literary: interiority, language, ambiguity tolerated)? Are core obligatory scenes present (Story Grid)? [L]
- Subversions: deliberate and recognisable or accidental? [L]
- Tropes: used freshly or as unexamined cliché? [L]
- Length vs category norms (see 3.6). [S]
- Comparable titles; target reader; hook/premise strength ("what if" clarity); content and tone signals for readers. [L]
- Opening/pacing conventions per genre (e.g. thrillers start fast; literary can start slowly). [L]
Note: judge against the genre the book wants to be, which the tool should ask or infer and state as an assumption.

### 2.18 Reader experience (beta-reader style questions)
Ask the LLM to simulate or report, with evidence and "confidence":
- Where would a reader likely get bored, confused, or stop? Mark by chapter. 
- Where does emotional engagement peak or flatten (empathy for protagonist, fear, laughter, grief)? 
- Which questions does the reader hold at each point (mysteries, hopes, fears)? Are they ever answered?
- Which characters/scenes are most memorable; which are forgettable?
- Moments of disbelief ("I don't buy this").
- Confusion map: unclear who/where/when, unclear motivations, unclear stakes.
- Would the reader recommend; what is the one-line takeaway they would give?
Also: sensitivity/representation (stereotypes, trauma handling, cultural accuracy, language of marginalised groups, content to flag), consistency of portrayal, accessibility of dialect rendering. [L; flag for human/sensitivity-reader verification rather than certify.]

---

## 3. Measurable metrics (script)

### 3.1 Structural and size
- Word count (total, per chapter, per scene); chapter count; scene breaks (detected by blank-line/`***`/heading markers). Chapter length mean, SD, coefficient of variation, min/max. Long outliers (> 2x median) flagged.
- Positional metrics: normalise to % of word count for events located by LLM.
- Character/proper-noun counts by chapter, first appearance positions, name collision (same initial/Levenshtein distance).
- POV share (words per POV character), once POV tags exist.

### 3.2 Readability
- **Flesch Reading Ease (English):** 206.835 - 1.015 * (words/sentences) - 84.6 * (syllables/words). Higher = easier. Typical commercial fiction sits roughly in 70-90; literary and dense prose lower. (heuristic; formula standard.) Flesch-Kincaid Grade: 0.39*(W/S) + 11.8*(syl/W) - 15.59. Fiction scores are weakly informative (dialogue fragments, one-word sentences); use per-chapter variation, not absolute.
- **Fernández-Huerta (Spanish, 1959):** 206.84 - 0.60*P - 1.02*F, where P = syllables per 100 words, F = sentences per 100 words.
- **Szigriszt-Pazos (Spanish, 1993; "perspicuidad", Flesch-Szigriszt):** 206.835 - 62.3*(syllables/words) - (words/sentences). Calibrated on Spanish corpora.
- **INFLESZ scale (Barrio-Cantalejo et al., 2008)** interprets Szigriszt-Pazos: < 40 muy difícil; 40-55 algo difícil; 55-65 normal; 65-80 bastante fácil; > 80 muy fácil. It was designed for health/educational texts (55 as the "adequate" cut-off) — for fiction treat as a relative gauge; literary Spanish often legitimately scores 50-60.
- Syllable counting for Spanish is rule-based (hiatus/diphthong rules; tools like `textstat` have Spanish support: `fernandez_huerta`, `szigriszt_pazos`, `gutierrez_polini`, `crawford`). Readability formulas ignore vocabulary rarity, syntax depth and content; never present as quality.
- Language note: formulas are language-specific. Do not apply English Flesch to Spanish (syllables per word are higher in Spanish and the scale shifts downward). For other languages, use language-specific or language-agnostic proxies (sentence length, word length, lexical diversity).

### 3.3 Sentences and rhythm
- Mean/median sentence length, SD, coefficient of variation, percentiles (P90), share of very long (> 40 words in English; > 50 in Spanish where longer sentences are conventional) and very short (< 5) sentences; runs of N consecutive sentences within +/-20% of the same length (monotony); sentence-opener repetition (share starting with the same word/pronoun/name); paragraph length distribution. Interpret per chapter relative to the book's own baseline (deviation scoring), not to a universal threshold.

### 3.4 Lexical diversity and repetition
- **TTR** is length-dependent; do not compare across chapters of different length. Use **MTLD** (McCarthy 2005; McCarthy & Jarvis 2010): sequentially scan tokens, count a "factor" each time the running TTR drops to 0.72; MTLD = tokens / factors, computed forward and backward and averaged (partial factors included). Recommended threshold range 0.66-0.75, 0.72 default. Also **HD-D** and **MATTR** (window e.g. 100-500 tokens) as length-robust alternatives. Higher = more varied; compare chapter vs book and vs genre peers; do not set an absolute pass/fail (web calculators' bands are unsourced). Lemmatise first, especially for inflected languages like Spanish.
- Repetition: frequency of content-word lemmas excluding stopwords, repeats within sliding windows (e.g. same non-stopword within 50-100 words), repeated n-grams (3-6 grams) across the book, repeated sentence openers, character "tics" (gestures, reaction verbs), echo detection of rare words within short distance. Report top-N with locations.
- Crutch-word lists per language (English: just, very, really, suddenly, seemed, began to, started to, that, only; Spanish: de repente, empezar a, comenzar a, muy, como si, pareció, un poco, algo, cosa, de pronto, mirar, sonreír, suspirar).

### 3.5 Style-specific densities
- **Adverbs:** English -ly adverbs per 1,000 words (flag clusters and in dialogue tags); Spanish **-mente** adverbs per 1,000 words. Common editorial advice (heuristic): sparing use, with no hard threshold in sources; compute per-chapter against book median and flag > ~2 SD.
- **Filter/perception words** per 1,000 words (saw, heard, felt, noticed, realised, watched, wondered, seemed; Spanish: ver/vio, sentir/sintió, notar, darse cuenta, parecer, oír).
- **Passive voice** (English be + past participle; Spanish "ser + participio" and pasiva refleja "se + verb"): weak signal; Spanish passive is rarer and often stylistic.
- **Dialogue ratio:** characters inside quotation marks (or after raya / within « ») / total characters or words, per chapter. Genre norms are loose; commercial fiction commonly 30-50% dialogue (heuristic, practitioner lore). Flag chapters at extremes (< 5% or > 80%) and long runs without either dialogue or action. Mind typographic conventions: Spanish dialogue marked with raya (—), possibly no closing mark; detection must be configurable.
- **Dialogue tags:** share of "said/dijo" vs fancy verbs; adverb-modified tags.
- **Info-dump proxy:** long paragraphs (> 250 words) without dialogue and with low verb-of-action share; high proper-noun/new-term density in a chapter.
- **Sensory words** lexicon counts by modality (hybrid).
- **Emotion naming** ("felt sad", "se sintió triste") counts (S candidate + LLM judge of show vs tell).
- **Tense/person consistency:** share of past vs present verbs per scene (POS tagging, spaCy/Stanza), person pronouns per chapter.
- **Sentiment arc** (lexicon/model-based) per chapter or window as a rough emotional/valence trajectory (hybrid, noisy; use for hypothesis only).

### 3.6 Typical word-count ranges (English-language trade publishing, heuristic; vary by source and market)
- Adult general/literary: ~70,000-100,000. Debut sweet spot ~80,000-90,000.
- Commercial/thriller/mystery: ~70,000-100,000 (cozy ~60,000-80,000).
- Romance: ~50,000-90,000 (category lines shorter, 50-60k).
- Science fiction/fantasy: ~90,000-120,000 (epic fantasy up to ~150k; debuts above ~120k are a hard sell).
- YA: ~50,000-80,000 (fantasy YA more). Middle grade: ~30,000-55,000.
- Horror ~70,000-90,000. Historical ~80,000-110,000.
Other markets/languages differ; self-publishing and serial formats ignore many of these. Report as "outside typical range for stated genre: market consideration, not a quality defect".

### 3.7 Tools
spaCy/Stanza (tokens, lemmas, POS, NER, dependency), `textstat` (readability incl. Spanish), `lexicalrichness` / `koRpus` (MTLD, HD-D, MATTR), regex lists, custom scene splitter. For long manuscripts, chunk by chapter and aggregate; LLM tasks per chapter produce structured JSON (summary, POV, goal, conflict, outcome, value shift, setups, facts) that scripts then analyse across the book (map -> reduce).

---

## 4. Frameworks summary

| Framework | Good for | When NOT to use / limits |
|---|---|---|
| Three-act (Aristotle; Syd Field; Freytag pyramid as five-part variant) | Quick macro-check of setup/confrontation/resolution proportions; Western commercial and drama; tragedy (Freytag) | Forced onto episodic, ensemble, quiet literary, cyclical or non-Western works; proportions are descriptive not laws; Freytag fits tragedy, poorly fits modern multi-thread novels |
| Save the Cat (Snyder/Cron; 15 beats) | Commercial genre and screenplay-like pacing; spotting missing beats (midpoint, "all is lost", break into two) | Formulaic if used as mandate; screenplay lengths; poor fit for literary/experimental or multi-protagonist works |
| Story Grid (Coyne): five commandments (inciting incident, progressive complications, crisis, climax, resolution), genre obligatory scenes and conventions, value shifts, scene analysis, foolscap spreadsheet | Scene-level diagnosis at any scale, genre promise check, finding scenes without value change | Heavy vocabulary; works best on genres with codified conventions; risk of mechanical scoring on loose structures |
| McKee (Story): value shift, gap between expectation and result, scene as turning point | Scene function test; "does anything change" | Over-applies to atmospheric or meditative scenes where change is subtle/accumulative |
| Truby (22 steps; moral argument, desire/need, weakness) | Character-plot integration, premise and moral argument, designing before drafting | Elaborate; prescriptive ordering; heavy for diagnosis of already finished books; Western moral-change assumption |
| Swain scene/sequel (goal-conflict-disaster; reaction-dilemma-decision) | Rhythm of action and reaction, motivation clarity, pacing diagnosis | Rigid for modern interwoven prose; many scenes combine both |
| Hero's Journey (Campbell/Vogler) / Dan Harmon circle | Myth, adventure, quest; reading inner transformation in epic structures | Over-fits; Campbell critiques (male, monomyth); not general |
| Kishotenketsu (ki-sho-ten-ketsu: introduction, development, twist, reconciliation) | Stories organised by juxtaposition/perspective shift rather than conflict; East Asian narrative, slice of life, short forms; avoids imposing conflict as the engine | Contested as a literal historical "plot model" outside Chinese/Japanese/Korean poetic origin; rarely a complete novel model |
| Freytag's pyramid | Classic dramatic arc vocabulary (exposition, rising action, climax, falling action, denouement) | Tragedy-centric, symmetrical shape rarely matches modern novels |
| Want/need, lie/truth (Weiland, Maass), arc types (positive, negative, flat/testing, static) | Character arc diagnosis | Not all protagonists have internal lies; flat arcs invert it (character holds truth, world changes) |
| Gardner psychic distance; free indirect discourse | POV/distance diagnosis, filter words | Descriptive, not prescriptive; distant narration is legitimate in some genres/voices |
| Chekhov's gun / foreshadowing | Setup-payoff ledger | Not every detail must pay off (atmosphere, realism, red herrings) |
| Dramatica / Snowflake / Seven-point | Planning; consistency of throughlines | Mostly plotting tools; limited as post-draft critique |
| Reader-response / beta-reader questions | Experience mapping (engagement, confusion) | Subjective; sample bias; LLM simulation of "a reader" is an approximation |

Meta-rules for the tool: (1) first identify the book's own form (genre, structure model, intended effect) and critique against that; (2) report structure frameworks as lenses ("under a three-act lens the midpoint is missing; under kishotenketsu the 'ten' is strong"), never as mandatory; (3) distinguish rule-breaking by design from execution failure; (4) in non-Western or experimental works, switch to checks of coherence, escalation of meaning, and effect, rather than conflict beats; (5) language and culture: dialogue conventions, sentence length norms, formality registers, honorifics and punctuation differ by language.

---

## 5. Sources

Editing and workflow
- https://reedsy.com/editing/developmental-editing
- https://fictionary.co/journal/developmental-editing
- https://www.editorworld.com/article/manuscript-critique-vs-editorial-letter-vs-developmental-edit
- https://www.adeptghostwriting.com/blog/developmental-editing-vs-copy-editing-whats-the-difference/
- https://www.tckpublishing.com/developmental-editing/
- https://shewrites.com/?p=1561

Readability (Spanish/English)
- https://www.screamingfrog.co.uk/blog/readability-of-spanish-texts-alternative-metrics-to-flesch/
- https://readabilityformulas.com/readability-formulas-to-score-spanish-texts/
- https://recyt.fecyt.es/index.php/ASSN/article/download/1953/1390/3366
- https://repositori.uji.es/xmlui/bitstream/handle/10234/167245/marti.pdf?sequence=1
- https://pypi.org/project/textstat

Lexical diversity
- https://metacpan.org/pod/Lingua::Diversity::MTLD
- https://rdrr.io/cran/koRpus/man/lex.div-methods.html
- https://lexicalrichness.readthedocs.io/en/latest/example.html
- McCarthy, P. & Jarvis, S. (2010), "MTLD, vocd-D, and HD-D", Behavior Research Methods 42(2) (paper cited via the above)

Frameworks (from established craft literature; not re-fetched this session, cite books)
- Coyne, S., The Story Grid (five commandments, genre conventions, scene analysis) — https://storygrid.com
- McKee, R., Story (value shifts, gap)
- Truby, J., The Anatomy of Story (22 steps) — https://truby.com
- Snyder, B., Save the Cat; Cron, L., Story Genius / Wired for Story
- Swain, D., Techniques of the Selling Writer (scene/sequel)
- Gardner, J., The Art of Fiction (psychic distance)
- Freytag, G., Die Technik des Dramas (1863)
- Weiland, K.M., Creating Character Arcs (positive/negative/flat arcs)
- Kishotenketsu overview — https://en.wikipedia.org/wiki/Kish%C5%8Dtenketsu
- Chekhov's gun — https://en.wikipedia.org/wiki/Chekhov%27s_gun

Caveats: word-count ranges, dialogue ratios and density thresholds in section 3 are practitioner heuristics (agent forums, editors' blogs), not peer-reviewed norms; INFLESZ attribution/dates vary between sources (INFLESZ built on Szigriszt-Pazos by Barrio-Cantalejo et al., c. 2008).
