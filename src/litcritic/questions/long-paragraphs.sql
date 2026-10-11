-- id = "long-paragraphs"
-- title = "Which paragraphs are much longer than usual?"
-- family = "style"
-- params = { factor = "times the average" }
-- defaults = { factor = 3 }
SELECT p.anchor, p.words
FROM paragraphs p, (SELECT AVG(words) AS mean FROM paragraphs WHERE words > 0) s
WHERE p.words > :factor * s.mean ORDER BY p.words DESC;
