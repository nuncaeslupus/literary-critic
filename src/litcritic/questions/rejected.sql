-- id = "rejected"
-- title = "Which issues did the writer reject, and why?"
-- family = "issues_progress"
-- params = {}
SELECT i.id, i.text AS issue, json_extract(d.fields_json, '$.reason') AS reason
FROM items d JOIN links l ON l.src = d.id AND l.rel = 'about'
JOIN v_issue i ON i.id = l.dst
WHERE d.type = 'decision' AND d.status != 'retired'
  AND json_extract(d.fields_json, '$.verdict') = 'rejected'
ORDER BY i.id;
