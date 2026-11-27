-- ============================================================
-- 060_grouped_tag_filter.sql — AND across tag groups, OR within
--
-- 025_filter_contacts_by_tags ORs across all selected tags, so
-- combining facets (ct:INDIA + buyer) unions instead of
-- intersecting. This rewrite groups the selected tags by their
-- prefix (the part before ':', so ct:/ds:/st: each form a group;
-- the unprefixed role tags buyer/seller form a 'role' group),
-- ORs within each group, and ANDs across groups:
--
--   (ct:INDIA OR ct:GERMANY) AND buyer AND ds:turmeric-…
--
-- Same signature, security model, and grants as 025 — drop-in.
-- Idempotent — safe to run multiple times.
-- ============================================================

CREATE OR REPLACE FUNCTION public.filter_contacts_by_tags(
  p_tag_ids UUID[],
  p_search TEXT DEFAULT NULL,
  p_limit INT DEFAULT 25,
  p_offset INT DEFAULT 0
)
RETURNS TABLE (contact contacts, total_count BIGINT)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  WITH sel AS (
    -- group key: prefix before ':' when present, else 'role' for
    -- buyer/seller, else the tag name itself (its own group)
    SELECT t.id,
           CASE
             WHEN position(':' IN t.name) > 0 THEN split_part(t.name, ':', 1)
             WHEN t.name IN ('buyer', 'seller') THEN 'role'
             ELSE t.name
           END AS grp
    FROM tags t
    WHERE t.id = ANY(p_tag_ids)
  ),
  groups AS (
    SELECT count(DISTINCT grp) AS n FROM sel
  ),
  matched AS (
    -- contacts matching at least one tag in EVERY selected group
    SELECT c.id, c.created_at
    FROM contacts c
    JOIN contact_tags ct ON ct.contact_id = c.id
    JOIN sel ON sel.id = ct.tag_id
    WHERE (
        p_search IS NULL
        OR c.name ILIKE '%' || p_search || '%'
        OR c.phone ILIKE '%' || p_search || '%'
        OR c.email ILIKE '%' || p_search || '%'
      )
    GROUP BY c.id, c.created_at
    HAVING count(DISTINCT sel.grp) = (SELECT n FROM groups)
  ),
  page AS (
    SELECT id, count(*) OVER() AS total_count
    FROM matched
    ORDER BY created_at DESC, id
    LIMIT p_limit OFFSET p_offset
  )
  SELECT c AS contact, page.total_count
  FROM page
  JOIN contacts c ON c.id = page.id
  ORDER BY c.created_at DESC, c.id;
$$;

ALTER FUNCTION public.filter_contacts_by_tags(UUID[], TEXT, INT, INT) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.filter_contacts_by_tags(UUID[], TEXT, INT, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.filter_contacts_by_tags(UUID[], TEXT, INT, INT) TO authenticated;
