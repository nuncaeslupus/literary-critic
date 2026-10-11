-- id = "needs-reread"
-- title = "Which knowledge needs re-reading after the last draft?"
-- family = "issues_progress"
-- params = {}
SELECT i.id, i.type, i.text, group_concat(DISTINCT s.state) AS span_states
FROM items i LEFT JOIN spans s ON s.item_id = i.id
WHERE i.status = 'needs_reread' OR s.state IN ('changed', 'lost')
GROUP BY i.id ORDER BY i.type, i.id;
