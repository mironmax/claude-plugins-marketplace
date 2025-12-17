"""Constants for knowledge graph operations."""

# Token estimation
BASE_NODE_TOKENS = 20
CHARS_PER_TOKEN = 4
TOKENS_PER_EDGE = 15

# Compaction
COMPACTION_TARGET_RATIO = 0.9

# Session
SESSION_ID_LENGTH = 8
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# Grace periods
GRACE_PERIOD_DAYS = 7
ORPHAN_GRACE_DAYS = 7

# Backup retention
MAX_RECENT_BACKUPS = 3    # Keep 3 most recent (within hours)
MAX_DAILY_BACKUPS = 7     # Keep 7 daily backups (one per day)
MAX_WEEKLY_BACKUPS = 4    # Keep 4 weekly backups (one per week)
BACKUP_INTERVAL_SECONDS = 3600  # Minimum 1 hour between backups

# Graph levels
LEVELS = ("user", "project")
