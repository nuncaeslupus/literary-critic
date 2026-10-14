-- id = "dialogue-share"
-- title = "What share of each chapter is dialogue?"
-- family = "dialogue"
-- params = {}
SELECT c.id, c.words, COALESCE(SUM(d.words), 0) AS dialogue_words,
       ROUND(100.0 * COALESCE(SUM(d.words), 0) / MAX(c.words, 1), 1) AS percent
FROM chapters c LEFT JOIN paragraphs p ON p.chapter = c.id
LEFT JOIN speech d ON d.para_idx = p.idx
GROUP BY c.id ORDER BY c.idx;
