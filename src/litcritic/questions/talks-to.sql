-- id = "talks-to"
-- title = "Who talks to whom, and how often?"
-- family = "relationships"
-- params = {}
SELECT s.name AS speaker, COALESCE(a.name, '(unknown)') AS addressee, COUNT(*) AS lines
FROM v_dialogue d JOIN v_entity s ON s.id = d.speaker
LEFT JOIN v_entity a ON a.id = d.addressee
GROUP BY d.speaker, d.addressee ORDER BY lines DESC;
