-- id = "character-appearances"
-- title = "When does each character first and last appear, and how often?"
-- family = "characters"
-- params = {}
WITH c AS (
  SELECT m.entity_id, COUNT(*) AS mentions, MIN(m.para_idx) AS lo, MAX(m.para_idx) AS hi
  FROM mentions m GROUP BY m.entity_id)
SELECT e.name, c.mentions, f.anchor AS first, l.anchor AS last
FROM c JOIN v_entity e ON e.id = c.entity_id
JOIN paragraphs f ON f.idx = c.lo JOIN paragraphs l ON l.idx = c.hi
WHERE e.kind = 'character'
ORDER BY c.mentions DESC, e.name;
