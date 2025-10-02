-- ============================================================
-- schema_merged.sql  (Scr4per)
-- Crea/actualiza: red_x, red_instagram, red_facebook
-- Incluye migraciones: 'friend' en FB y tablas reactions (X/IG/FB)
-- Es idempotente.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1) Esquemas
-- ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS red_x;
CREATE SCHEMA IF NOT EXISTS red_instagram;
CREATE SCHEMA IF NOT EXISTS red_facebook;

-- ------------------------------------------------------------
-- 2) Enums por esquema (crear si no existen)
-- ------------------------------------------------------------
DO $$
BEGIN
  -- red_x
  IF to_regtype('red_x.platform_enum') IS NULL THEN
    CREATE TYPE red_x.platform_enum AS ENUM ('x');
  END IF;
  IF to_regtype('red_x.rel_type_enum') IS NULL THEN
    CREATE TYPE red_x.rel_type_enum AS ENUM ('follower', 'following');
  END IF;

  -- red_instagram
  IF to_regtype('red_instagram.platform_enum') IS NULL THEN
    CREATE TYPE red_instagram.platform_enum AS ENUM ('instagram');
  END IF;
  IF to_regtype('red_instagram.rel_type_enum') IS NULL THEN
    CREATE TYPE red_instagram.rel_type_enum AS ENUM ('follower', 'following');
  END IF;

  -- red_facebook
  IF to_regtype('red_facebook.platform_enum') IS NULL THEN
    CREATE TYPE red_facebook.platform_enum AS ENUM ('facebook');
  END IF;
  IF to_regtype('red_facebook.rel_type_enum') IS NULL THEN
    CREATE TYPE red_facebook.rel_type_enum AS ENUM ('follower', 'following');
  END IF;
END
$$;

-- Asegurar que 'friend' esté en el enum de Facebook (migración)
DO $$
BEGIN
  -- si existe el enum, añade 'friend' si falta
  IF to_regtype('red_facebook.rel_type_enum') IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
      JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname = 'red_facebook'
        AND t.typname = 'rel_type_enum'
        AND e.enumlabel = 'friend'
    ) THEN
      EXECUTE 'ALTER TYPE red_facebook.rel_type_enum ADD VALUE IF NOT EXISTS ''friend''';
    END IF;
  END IF;
END
$$;

-- (Compat opcional por si alguna instalación usa un esquema 'core' con rel_type_enum)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'rel_type_enum' AND n.nspname = 'core'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
      JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname = 'core'
        AND t.typname = 'rel_type_enum'
        AND e.enumlabel = 'friend'
    ) THEN
      EXECUTE 'ALTER TYPE core.rel_type_enum ADD VALUE IF NOT EXISTS ''friend''';
    END IF;
  END IF;
END
$$;

-- ------------------------------------------------------------
-- 3) Tablas por esquema
--    (perfiles, relaciones, posts, comments, reactions)
-- ------------------------------------------------------------

-- ======================== red_x ========================
CREATE TABLE IF NOT EXISTS red_x.profiles (
  id          BIGSERIAL PRIMARY KEY,
  platform    red_x.platform_enum NOT NULL DEFAULT 'x',
  username    TEXT NOT NULL,
  full_name   TEXT,
  profile_url TEXT,
  photo_url   TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_profiles_x UNIQUE (platform, username),
  CONSTRAINT chk_profiles_platform_x CHECK (platform = 'x')
);

CREATE TABLE IF NOT EXISTS red_x.relationships (
  id                  BIGSERIAL PRIMARY KEY,
  platform            red_x.platform_enum NOT NULL DEFAULT 'x',
  owner_profile_id    BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
  related_profile_id  BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
  rel_type            red_x.rel_type_enum NOT NULL,
  collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_relationship_x UNIQUE (platform, owner_profile_id, related_profile_id, rel_type),
  CONSTRAINT chk_relationships_platform_x CHECK (platform = 'x')
);

CREATE TABLE IF NOT EXISTS red_x.posts (
  id               BIGSERIAL PRIMARY KEY,
  platform         red_x.platform_enum NOT NULL DEFAULT 'x',
  owner_profile_id BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
  post_url         TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_posts_x UNIQUE (platform, post_url),
  CONSTRAINT chk_posts_platform_x CHECK (platform = 'x')
);

CREATE TABLE IF NOT EXISTS red_x.comments (
  id                    BIGSERIAL PRIMARY KEY,
  post_id               BIGINT NOT NULL REFERENCES red_x.posts(id) ON DELETE CASCADE,
  commenter_profile_id  BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
  first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_comments_x UNIQUE (post_id, commenter_profile_id)
);

