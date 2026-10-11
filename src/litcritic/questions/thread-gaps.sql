-- id = "thread-gaps"
-- title = "Is every storyline told continuously, or are there gaps?"
-- family = "threads"
-- params = { min_words = "smallest gap to list" }
-- defaults = { min_words = 1000 }
WITH passages AS (
  SELECT t.id AS thread, t.name, s.start_idx,
         (SELECT word0 FROM para_pos WHERE idx = s.start_idx) AS w0,
         (SELECT word0 + words FROM para_pos WHERE idx = s.end_idx) AS w1
  FROM v_thread t JOIN spans s ON s.item_id = t.id
  WHERE s.start_idx IS NOT NULL),
ordered AS (
  SELECT *, MAX(w1) OVER (PARTITION BY thread ORDER BY w0, w1
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS covered
  FROM passages)
SELECT name,
       (SELECT anchor FROM para_pos pp JOIN paragraphs p ON p.idx = pp.idx
        WHERE pp.word0 < covered ORDER BY pp.idx DESC LIMIT 1) AS after,
       (SELECT anchor FROM paragraphs WHERE idx = start_idx) AS resumes_at,
       w0 - covered AS gap_words
FROM ordered
WHERE covered IS NOT NULL AND w0 - covered >= :min_words
ORDER BY gap_words DESC, name;
