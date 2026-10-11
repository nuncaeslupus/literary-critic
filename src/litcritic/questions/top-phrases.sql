-- id = "top-phrases"
-- title = "Which phrases recur across the book?"
-- family = "lexicon"
-- params = { n = "words per phrase", min_uses = "fewest uses to list" }
-- defaults = { n = 3, min_uses = 3 }
SELECT phrase, uses, chapters FROM (
  SELECT 'error: n must be 2, 3 or 4' AS phrase, NULL AS uses, NULL AS chapters
  WHERE :n NOT BETWEEN 2 AND 4
  UNION ALL
  SELECT norm, COUNT(*), COUNT(DISTINCT p.chapter)
  FROM ngrams g JOIN paragraphs p ON p.idx = g.para_idx
  WHERE g.n = :n GROUP BY norm HAVING COUNT(*) >= :min_uses)
ORDER BY uses IS NULL DESC, uses DESC, phrase;
