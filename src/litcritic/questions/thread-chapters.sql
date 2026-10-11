-- id = "thread-chapters"
-- title = "Which storylines advance in each chapter?"
-- family = "threads"
-- params = {}
SELECT p.chapter, group_concat(DISTINCT t.name) AS threads, COUNT(DISTINCT t.id) AS n
FROM v_thread t JOIN spans s ON s.item_id = t.id
JOIN paragraphs p ON p.idx BETWEEN s.start_idx AND s.end_idx
GROUP BY p.chapter ORDER BY MIN(p.idx);
