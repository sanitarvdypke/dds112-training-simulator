"""DDS recipient profile."""
from alembic import op
import sqlalchemy as sa
revision = "0005_dds_profiles"
down_revision = "0004_ekp_classifier"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("dds_service_key", sa.String(64), nullable=True))

def downgrade():
    op.drop_column("users", "dds_service_key")
