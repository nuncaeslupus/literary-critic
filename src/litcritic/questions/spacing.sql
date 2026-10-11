-- id = "spacing"
-- title = "Where are there double spaces or spaces before punctuation?"
-- family = "mechanics"
-- params = {}
SELECT anchor,
       instr(text, '  ') > 0 AS double_space,
       (instr(text, ' ,') + instr(text, ' .') + instr(text, ' ;') + instr(text, ' :')) > 0
         AS space_before_punct
FROM paragraphs
WHERE instr(text, '  ') > 0 OR instr(text, ' ,') > 0 OR instr(text, ' .') > 0
   OR instr(text, ' ;') > 0 OR instr(text, ' :') > 0
ORDER BY idx;
