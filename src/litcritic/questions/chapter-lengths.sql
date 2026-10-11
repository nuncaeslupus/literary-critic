-- id = "chapter-lengths"
-- title = "Which chapters are much longer or shorter than the rest?"
-- family = "structure"
-- params = {}
WITH s AS (SELECT AVG(words) AS mean, AVG(words * words) - AVG(words) * AVG(words) AS var
           FROM chapters WHERE id != 'c00')
SELECT c.id, c.title, c.words,
       CASE WHEN (c.words - s.mean) * (c.words - s.mean) > 2.25 * s.var
            THEN CASE WHEN c.words > s.mean THEN 'long' ELSE 'short' END ELSE '' END AS flag
FROM chapters c, s WHERE c.id != 'c00' ORDER BY c.idx;
