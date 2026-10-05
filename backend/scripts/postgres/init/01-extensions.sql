-- btree_gist backs the appointments no-overlap exclusion constraint (plan §5).
-- btree_gin_ginip_ops backs trigram/pg_trgm search on customers (plan §3).
-- Run automatically on first container start.
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
