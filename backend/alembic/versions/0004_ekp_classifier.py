"""Versioned EKP imports and normalized incident records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_ekp_classifier"
down_revision = "0003_demo_actions"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("classifier_imports", sa.Column("source_sha256", sa.String(64)))
    op.add_column("classifier_imports", sa.Column("format", sa.String(30), nullable=False, server_default="legacy"))
    op.add_column("classifier_imports", sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("classifier_imports", sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.create_table("classifier_entries",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("import_id", sa.UUID(), sa.ForeignKey("classifier_imports.id"), nullable=False),
        sa.Column("source_sheet", sa.String(255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("group_name", sa.String(1000)),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("import_id", "source_sheet", "source_row"))
    op.create_index("ix_classifier_entries_import_id", "classifier_entries", ["import_id"])
    op.create_index("ix_classifier_entries_code", "classifier_entries", ["code"])

def downgrade():
    op.drop_table("classifier_entries")
    for name in ["warnings", "metadata_json", "format", "source_sha256"]:
        op.drop_column("classifier_imports", name)
