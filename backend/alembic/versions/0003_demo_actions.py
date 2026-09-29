"""Complete seed card requirements without changing historical assessments."""
from alembic import op

revision = "0003_demo_actions"
down_revision = "0002_classifier_import"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""INSERT INTO expected_actions (id, scenario_id, action_type, payload, required, weight, order_no)
        SELECT gen_random_uuid(), s.id, 'SELECT_SERVICES', jsonb_build_object('services', s.expected_state->'services'), true, 1, 4
        FROM scenarios s WHERE s.code IN ('DEMO-001','DEMO-002','DEMO-003')
        AND NOT EXISTS (SELECT 1 FROM expected_actions e WHERE e.scenario_id=s.id AND e.action_type='SELECT_SERVICES')""")
    op.execute("""INSERT INTO expected_actions (id, scenario_id, action_type, payload, required, weight, order_no)
        SELECT gen_random_uuid(), s.id, 'SELECT_TAGS', jsonb_build_object('tags', s.incident_payload->'tags'), true, 1, 5
        FROM scenarios s WHERE s.code IN ('DEMO-001','DEMO-002','DEMO-003')
        AND NOT EXISTS (SELECT 1 FROM expected_actions e WHERE e.scenario_id=s.id AND e.action_type='SELECT_TAGS')""")

def downgrade():
    op.execute("""DELETE FROM expected_actions WHERE action_type IN ('SELECT_SERVICES','SELECT_TAGS')
        AND scenario_id IN (SELECT id FROM scenarios WHERE code IN ('DEMO-001','DEMO-002','DEMO-003'))""")
