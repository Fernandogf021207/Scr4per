-- ============================================================
-- Scr4per unified schema (core)
-- Combines base schema + all migrations into a single script.
-- Drops legacy platform-specific schemas and builds everything under `core`.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- Ensure target schema + helpers
-- ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS core;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

-- Enums (create or extend with missing values)
DO $$
DECLARE
  label TEXT;
BEGIN
  IF to_regtype('core.platform_enum') IS NULL THEN
    CREATE TYPE core.platform_enum AS ENUM ('facebook', 'instagram', 'x');
  END IF;

  IF to_regtype('core.rel_type_enum') IS NULL THEN
    CREATE TYPE core.rel_type_enum AS ENUM (
      'follower', 'following', 'followed', 'friend', 'commented', 'reacted'
    );
  ELSE
    FOREACH label IN ARRAY ARRAY['follower','following','followed','friend','commented','reacted'] LOOP
      IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'core'
          AND t.typname = 'rel_type_enum'
          AND e.enumlabel = label
      ) THEN
        EXECUTE format('ALTER TYPE core.rel_type_enum ADD VALUE IF NOT EXISTS %L', label);
      END IF;
    END LOOP;
  END IF;
END
$$;

-- ------------------------------------------------------------
-- Tables
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.profiles (
  id          BIGSERIAL PRIMARY KEY,
  platform    core.platform_enum NOT NULL,
  username    TEXT NOT NULL,
  full_name   TEXT,
  profile_url TEXT,
  photo_url   TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_core_profiles UNIQUE (platform, username)
);

CREATE INDEX IF NOT EXISTS idx_core_profiles_platform_username ON core.profiles(platform, username);

CREATE TABLE IF NOT EXISTS core.relationships (
  id                  BIGSERIAL PRIMARY KEY,
  platform            core.platform_enum NOT NULL,
  owner_profile_id    BIGINT NOT NULL REFERENCES core.profiles(id) ON DELETE CASCADE,
  related_profile_id  BIGINT NOT NULL REFERENCES core.profiles(id) ON DELETE CASCADE,
  rel_type            core.rel_type_enum NOT NULL,
  collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_core_relationships UNIQUE (platform, owner_profile_id, related_profile_id, rel_type)
);

CREATE INDEX IF NOT EXISTS idx_core_relationships_owner_type ON core.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_core_relationships_related_type ON core.relationships(related_profile_id, rel_type);

CREATE TABLE IF NOT EXISTS core.posts (
  id               BIGSERIAL PRIMARY KEY,
  platform         core.platform_enum NOT NULL,
  owner_profile_id BIGINT NOT NULL REFERENCES core.profiles(id) ON DELETE CASCADE,
  post_url         TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_core_posts UNIQUE (platform, post_url)
);

CREATE INDEX IF NOT EXISTS idx_core_posts_owner ON core.posts(owner_profile_id);

CREATE TABLE IF NOT EXISTS core.comments (
  id                    BIGSERIAL PRIMARY KEY,
  post_id               BIGINT NOT NULL REFERENCES core.posts(id) ON DELETE CASCADE,
  commenter_profile_id  BIGINT NOT NULL REFERENCES core.profiles(id) ON DELETE CASCADE,
  first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_core_comments UNIQUE (post_id, commenter_profile_id)
);

CREATE TABLE IF NOT EXISTS core.reactions (
  id                  BIGSERIAL PRIMARY KEY,
  post_id             BIGINT NOT NULL REFERENCES core.posts(id) ON DELETE CASCADE,
  reactor_profile_id  BIGINT NOT NULL REFERENCES core.profiles(id) ON DELETE CASCADE,
  reaction_type       TEXT,
  first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_core_reactions UNIQUE (post_id, reactor_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_core_reactions_post ON core.reactions(post_id);
CREATE INDEX IF NOT EXISTS idx_core_reactions_reactor ON core.reactions(reactor_profile_id);

-- Graph sessions (autosave / cached layouts)
CREATE TABLE IF NOT EXISTS core.graph_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_platform   core.platform_enum NOT NULL,
  owner_username   TEXT NOT NULL,
  elements         JSONB NOT NULL,
  style            JSONB,
  layout           JSONB,
  elements_path    TEXT,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_core_graph_sessions UNIQUE (owner_platform, owner_username)
);

CREATE INDEX IF NOT EXISTS idx_core_graph_sessions_elements_path ON core.graph_sessions(elements_path);

COMMIT;

-- Cleanup legacy helper function if it exists
DROP FUNCTION IF EXISTS _add_enum_value_if_not_exists(text, text, text);

-- Optional: leave `public` empty; use `core` as working schema going forward.
-- Remove any remaining legacy schemas if necessary
DROP SCHEMA IF EXISTS red_x CASCADE;
DROP SCHEMA IF EXISTS red_instagram CASCADE;
DROP SCHEMA IF EXISTS red_facebook CASCADE;
-- ============================================================
-- End of unified schema
-- ============================================================
