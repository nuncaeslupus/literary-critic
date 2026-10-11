-- id = "setups-without-payoff"
-- title = "Which setups have no payoff?"
-- family = "threads"
-- params = {}
SELECT s.id, s.label, (SELECT anchor FROM paragraphs WHERE idx = s.para_idx) AS at
FROM v_setup s
WHERE s.side = 'setup' AND s.status != 'retired'
  AND NOT EXISTS (SELECT 1 FROM links l WHERE l.dst = s.id AND l.rel = 'pays_off')
ORDER BY s.para_idx;
