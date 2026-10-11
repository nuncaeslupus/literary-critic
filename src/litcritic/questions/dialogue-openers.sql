-- id = "dialogue-openers"
-- title = "Are dialogue lines opened the same way throughout?"
-- family = "mechanics"
-- params = {}
SELECT CASE WHEN text GLOB '--*' THEN '--' WHEN text GLOB '—*' THEN '—' WHEN text GLOB '-*' THEN '-'
            WHEN text GLOB '«*' THEN '«' WHEN text GLOB '“*' THEN '“' ELSE '"' END AS opener,
       COUNT(*) AS lines, COUNT(DISTINCT chapter) AS chapters
FROM paragraphs
WHERE scene NOT LIKE '%.s0'
  AND (text GLOB '-*' OR text GLOB '—*' OR text GLOB '«*' OR text GLOB '“*' OR text GLOB '"*')
GROUP BY opener ORDER BY lines DESC;
