"""add monitoring tables (ground alarm / lightning jump push+event / ingest file)

Revision ID: b8f3a2c1d4e5
Revises: f3a1b2c4d5e6
Create Date: 2026-07-28

监测预警数据接入：地面自动站报警 + 高空闪电跃增预警，详见项目计划
"监测预警数据接入与展示"。
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b8f3a2c1d4e5'
down_revision: Union[str, None] = 'f3a1b2c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'monitoring_ground_alarm',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('push_time', sa.BigInteger(), nullable=True),
        sa.Column('coverage_start', sa.BigInteger(), nullable=True),
        sa.Column('coverage_end', sa.BigInteger(), nullable=True),
        sa.Column('station_id', sa.Text(), nullable=False),
        sa.Column('station_name', sa.Text(), nullable=True),
        sa.Column('county', sa.Text(), nullable=True),
        sa.Column('province', sa.Text(), nullable=True),
        sa.Column('observed_at', sa.BigInteger(), nullable=False),
        sa.Column('pre', sa.Float(), nullable=True),
        sa.Column('rain_5m', sa.Float(), nullable=True),
        sa.Column('rain_10m', sa.Float(), nullable=True),
        sa.Column('rain_15m', sa.Float(), nullable=True),
        sa.Column('rain_20m', sa.Float(), nullable=True),
        sa.Column('rain_25m', sa.Float(), nullable=True),
        sa.Column('rain_30m', sa.Float(), nullable=True),
        sa.Column('level', sa.Text(), nullable=True),
        sa.Column('source_file', sa.Text(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            'station_id', 'observed_at', 'source_file',
            name='uq_ground_alarm_station_time_file',
        ),
    )
    op.create_index(
        'ix_ground_alarm_observed_at', 'monitoring_ground_alarm', ['observed_at']
    )
    op.create_index(
        'ix_ground_alarm_station_observed',
        'monitoring_ground_alarm',
        ['station_id', 'observed_at'],
    )

    op.create_table(
        'monitoring_lightning_push',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('push_time', sa.BigInteger(), nullable=True),
        sa.Column('coverage_start', sa.BigInteger(), nullable=True),
        sa.Column('coverage_end', sa.BigInteger(), nullable=True),
        sa.Column('csv_path', sa.Text(), nullable=False),
        sa.Column('json_path', sa.Text(), nullable=True),
        sa.Column('png_path', sa.Text(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('csv_path', name='uq_lightning_push_csv_path'),
    )
    op.create_index(
        'ix_lightning_push_push_time', 'monitoring_lightning_push', ['push_time']
    )

    op.create_table(
        'monitoring_lightning_jump_event',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('push_id', sa.Text(), nullable=False),
        sa.Column('cell_seq', sa.Text(), nullable=True),
        sa.Column('region', sa.Text(), nullable=False),
        sa.Column('jump_times', sa.Text(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    op.create_index(
        'ix_lightning_jump_push_id',
        'monitoring_lightning_jump_event',
        ['push_id'],
    )

    op.create_table(
        'monitoring_ingest_file',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('source_file', sa.Text(), nullable=False),
        sa.Column('ingested_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            'kind', 'source_file', name='uq_ingest_file_kind_source'
        ),
    )


def downgrade():
    op.drop_table('monitoring_ingest_file')
    op.drop_index('ix_lightning_jump_push_id', 'monitoring_lightning_jump_event')
    op.drop_table('monitoring_lightning_jump_event')
    op.drop_index('ix_lightning_push_push_time', 'monitoring_lightning_push')
    op.drop_table('monitoring_lightning_push')
    op.drop_index('ix_ground_alarm_station_observed', 'monitoring_ground_alarm')
    op.drop_index('ix_ground_alarm_observed_at', 'monitoring_ground_alarm')
    op.drop_table('monitoring_ground_alarm')
