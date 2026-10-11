-- id = "character-absences"
-- title = "Which characters disappear for long stretches?"
-- family = "characters"
-- params = { min_words = "smallest absence to list" }
-- defaults = { min_words = 5000 }
WITH seen AS (
  SELECT DISTINCT m.entity_id, m.para_idx, pp.word0, pp.word0 + pp.words AS w1
  FROM mentions m JOIN para_pos pp ON pp.idx = m.para_idx),
total AS (SELECT SUM(words) AS w FROM paragraphs),
gaps AS (
  SELECT entity_id, 'between' AS kind,
         LAG(para_idx) OVER (PARTITION BY entity_id ORDER BY word0) AS last_idx, para_idx AS back_idx,
         word0 - LAG(w1) OVER (PARTITION BY entity_id ORDER BY word0) AS gap
  FROM seen
  UNION ALL
  SELECT entity_id, 'before first', NULL, MIN(para_idx), MIN(word0) FROM seen GROUP BY entity_id
  UNION ALL
  SELECT s.entity_id, 'after last', MAX(s.para_idx), NULL, (SELECT w FROM total) - MAX(s.w1)
  FROM seen s GROUP BY s.entity_id)
SELECT e.name, g.kind,
       (SELECT anchor FROM paragraphs WHERE idx = g.last_idx) AS last_seen,
       (SELECT anchor FROM paragraphs WHERE idx = g.back_idx) AS back_at, g.gap AS gap_words
FROM gaps g JOIN v_entity e ON e.id = g.entity_id
WHERE e.kind = 'character' AND g.gap >= :min_words
ORDER BY g.gap DESC, e.name;
