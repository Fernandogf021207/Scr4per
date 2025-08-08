-- Scr4per DB schema for X, Instagram, Facebook
-- Safe enum creation
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'platform_enum'
    ) THEN
        CREATE TYPE platform_enum AS ENUM ('x', 'instagram', 'facebook');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'rel_type_enum'
    ) THEN
        CREATE TYPE rel_type_enum AS ENUM ('follower', 'following');
    END IF;
END $$;

-- Profiles for any platform
CREATE TABLE IF NOT EXISTS profiles (
    id              BIGSERIAL PRIMARY KEY,
    platform        platform_enum NOT NULL,
    username        TEXT NOT NULL,
    full_name       TEXT,
    profile_url     TEXT,
    photo_url       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_profiles UNIQUE (platform, username)
);

-- Relationships: followers / following of a given owner profile
CREATE TABLE IF NOT EXISTS relationships (
    id                  BIGSERIAL PRIMARY KEY,
    platform            platform_enum NOT NULL,
    owner_profile_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    related_profile_id  BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    rel_type            rel_type_enum NOT NULL,
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_relationship UNIQUE (platform, owner_profile_id, related_profile_id, rel_type)
);

-- Posts (needed to store commenters for X; can be reused for IG/FB if needed)
CREATE TABLE IF NOT EXISTS posts (
    id                  BIGSERIAL PRIMARY KEY,
    platform            platform_enum NOT NULL,
    owner_profile_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    post_url            TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_posts UNIQUE (platform, post_url)
);

-- Commenters on posts
CREATE TABLE IF NOT EXISTS comments (
    id                      BIGSERIAL PRIMARY KEY,
    post_id                 BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    commenter_profile_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_comments UNIQUE (post_id, commenter_profile_id)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_profiles_platform_username ON profiles(platform, username);
CREATE INDEX IF NOT EXISTS idx_relationships_owner_type ON relationships(owner_profile_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_posts_owner ON posts(owner_profile_id);
