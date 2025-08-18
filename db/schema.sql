

-- Dedicated schemas only
CREATE SCHEMA IF NOT EXISTS red_x;
CREATE SCHEMA IF NOT EXISTS red_instagram;
CREATE SCHEMA IF NOT EXISTS red_facebook;

-- Create enums inside each target schema (idempotent)
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

-- ======================== SCHEMA red_x ========================
-- Profiles
CREATE TABLE IF NOT EXISTS red_x.profiles (
    id              BIGSERIAL PRIMARY KEY,
    platform        red_x.platform_enum NOT NULL DEFAULT 'x',
    username        TEXT NOT NULL,
    full_name       TEXT,
    profile_url     TEXT,
    photo_url       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_profiles_x UNIQUE (platform, username),
    CONSTRAINT chk_profiles_platform_x CHECK (platform = 'x')
);

-- Relationships
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

-- Posts
CREATE TABLE IF NOT EXISTS red_x.posts (
    id                  BIGSERIAL PRIMARY KEY,
    platform            red_x.platform_enum NOT NULL DEFAULT 'x',
    owner_profile_id    BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
    post_url            TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_posts_x UNIQUE (platform, post_url),
    CONSTRAINT chk_posts_platform_x CHECK (platform = 'x')
);

-- Comments
CREATE TABLE IF NOT EXISTS red_x.comments (
    id                      BIGSERIAL PRIMARY KEY,
    post_id                 BIGINT NOT NULL REFERENCES red_x.posts(id) ON DELETE CASCADE,
    commenter_profile_id    BIGINT NOT NULL REFERENCES red_x.profiles(id) ON DELETE CASCADE,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_comments_x UNIQUE (post_id, commenter_profile_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_x_profiles_platform_username ON red_x.profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_x_relationships_owner_type ON red_x.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_x_posts_owner ON red_x.posts(owner_profile_id);

-- ======================== SCHEMA red_instagram ========================
-- Profiles
CREATE TABLE IF NOT EXISTS red_instagram.profiles (
    id              BIGSERIAL PRIMARY KEY,
    platform        red_instagram.platform_enum NOT NULL DEFAULT 'instagram',
    username        TEXT NOT NULL,
    full_name       TEXT,
    profile_url     TEXT,
    photo_url       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_profiles_ig UNIQUE (platform, username),
    CONSTRAINT chk_profiles_platform_ig CHECK (platform = 'instagram')
);

-- Relationships
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

-- Posts
CREATE TABLE IF NOT EXISTS red_instagram.posts (
    id                  BIGSERIAL PRIMARY KEY,
    platform            red_instagram.platform_enum NOT NULL DEFAULT 'instagram',
    owner_profile_id    BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
    post_url            TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_posts_ig UNIQUE (platform, post_url),
    CONSTRAINT chk_posts_platform_ig CHECK (platform = 'instagram')
);

-- Comments
CREATE TABLE IF NOT EXISTS red_instagram.comments (
    id                      BIGSERIAL PRIMARY KEY,
    post_id                 BIGINT NOT NULL REFERENCES red_instagram.posts(id) ON DELETE CASCADE,
    commenter_profile_id    BIGINT NOT NULL REFERENCES red_instagram.profiles(id) ON DELETE CASCADE,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_comments_ig UNIQUE (post_id, commenter_profile_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ig_profiles_platform_username ON red_instagram.profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_ig_relationships_owner_type ON red_instagram.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_ig_posts_owner ON red_instagram.posts(owner_profile_id);

-- ======================== SCHEMA red_facebook ========================
-- Profiles
CREATE TABLE IF NOT EXISTS red_facebook.profiles (
    id              BIGSERIAL PRIMARY KEY,
    platform        red_facebook.platform_enum NOT NULL DEFAULT 'facebook',
    username        TEXT NOT NULL,
    full_name       TEXT,
    profile_url     TEXT,
    photo_url       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_profiles_fb UNIQUE (platform, username),
    CONSTRAINT chk_profiles_platform_fb CHECK (platform = 'facebook')
);

-- Relationships
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

-- Posts
CREATE TABLE IF NOT EXISTS red_facebook.posts (
    id                  BIGSERIAL PRIMARY KEY,
    platform            red_facebook.platform_enum NOT NULL DEFAULT 'facebook',
    owner_profile_id    BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
    post_url            TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_posts_fb UNIQUE (platform, post_url),
    CONSTRAINT chk_posts_platform_fb CHECK (platform = 'facebook')
);

-- Comments
CREATE TABLE IF NOT EXISTS red_facebook.comments (
    id                      BIGSERIAL PRIMARY KEY,
    post_id                 BIGINT NOT NULL REFERENCES red_facebook.posts(id) ON DELETE CASCADE,
    commenter_profile_id    BIGINT NOT NULL REFERENCES red_facebook.profiles(id) ON DELETE CASCADE,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_comments_fb UNIQUE (post_id, commenter_profile_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_fb_profiles_platform_username ON red_facebook.profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_fb_relationships_owner_type ON red_facebook.relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_fb_posts_owner ON red_facebook.posts(owner_profile_id);