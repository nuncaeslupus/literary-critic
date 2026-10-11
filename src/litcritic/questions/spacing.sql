-- id = "spacing"
-- title = "Where are there double spaces or spaces before punctuation?"
-- family = "mechanics"
-- params = {}
WITH lang AS (SELECT COALESCE(language, '') AS l FROM works LIMIT 1)
SELECT anchor,
       instr(text, '  ') > 0 AS double_space,
       (instr(text, ' ,') + instr(text, ' .')
        + CASE WHEN (SELECT l FROM lang) = 'fr' THEN 0
               ELSE instr(text, ' ;') + instr(text, ' :') + instr(text, ' ?') + instr(text, ' !')
          END) > 0 AS space_before_punct
FROM paragraphs
WHERE instr(text, '  ') > 0 OR instr(text, ' ,') > 0 OR instr(text, ' .') > 0
   OR ((SELECT l FROM lang) != 'fr'
       AND (instr(text, ' ;') > 0 OR instr(text, ' :') > 0
            OR instr(text, ' ?') > 0 OR instr(text, ' !') > 0))
ORDER BY idx;
