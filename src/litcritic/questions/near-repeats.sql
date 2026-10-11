-- id = "near-repeats"
-- title = "Which words are repeated close together?"
-- family = "lexicon"
-- params = { window = "tokens apart", min_len = "shortest word to consider" }
-- defaults = { window = 12, min_len = 5 }
WITH r AS (
  SELECT a.norm AS word, COUNT(*) AS times, MIN(a.para_idx) AS lo
  FROM tokens a JOIN tokens b
    ON b.para_idx = a.para_idx AND b.norm = a.norm AND b.pos > a.pos AND b.pos - a.pos <= :window
  WHERE a.is_word = 1 AND length(a.norm) >= :min_len
  GROUP BY a.norm)
SELECT r.word, r.times, p.anchor AS first_at
FROM r JOIN paragraphs p ON p.idx = r.lo
ORDER BY r.times DESC, r.word;
