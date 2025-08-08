-- Optional: create DB role and database (run with a superuser)
-- Adjust password as needed.
-- CREATE ROLE scr4per_user WITH LOGIN PASSWORD 'your_password_here';
-- CREATE DATABASE scr4per OWNER scr4per_user;
-- GRANT ALL PRIVILEGES ON DATABASE scr4per TO scr4per_user;

-- After connecting to DB `scr4per` as scr4per_user, run the schema:
-- \i db/schema.sql

-- Seed minimal data (optional)
-- INSERT INTO profiles(platform, username, full_name, profile_url, photo_url)
-- VALUES ('x', 'example', 'Example User', 'https://x.com/example', NULL)
-- ON CONFLICT DO NOTHING;
