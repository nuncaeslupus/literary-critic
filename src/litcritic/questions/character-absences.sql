-- id = "character-absences"
-- title = "Which characters disappear for long stretches?"
-- family = "characters"
-- params = { min_words = "smallest absence to list" }
-- defaults = { min_words = 5000 }
WITH seen AS (
  SELECT DISTINCT m.entity_id, m.para_idx, pp.word0 FROM mentions m
  JOIN para_pos pp ON pp.idx = m.para_idx),
gaps AS (
  SELECT entity_id, para_idx, word0 - LAG(word0) OVER (PARTITION BY entity_id ORDER BY word0) AS gap,
         LAG(para_idx) OVER (PARTITION BY entity_id ORDER BY word0) AS prev
  FROM seen)
SELECT e.name, (SELECT anchor FROM paragraphs WHERE idx = g.prev) AS last_seen,
       (SELECT anchor FROM paragraphs WHERE idx = g.para_idx) AS back_at, g.gap AS gap_words
FROM gaps g JOIN v_entity e ON e.id = g.entity_id
WHERE e.kind = 'character' AND g.gap >= :min_words
ORDER BY g.gap DESC;
