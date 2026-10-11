-- id = "expression-use"
-- title = "Am I overusing an expression? Uses per chapter."
-- family = "lexicon"
-- params = { expression = "one or more words" }
WITH q AS (SELECT norm(:expression) AS e),
w AS (SELECT e, length(e) - length(replace(e, ' ', '')) + 1 AS n FROM q),
hits AS (
  SELECT t.para_idx FROM tokens t JOIN w ON w.n = 1 AND t.norm = w.e
  UNION ALL
  SELECT g.para_idx FROM ngrams g JOIN w ON w.n > 1 AND g.n = w.n AND g.norm = w.e
)
SELECT p.chapter, COUNT(*) AS uses
FROM hits h JOIN paragraphs p ON p.idx = h.para_idx
GROUP BY p.chapter ORDER BY MIN(p.idx);
