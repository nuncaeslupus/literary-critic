-- id = "expression-use"
-- title = "Am I overusing an expression? Uses per chapter."
-- family = "lexicon"
-- params = { expression = "one or more words" }
WITH w AS (
  SELECT phrase(:expression) AS e,
         length(phrase(:expression)) - length(replace(phrase(:expression), ' ', '')) + 1 AS n),
hits AS (
  SELECT t.para_idx FROM tokens t JOIN w ON w.n = 1 AND t.norm = w.e
  UNION ALL
  SELECT g.para_idx FROM ngrams g JOIN w ON w.n BETWEEN 2 AND 4 AND g.n = w.n AND g.norm = w.e
)
SELECT chapter, uses FROM (
  SELECT 'error: expressions of 1 to 4 words only' AS chapter, NULL AS uses, -1 AS k
  FROM w WHERE w.n > 4 OR w.e = ''
  UNION ALL
  SELECT p.chapter, COUNT(*), MIN(p.idx)
  FROM hits h JOIN paragraphs p ON p.idx = h.para_idx GROUP BY p.chapter)
ORDER BY k;
