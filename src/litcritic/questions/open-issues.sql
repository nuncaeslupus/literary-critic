-- id = "open-issues"
-- title = "Which issues are still open, by level and severity?"
-- family = "issues_progress"
-- params = {}
SELECT level, severity, COUNT(*) AS open
FROM v_issue i
WHERE i.status = 'active' AND COALESCE(i.kind, 'problem') = 'problem'
  AND NOT EXISTS (
    SELECT 1 FROM links l JOIN items d ON d.id = l.src
    WHERE l.dst = i.id AND l.rel = 'about' AND d.type = 'decision' AND d.status != 'retired'
      AND json_extract(d.fields_json, '$.verdict') IN ('rejected', 'done', 'done_differently'))
GROUP BY level, severity ORDER BY level, severity;
