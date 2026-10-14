from alembic import context
from smarthive.db.engine import engine

# Raw SQL migrations, no ORM metadata: docs/05-backend/05-data-model.md is the schema's source.
with engine().connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
