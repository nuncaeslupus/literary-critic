-- id = "never-together"
-- title = "Which main characters never share a scene?"
-- family = "relationships"
-- params = { min_mentions = "only characters mentioned at least this often" }
-- defaults = { min_mentions = 10 }
WITH main AS (
  SELECT e.id, e.name FROM v_entity e JOIN mentions m ON m.entity_id = e.id
  WHERE e.kind = 'character' GROUP BY e.id HAVING COUNT(*) >= :min_mentions)
SELECT a.name AS a, b.name AS b
FROM main a JOIN main b ON a.id < b.id
WHERE NOT EXISTS (SELECT 1 FROM copresence c WHERE c.a = a.id AND c.b = b.id)
ORDER BY a.name, b.name;
