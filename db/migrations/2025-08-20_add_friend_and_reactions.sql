-- Add 'friend' to Facebook rel_type enum and create reactions tables across schemas

-- Facebook: extend enum safely
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'rel_type_enum' AND n.nspname = 'red_facebook'
    ) THEN
        -- enum missing (should exist from schema.sql); skip
        RAISE NOTICE 'Enum red_facebook.rel_type_enum not found; ensure schema.sql applied first';
    ELSE
        -- Add value if not exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'red_facebook' AND t.typname = 'rel_type_enum' AND e.enumlabel = 'friend'
        ) THEN
            EXECUTE 'ALTER TYPE red_facebook.rel_type_enum ADD VALUE IF NOT EXISTS ''friend''';
        END IF;
    END IF;
END$$;

-- Reactions tables for each schema
CREATE TABLE IF NOT EXISTS red_x.reactions (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES red_x.posts(id) ON DELETE CASCADE,
    reactor_profile_id BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
    reaction_type TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rx_x UNIQUE (post_id, reactor_profile_id)
);

CREATE TABLE IF NOT EXISTS red_instagram.reactions (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES red_instagram.posts(id) ON DELETE CASCADE,
    reactor_profile_id BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
    reaction_type TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rx_ig UNIQUE (post_id, reactor_profile_id)
);

CREATE TABLE IF NOT EXISTS red_facebook.reactions (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES red_facebook.posts(id) ON DELETE CASCADE,
    reactor_profile_id BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
    reaction_type TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rx_fb UNIQUE (post_id, reactor_profile_id)
);
