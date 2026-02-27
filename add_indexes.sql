-- Index sur les colonnes les plus requêtées
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_club_id ON users(club_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_is_active ON users(is_active);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_deleted_at ON users(deleted_at) WHERE deleted_at IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_club_members_club_id ON club_members(club_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_club_members_user_id ON club_members(user_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_club_members_invite_token ON club_members(invite_token) WHERE invite_token IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_club_members_status ON club_members(status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_matches_user_id ON matches(user_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_matches_club_id ON matches(club_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_players_club_id ON players(club_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_players_user_id ON players(user_id);
