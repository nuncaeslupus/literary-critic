-- id = "speech-chapters"
-- title = "In how many chapters does a character speak?"
-- family = "characters"
-- params = { character = "entity id or name" }
WITH who AS (SELECT id FROM v_entity WHERE id = :character OR norm(name) = norm(:character))
SELECT COUNT(DISTINCT p.chapter) AS chapters, group_concat(DISTINCT p.chapter) AS which
FROM v_dialogue d JOIN paragraphs p ON p.idx = d.para_idx
WHERE d.speaker IN (SELECT id FROM who);
