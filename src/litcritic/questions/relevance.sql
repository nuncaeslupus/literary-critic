-- id = "relevance"
-- title = "Which characters matter most to a given character?"
-- family = "relationships"
-- params = { character = "entity id or name" }
WITH who AS (SELECT id FROM v_entity WHERE id = :character OR norm(name) = norm(:character)),
together AS (
  SELECT CASE WHEN a IN (SELECT id FROM who) THEN b ELSE a END AS other, COUNT(DISTINCT scene) AS n
  FROM copresence WHERE a IN (SELECT id FROM who) OR b IN (SELECT id FROM who)
  GROUP BY other),
talks AS (
  SELECT CASE WHEN speaker IN (SELECT id FROM who) THEN addressee ELSE speaker END AS other,
         COUNT(*) AS n
  FROM v_dialogue
  WHERE (speaker IN (SELECT id FROM who) AND addressee IS NOT NULL)
     OR addressee IN (SELECT id FROM who)
  GROUP BY other)
SELECT e.name, COALESCE(s.n, 0) AS scenes_together, COALESCE(t.n, 0) AS exchanges,
       COALESCE(s.n, 0) + 2 * COALESCE(t.n, 0) AS score
FROM v_entity e
LEFT JOIN together s ON s.other = e.id
LEFT JOIN talks t ON t.other = e.id
WHERE e.kind = 'character' AND e.id NOT IN (SELECT id FROM who)
  AND COALESCE(s.n, 0) + COALESCE(t.n, 0) > 0
ORDER BY score DESC, e.name;
