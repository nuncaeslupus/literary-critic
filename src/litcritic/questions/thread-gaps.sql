-- id = "thread-gaps"
-- title = "Is every storyline told continuously, or are there gaps?"
-- family = "threads"
-- params = { min_words = "smallest gap to list" }
-- defaults = { min_words = 1000 }
WITH passages AS (
  SELECT t.id AS thread, t.name, s.start_idx, s.end_idx,
         (SELECT word0 FROM para_pos WHERE idx = s.start_idx) AS w0,
         (SELECT word0 + words FROM para_pos WHERE idx = s.end_idx) AS w1
  FROM v_thread t JOIN spans s ON s.item_id = t.id
  WHERE s.start_idx IS NOT NULL),
ordered AS (
  SELECT *, LAG(w1) OVER (PARTITION BY thread ORDER BY w0) AS prev_end,
            LAG(end_idx) OVER (PARTITION BY thread ORDER BY w0) AS prev_idx
  FROM passages)
SELECT name,
       (SELECT anchor FROM paragraphs WHERE idx = prev_idx) AS after,
       (SELECT anchor FROM paragraphs WHERE idx = start_idx) AS resumes_at,
       w0 - prev_end AS gap_words
FROM ordered
WHERE prev_end IS NOT NULL AND w0 - prev_end >= :min_words
ORDER BY gap_words DESC, name;