-- reactions (creada por migración; dejamos IF NOT EXISTS)
CREATE TABLE IF NOT EXISTS red_x.reactions (
  id                  BIGSERIAL PRIMARY KEY,
  post_id             BIGINT NOT NULL REFERENCES red_x.posts(id) ON DELETE CASCADE,
  reactor_profile_id  BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
  reaction_type       TEXT,
  first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_reactions_x UNIQUE (post_id, reactor_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_x_profiles_platform_username ON red_x.profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_x_relationships_owner_type ON red_x.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_x_posts_owner ON red_x.posts(owner_profile_id);

-- ======================== red_instagram ========================
CREATE TABLE IF NOT EXISTS red_instagram.profiles (
  id          BIGSERIAL PRIMARY KEY,
  platform    red_instagram.platform_enum NOT NULL DEFAULT 'instagram',
  username    TEXT NOT NULL,
  full_name   TEXT,
  profile_url TEXT,
  photo_url   TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_profiles_ig UNIQUE (platform, username),
  CONSTRAINT chk_profiles_platform_ig CHECK (platform = 'instagram')
);

CREATE TABLE IF NOT EXISTS red_instagram.relationships (
  id                  BIGSERIAL PRIMARY KEY,
  platform            red_instagram.platform_enum NOT NULL DEFAULT 'instagram',
  owner_profile_id    BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
  related_profile_id  BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
  rel_type            red_instagram.rel_type_enum NOT NULL,
  collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_relationship_ig UNIQUE (platform, owner_profile_id, related_profile_id, rel_type),
  CONSTRAINT chk_relationships_platform_ig CHECK (platform = 'instagram')
);

CREATE TABLE IF NOT EXISTS red_instagram.posts (
  id               BIGSERIAL PRIMARY KEY,
  platform         red_instagram.platform_enum NOT NULL DEFAULT 'instagram',
  owner_profile_id BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
  post_url         TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_posts_ig UNIQUE (platform, post_url),
  CONSTRAINT chk_posts_platform_ig CHECK (platform = 'instagram')
);

CREATE TABLE IF NOT EXISTS red_instagram.comments (
  id                    BIGSERIAL PRIMARY KEY,
  post_id               BIGINT NOT NULL REFERENCES red_instagram.posts(id) ON DELETE CASCADE,
  commenter_profile_id  BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
  first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_comments_ig UNIQUE (post_id, commenter_profile_id)
);

CREATE TABLE IF NOT EXISTS red_instagram.reactions (
  id                  BIGSERIAL PRIMARY KEY,
  post_id             BIGINT NOT NULL REFERENCES red_instagram.posts(id) ON DELETE CASCADE,
  reactor_profile_id  BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
  reaction_type       TEXT,
  first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_reactions_ig UNIQUE (post_id, reactor_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_ig_profiles_platform_username ON red_instagram.profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_ig_relationships_owner_type ON red_instagram.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_ig_posts_owner ON red_instagram.posts(owner_profile_id);

-- ======================== red_facebook ========================
CREATE TABLE IF NOT EXISTS red_facebook.profiles (
  id          BIGSERIAL PRIMARY KEY,
  platform    red_facebook.platform_enum NOT NULL DEFAULT 'facebook',
  username    TEXT NOT NULL,
  full_name   TEXT,
  profile_url TEXT,
  photo_url   TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_profiles_fb UNIQUE (platform, username),
  CONSTRAINT chk_profiles_platform_fb CHECK (platform = 'facebook')
);

CREATE TABLE IF NOT EXISTS red_facebook.relationships (
  id                  BIGSERIAL PRIMARY KEY,
  platform            red_facebook.platform_enum NOT NULL DEFAULT 'facebook',
  owner_profile_id    BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
  related_profile_id  BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
  rel_type            red_facebook.rel_type_enum NOT NULL,
  collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_relationship_fb UNIQUE (platform, owner_profile_id, related_profile_id, rel_type),
  CONSTRAINT chk_relationships_platform_fb CHECK (platform = 'facebook')
);

CREATE TABLE IF NOT EXISTS red_facebook.posts (
  id               BIGSERIAL PRIMARY KEY,
  platform         red_facebook.platform_enum NOT NULL DEFAULT 'facebook',
  owner_profile_id BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
  post_url         TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_posts_fb UNIQUE (platform, post_url),
  CONSTRAINT chk_posts_platform_fb CHECK (platform = 'facebook')
);

CREATE TABLE IF NOT EXISTS red_facebook.comments (
  id                    BIGSERIAL PRIMARY KEY,
  post_id               BIGINT NOT NULL REFERENCES red_facebook.posts(id) ON DELETE CASCADE,
  commenter_profile_id  BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
  first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_comments_fb UNIQUE (post_id, commenter_profile_id)
);

CREATE TABLE IF NOT EXISTS red_facebook.reactions (
  id                  BIGSERIAL PRIMARY KEY,
  post_id             BIGINT NOT NULL REFERENCES red_facebook.posts(id) ON DELETE CASCADE,
  reactor_profile_id  BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
  reaction_type       TEXT,
  first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_reactions_fb UNIQUE (post_id, reactor_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_fb_profiles_platform_username ON red_facebook.profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_fb_relationships_owner_type ON red_facebook.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_fb_posts_owner ON red_facebook.posts(owner_profile_id);

COMMIT;

-- ============================================================
-- Fin schema_merged.sql
-- ============================================================
