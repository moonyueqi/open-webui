"""add calendar tables

Revision ID: 56359461a091
Revises: d4e5f6a7b8c9
Create Date: 2026-04-19 16:20:58.162045

Ported from upstream open-webui (commit 8d739e2ab). The original upstream
down_revision pointed to c1d2e3f4a5b6 (shared_chat table) which is not present
on the common branch; calendar tables don't depend on that table, so we chain
this migration after our ported automation migration d4e5f6a7b8c9.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56359461a091'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'calendar',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('color', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calendar_user', 'calendar', ['user_id'], unique=False)

    op.create_table(
        'calendar_event',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('calendar_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_at', sa.BigInteger(), nullable=False),
        sa.Column('end_at', sa.BigInteger(), nullable=True),
        sa.Column('all_day', sa.Boolean(), nullable=False),
        sa.Column('rrule', sa.Text(), nullable=True),
        sa.Column('color', sa.Text(), nullable=True),
        sa.Column('location', sa.Text(), nullable=True),
        sa.Column('data', sa.JSON(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('is_cancelled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calendar_event_calendar', 'calendar_event', ['calendar_id', 'start_at'], unique=False)
    op.create_index('ix_calendar_event_user_date', 'calendar_event', ['user_id', 'start_at'], unique=False)

    op.create_table(
        'calendar_event_attendee',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_event_attendee'),
    )
    op.create_index('ix_calendar_event_attendee_user', 'calendar_event_attendee', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_calendar_event_attendee_user', table_name='calendar_event_attendee')
    op.drop_table('calendar_event_attendee')
    op.drop_index('ix_calendar_event_user_date', table_name='calendar_event')
    op.drop_index('ix_calendar_event_calendar', table_name='calendar_event')
    op.drop_table('calendar_event')
    op.drop_index('ix_calendar_user', table_name='calendar')
    op.drop_table('calendar')
