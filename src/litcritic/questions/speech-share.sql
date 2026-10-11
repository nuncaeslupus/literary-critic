-- id = "speech-share"
-- title = "How much does each character speak, in lines and words?"
-- family = "dialogue"
-- params = {}
SELECT e.name, COUNT(*) AS lines, SUM(d.words) AS words
FROM v_dialogue d JOIN v_entity e ON e.id = d.speaker
GROUP BY e.id ORDER BY words DESC, e.name;
