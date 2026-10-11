-- id = "scenes-per-chapter"
-- title = "How many scenes does each chapter have, and how long are they?"
-- family = "structure"
-- params = {}
SELECT c.id, COUNT(s.id) AS scenes, CAST(AVG(s.words) AS INTEGER) AS avg_words,
       MIN(s.words) AS shortest, MAX(s.words) AS longest
FROM chapters c LEFT JOIN scenes s ON s.chapter = c.id
GROUP BY c.id ORDER BY c.idx;
