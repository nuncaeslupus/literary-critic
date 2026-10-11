-- id = "top-phrases"
-- title = "Which phrases recur across the book?"
-- family = "lexicon"
-- params = { n = "words per phrase", min_uses = "fewest uses to list" }
-- defaults = { n = 3, min_uses = 3 }
SELECT norm AS phrase, COUNT(*) AS uses, COUNT(DISTINCT p.chapter) AS chapters
FROM ngrams g JOIN paragraphs p ON p.idx = g.para_idx
WHERE g.n = :n GROUP BY norm HAVING COUNT(*) >= :min_uses
ORDER BY uses DESC, phrase;
