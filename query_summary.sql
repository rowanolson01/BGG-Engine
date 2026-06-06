SELECT 
    COUNT(*) as total_games,
    ROUND(AVG(AvgRating), 2) as avg_rating,
    ROUND(AVG(GameWeight), 2) as avg_weight,
    MIN(YearPublished) as earliest_year,
    MAX(YearPublished) as latest_year,
    SUM(NumOwned) as total_copies_owned
FROM games
WHERE NumUserRatings >= 100
AND YearPublished >= 1950