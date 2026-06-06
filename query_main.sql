SELECT
g.*,
m.*,
s.*,
t.*
FROM games g
left join mechanics m on g.BGGId = m.BGGId
left join subcategories s on g.BGGId = s.BGGId
left join themes t on g.BGGId = t.BGGId
WHERE g.NumUserRatings >= 100
AND g.YearPublished >= 1950