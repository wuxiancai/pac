from alembic import context


config = context.config
connection = config.attributes.get("connection")
if connection is None:
    raise RuntimeError("SQLCipher POC migrations require the in-memory keyed connection")

context.configure(connection=connection, target_metadata=None, render_as_batch=False)
with context.begin_transaction():
    context.run_migrations()
